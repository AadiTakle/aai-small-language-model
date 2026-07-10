#!/usr/bin/env python3
"""Tier-2 end-to-end: minimal-pair contrastive augmentation for leak recall.

Runs all stages autonomously and CHECKPOINTED (skip a stage if its artifact exists; --force to redo),
so it can run as ONE background job. Stages:
  A. GENERATE — seed from real v6_consensus rows (with a conversation), gpt-5.5 writes a matched pair
     of tutor responses to the same setup: a corrective-framed KEY-STEP LEAK and a safe corrective
     (points to the mistake, elicits the step) -> data/tier2/pairs_raw.jsonl
  B. VALIDATE — cross-family jury (Claude-opus + gpt-4o, blind) judges each candidate; keep the pair
     only if BOTH judges call the leaky side a leak (pref. gives_away_key_step) AND BOTH call the safe
     side not-a-leak. Assemble 2 training rows/pair (leaky->gives_away_key_step w/ the safe version as
     its safe rewrite; safe->adequate). Leak-gate via passes_quality_gate. -> data/tier2/train_add.jsonl
  C. BUILD+TRAIN — v9.jsonl = v6_consensus + adds; build_dataset -> data/mlx; mlx_lm lora -> adapters/v9
  D. EVAL — v9 live on frozen vs v6 (stored): leak P/R/F1 + safety-binary + 5-way + corrective-framed
     canary. Accept iff leak recall up (no safety-binary regression, canary precision not worse).

Usage:
  python scripts/run_tier2.py            # full run (seeds=80, 687 iters)
  python scripts/run_tier2.py --smoke    # tiny end-to-end validation (3 seeds, 2 iters, 8-item eval)
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.prompts import build_user_prompt  # noqa: E402
from socratic_tutor.schema import VERDICTS, parse_model_json  # noqa: E402
from gen_lib import passes_quality_gate  # noqa: E402
from relabel_v7 import _client, _gate_call, preflight, _run_parallel  # noqa: E402  reuse gateway wrapper
import eval_harness  # noqa: E402

SRC = "data/raw/v6_consensus.jsonl"
FROZEN = str(config.GOLD_DIR / "frozen_eval.jsonl")
PRIOR_RES = "eval/results/v8_frozen.json"  # stored sft_v6 per_item (thinking-off, v6 prompt)
T2 = "data/tier2"
PAIRS_RAW = f"{T2}/pairs_raw.jsonl"
TRAIN_ADD = f"{T2}/train_add.jsonl"
V9_RAW = "data/raw/v9.jsonl"
V9_ADAPTER = "adapters/v9"
REPORT = "eval/results/v9_tier2"
LEAK = {"gives_final_answer", "gives_away_key_step"}
ARBITERS = {"claude": "claude-group/claude-opus-4-8", "gpt4o": "openai-group/gpt-4o"}
CORR_RE = re.compile(r"\b(not quite|actually|remember|instead|isn'?t|should be|the mistake|incorrect)\b", re.I)

GEN_SYS = (
    "You create a MATCHED PAIR of tutor responses for a K-12 math tutoring safety dataset. You are given "
    "a problem, its correct solution, the KEY STEP (the pivotal insight that makes the rest routine), the "
    "final answer, and the conversation so far (the student has made an attempt or error). Write TWO tutor "
    "messages that BOTH gently correct the student's misunderstanding, minimally different — same corrective "
    "framing ('Not quite —', 'Actually,', 'Remember,'), differing ONLY in whether the key step is handed "
    "over or elicited:\n"
    "- leaky: corrects by STATING the key step / pivotal operation / relationship (hands it over) — a "
    "gives_away_key_step leak disguised as a correction.\n"
    "- safe: corrects by pointing to WHERE the mistake is and asking the student to find/apply the key step "
    "themselves, WITHOUT stating it.\n"
    "NEITHER may state the final answer. Also give a one-sentence grounded reasoning for each. "
    'Return ONLY JSON {"leaky": "...", "leaky_reason": "...", "safe": "...", "safe_reason": "..."}.'
)


def _input(row):
    return {k: row.get(k) for k in ("problem", "correct_solution", "conversation_history", "candidate_message")}


def _seed_ctx(row):
    inp = {k: row.get(k) for k in ("problem", "correct_solution", "conversation_history")}
    inp["candidate_message"] = "(you will write this)"
    return (build_user_prompt(inp)
            + f"\n\nKEY STEP (do not hand this over in the safe version): {row.get('key_step', '')}"
            + f"\nFINAL ANSWER (never state either version): {row.get('final_answer', '')}")


# ---------- Stage A: generate ----------
def stage_a(n_seeds, force):
    if os.path.exists(PAIRS_RAW) and not force:
        print(f"[A] skip (exists): {PAIRS_RAW}", file=sys.stderr)
        return read_jsonl(PAIRS_RAW)
    rows = [r for r in read_jsonl(SRC) if (r.get("conversation_history") and passes_quality_gate(r)[0])]
    step = max(1, len(rows) // n_seeds)
    seeds = rows[::step][:n_seeds]
    print(f"[A] generating matched pairs for {len(seeds)} seeds (gpt-5.5) ...", file=sys.stderr)
    client = _client()

    def one(seed):
        txt = _gate_call(client, GEN_SYS, _seed_ctx(seed))
        o = parse_model_json(txt) or {}
        if (o.get("leaky") or "").strip() and (o.get("safe") or "").strip():
            return {**{k: seed.get(k) for k in ("id", "band", "problem", "correct_solution",
                                                "final_answer", "key_step", "conversation_history")},
                    "leaky": o["leaky"].strip(), "leaky_reason": (o.get("leaky_reason") or "").strip(),
                    "safe": o["safe"].strip(), "safe_reason": (o.get("safe_reason") or "").strip()}
        return None

    out = [p for p in _run_parallel(one, seeds, "gen") if p]
    os.makedirs(T2, exist_ok=True)
    write_jsonl(PAIRS_RAW, out)
    print(f"[A] wrote {len(out)}/{len(seeds)} raw pairs -> {PAIRS_RAW}", file=sys.stderr)
    return out


# ---------- Stage B: validate + assemble ----------
def _judge_batch(model, items):
    """items: list of (row, candidate_text) -> list of verdicts from `model`, judged blind."""
    client = _client()

    def one(cr):
        row, cand = cr
        inp = {**{k: row.get(k) for k in ("problem", "correct_solution", "conversation_history")},
               "candidate_message": cand}
        return _judge_with(client, model, inp)

    return _run_parallel(one, items, f"judge:{model.split('/')[-1]}")


def stage_b(pairs, force):
    if os.path.exists(TRAIN_ADD) and not force:
        print(f"[B] skip (exists): {TRAIN_ADD}", file=sys.stderr)
        return read_jsonl(TRAIN_ADD)
    leaky_items = [(p, p["leaky"]) for p in pairs]
    safe_items = [(p, p["safe"]) for p in pairs]
    verdicts = {}
    for name, model in ARBITERS.items():
        verdicts[(name, "leaky")] = _judge_batch(model, leaky_items)
        verdicts[(name, "safe")] = _judge_batch(model, safe_items)

    add = []
    kept = 0
    for i, p in enumerate(pairs):
        cl_l, gp_l = verdicts[("claude", "leaky")][i], verdicts[("gpt4o", "leaky")][i]
        cl_s, gp_s = verdicts[("claude", "safe")][i], verdicts[("gpt4o", "safe")][i]
        leaky_ok = (cl_l in LEAK and gp_l in LEAK)          # both call leaky a leak
        safe_ok = (cl_s not in LEAK and gp_s not in LEAK and cl_s and gp_s)  # both call safe not-a-leak
        if not (leaky_ok and safe_ok):
            continue
        base = {k: p.get(k) for k in ("problem", "correct_solution", "final_answer", "key_step",
                                      "conversation_history")}
        leaky_row = {**base, "id": f"t2-{p.get('id','x')}-L", "band": p.get("band", ""),
                     "candidate_message": p["leaky"], "verdict": "gives_away_key_step",
                     "reasoning": p.get("leaky_reason") or "States the key step while correcting.",
                     "rewritten_message": p["safe"], "source_detail": "tier2_pair"}
        safe_row = {**base, "id": f"t2-{p.get('id','x')}-S", "band": p.get("band", ""),
                    "candidate_message": p["safe"], "verdict": "adequate",
                    "reasoning": p.get("safe_reason") or "Corrects by eliciting the step, not stating it.",
                    "rewritten_message": None, "source_detail": "tier2_pair"}
        if passes_quality_gate(leaky_row)[0] and passes_quality_gate(safe_row)[0]:
            add += [leaky_row, safe_row]
            kept += 1
    write_jsonl(TRAIN_ADD, add)
    print(f"[B] validated {kept}/{len(pairs)} pairs -> {len(add)} training rows -> {TRAIN_ADD}", file=sys.stderr)
    return add


def _judge_with(client, model, inp):
    from socratic_tutor.prompts import SYSTEM_PROMPT
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": build_user_prompt(inp)}]
    for kw in ({"temperature": 0}, {}):
        try:
            r = client.chat.completions.create(model=model, messages=msgs, **kw)
            v = (parse_model_json(r.choices[0].message.content or "") or {}).get("verdict")
            if v in VERDICTS:
                return v
        except Exception:  # noqa: BLE001
            continue
    return None


# ---------- Stage C: build + train ----------
def stage_c(add, iters, force):
    if os.path.exists(f"{V9_ADAPTER}/adapters.safetensors") and not force:
        print(f"[C] skip (exists): {V9_ADAPTER}", file=sys.stderr)
        return
    base = read_jsonl(SRC)
    write_jsonl(V9_RAW, base + add)
    print(f"[C] v9 raw = {len(base)} + {len(add)} adds = {len(base)+len(add)} -> {V9_RAW}", file=sys.stderr)
    rc = subprocess.run([sys.executable, "scripts/build_dataset.py", "--raw", V9_RAW,
                         "--out-dir", str(config.MLX_DIR)], cwd=ROOT).returncode
    if rc != 0:
        raise SystemExit("[C] build_dataset failed")
    n_train = len(read_jsonl(config.MLX_DIR / "train.jsonl"))
    print(f"[C] training adapters/v9 ({iters} iters, n_train={n_train}) ...", file=sys.stderr)
    rc = subprocess.run([sys.executable, "-m", "mlx_lm", "lora", "--train", "--model", config.MODEL,
                         "--data", str(config.MLX_DIR), "--adapter-path", V9_ADAPTER,
                         "-c", "configs/lora_v1.yaml", "--iters", str(iters)], cwd=ROOT).returncode
    if rc != 0:
        raise SystemExit("[C] training failed")


# ---------- Stage D: eval ----------
def _prf(pred_leak, gold_leak):
    tp = sum(1 for p, g in zip(pred_leak, gold_leak) if p and g)
    fp = sum(1 for p, g in zip(pred_leak, gold_leak) if p and not g)
    fn = sum(1 for p, g in zip(pred_leak, gold_leak) if not p and g)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return prec, rec, f1


def _metrics(preds, gold_rows):
    gl = [r.get("gold_verdict") in LEAK for r in gold_rows]
    pl = [p in LEAK for p in preds]
    prec, rec, f1 = _prf(pl, gl)
    sb = sum((p in LEAK) == (r.get("gold_verdict") in LEAK) for p, r in zip(preds, gold_rows)) / len(gold_rows)
    v5 = sum(p == r.get("gold_verdict") for p, r in zip(preds, gold_rows)) / len(gold_rows)
    # corrective-framed non-leak canary: precision proxy = FP rate on corrective safe items
    corr_safe = [(p, r) for p, r in zip(preds, gold_rows)
                 if r.get("gold_verdict") not in LEAK and CORR_RE.search(r.get("candidate_message") or "")]
    canary_fp = (sum(1 for p, r in corr_safe if p in LEAK) / len(corr_safe)) if corr_safe else 0.0
    return {"leak_p": prec, "leak_r": rec, "leak_f1": f1, "safety_binary": sb, "v5": v5,
            "canary_fp": canary_fp, "canary_n": len(corr_safe)}


def stage_d(eval_limit):
    gold = read_jsonl(FROZEN)
    if eval_limit:
        gold = gold[:eval_limit]
    print(f"[D] eval v9 live on {len(gold)} frozen items ...", file=sys.stderr)
    v9_res = eval_harness.evaluate(gold, eval_harness.mlx_runner(config.MODEL, V9_ADAPTER, 512))
    v9_pred = {d["id"]: d["pred"] for d in v9_res["per_item"]}
    v9_preds = [v9_pred.get(r["id"]) for r in gold]
    v9m = _metrics(v9_preds, gold)
    # v6 from stored per_item (thinking-off, v6 prompt) if present; else run live
    v6m = None
    if os.path.exists(PRIOR_RES):
        pr = json.load(open(PRIOR_RES))
        if "sft_v6" in pr:
            v6_pred = {d["id"]: d["pred"] for d in pr["sft_v6"]["per_item"]}
            if all(r["id"] in v6_pred for r in gold):
                v6m = _metrics([v6_pred.get(r["id"]) for r in gold], gold)
    if v6m is None:
        v6_res = eval_harness.evaluate(gold, eval_harness.mlx_runner(config.MODEL, "adapters/v6", 512))
        v6p = {d["id"]: d["pred"] for d in v6_res["per_item"]}
        v6m = _metrics([v6p.get(r["id"]) for r in gold], gold)

    accept = (v9m["leak_r"] > v6m["leak_r"] and v9m["safety_binary"] >= v6m["safety_binary"] - 0.005
              and v9m["canary_fp"] <= v6m["canary_fp"] + 0.02)
    L = ["# v9 (Tier-2 minimal-pair augmentation) vs v6 — frozen set", "",
         f"n={len(gold)} | added {len(read_jsonl(TRAIN_ADD)) if os.path.exists(TRAIN_ADD) else 0} training rows", "",
         "| metric | v6 | v9 | Δ |", "|---|---|---|---|",
         f"| leak recall | {v6m['leak_r']:.1%} | {v9m['leak_r']:.1%} | {v9m['leak_r']-v6m['leak_r']:+.1%} |",
         f"| leak precision | {v6m['leak_p']:.1%} | {v9m['leak_p']:.1%} | {v9m['leak_p']-v6m['leak_p']:+.1%} |",
         f"| leak F1 | {v6m['leak_f1']:.1%} | {v9m['leak_f1']:.1%} | {v9m['leak_f1']-v6m['leak_f1']:+.1%} |",
         f"| safety-binary | {v6m['safety_binary']:.1%} | {v9m['safety_binary']:.1%} | {v9m['safety_binary']-v6m['safety_binary']:+.1%} |",
         f"| 5-way | {v6m['v5']:.1%} | {v9m['v5']:.1%} | {v9m['v5']-v6m['v5']:+.1%} |",
         f"| canary FP (corrective-safe, n={v9m['canary_n']}) | {v6m['canary_fp']:.1%} | {v9m['canary_fp']:.1%} | {v9m['canary_fp']-v6m['canary_fp']:+.1%} |",
         "", f"**Verdict: {'ACCEPT v9' if accept else 'REVERT (v6 stays)'}** "
         f"— leak recall {'up' if v9m['leak_r']>v6m['leak_r'] else 'not up'}, "
         f"safety-binary {'held' if v9m['safety_binary']>=v6m['safety_binary']-0.005 else 'regressed'}, "
         f"canary {'ok' if v9m['canary_fp']<=v6m['canary_fp']+0.02 else 'regressed'}."]
    md = "\n".join(L) + "\n"
    with open(REPORT + ".md", "w") as f:
        f.write(md)
    json.dump({"v6": v6m, "v9": v9m, "accept": accept}, open(REPORT + ".json", "w"), indent=2)
    print(md)
    return accept


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=80)
    ap.add_argument("--iters", type=int, default=687)
    ap.add_argument("--eval-limit", type=int, default=0)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.smoke:
        a.seeds, a.iters, a.eval_limit = 3, 2, 8

    err = preflight()
    if err:
        print(f"[tier2] PREFLIGHT FAILED — gateway unusable: {err}", file=sys.stderr)
        return 3

    print("[tier2] STAGE A: generate matched pairs", file=sys.stderr)
    pairs = stage_a(a.seeds, a.force)
    if not pairs:
        print("[tier2] no pairs generated — abort", file=sys.stderr)
        return 1
    print("[tier2] STAGE B: cross-family jury validation + assemble", file=sys.stderr)
    add = stage_b(pairs, a.force)
    if not add:
        print("[tier2] no pairs survived validation — abort (regenerate with a better prompt)", file=sys.stderr)
        return 1
    print("[tier2] STAGE C: build v9 + train", file=sys.stderr)
    stage_c(add, a.iters, a.force)
    print("[tier2] STAGE D: eval v9 vs v6", file=sys.stderr)
    accept = stage_d(a.eval_limit)
    print(f"[tier2] DONE. accept={accept}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
