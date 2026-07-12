"""Phase 4b: dataset-growth vs performance. Grow the rewrite + judge training sets with boundary
minimal-pairs (from gen_boundary) in steps, retrain from the base each time (~2 epochs, fixed
recipe), and measure. Saves boundary_scaling.json after EVERY point (crash-safe — partial curves
still plot).

  rewrite: base rewrite_train_v4 + N boundary (leaky->safe) rows; metric = SHARP leak on held-out 60.
  judge:   base v9b verdict rows + 2N boundary (leaky->gives_away, safe->adequate); metric = leak
           recall + safety-binary on the frozen verdict set.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.schema import parse_model_json  # noqa: E402
from overnight.split_common import (  # noqa: E402
    LEAK, input_dict, infer_verdict_prompt, llm_leaks, llm_leaks_sharp,
)
from overnight.eval_rewrite import mlx_hints

STEPS = [0, 50, 100, 200, 400]
WORK = REPO / "data" / "boundary"
ADP = REPO / "adapters" / "boundary"
WORK.mkdir(parents=True, exist_ok=True)
ADP.mkdir(parents=True, exist_ok=True)
OUT = REPO / "eval" / "results" / "overnight" / "boundary_scaling.json"
RESULTS = {"rewrite": [], "judge": [], "meta": {"steps": STEPS}}


def log(msg):
    print(f"[scale] {msg}", file=sys.stderr, flush=True)


def save():
    OUT.write_text(json.dumps(RESULTS, indent=2), encoding="utf-8")


def render(task, src, out_dir):
    r = subprocess.run(
        [".venv/bin/python", "scripts/overnight/render_split.py", "--task", task,
         "--src", str(src), "--out-dir", str(out_dir)],
        cwd=str(REPO), capture_output=True, text=True)
    if r.returncode != 0:
        log(f"render FAILED ({task}): {r.stderr[-300:]}")
        return False
    return True


def train(data_dir, adapter, iters, logfile):
    with open(logfile, "w") as lf:
        r = subprocess.run(
            [".venv/bin/python", "-m", "mlx_lm", "lora", "--train", "--model", config.MODEL,
             "--data", str(data_dir), "--adapter-path", str(adapter),
             "-c", "configs/lora_v1.yaml", "--iters", str(iters)],
            cwd=str(REPO), stdout=lf, stderr=subprocess.STDOUT)
    return r.returncode == 0


def iters_for(mlx_dir):
    n = sum(1 for _ in open(Path(mlx_dir) / "train.jsonl"))
    return min(700, max(120, int(n * 0.5)))  # ~2 epochs, bounded


# --------------------------------------------------------------------------- #
# rewrite scaling
# --------------------------------------------------------------------------- #
def rewrite_row(p):
    return {"id": f"{p['id']}-bnd", "problem": p["problem"], "correct_solution": p["correct_solution"],
            "conversation_history": p["conversation_history"], "final_answer": p.get("final_answer", ""),
            "key_step": p.get("key_step", ""), "source": "boundary", "verdict": "gives_away_key_step",
            "reason": "hands over the key step the student still needs to find",
            "candidate_message": p["leaky_candidate"], "target_rewrite": p["safe_rewrite"]}


def measure_rewrite(adapter, ctxs):
    hints = mlx_hints(str(adapter), ctxs)
    hs = [(c, hints.get(c["id"], "")) for c in ctxs]
    n = len(ctxs)
    sharp = sum(1 for c, h in hs if h and llm_leaks_sharp(h, c)) / n
    broad = sum(1 for c, h in hs if h and llm_leaks(h, c)) / n
    return {"sharp_leak": round(sharp, 3), "broad_leak": round(broad, 3)}


def scale_rewrite(pairs, base, heldout):
    log(f"REWRITE scaling: base={len(base)} rows, held-out={len(heldout)}")
    for N in STEPS:
        try:
            combined = base + [rewrite_row(p) for p in pairs[:N]]
            src = WORK / f"rw_b{N}.jsonl"
            write_jsonl(src, combined)
            mlx_dir = WORK / f"mlx_rw_b{N}"
            if not render("rewrite", src, mlx_dir):
                continue
            it = iters_for(mlx_dir)
            adapter = ADP / f"rw_b{N}"
            log(f"  N={N}: {len(combined)} rows, {it} iters -> train")
            if not train(mlx_dir, adapter, it, WORK / f"rw_b{N}.log"):
                log(f"  N={N}: train FAILED"); continue
            m = measure_rewrite(adapter, heldout)
            RESULTS["rewrite"].append({"added": N, "total": len(combined), **m})
            log(f"  N={N}: sharp_leak={m['sharp_leak']:.1%} broad_leak={m['broad_leak']:.1%}")
            save()
        except Exception as e:  # noqa: BLE001
            log(f"  N={N}: ERROR {type(e).__name__}: {e}")


# --------------------------------------------------------------------------- #
# judge scaling
# --------------------------------------------------------------------------- #
def judge_rows(p):
    base = {"problem": p["problem"], "correct_solution": p["correct_solution"],
            "conversation_history": p["conversation_history"], "final_answer": p.get("final_answer", ""),
            "key_step": p.get("key_step", "")}
    leaky = {**base, "id": f"{p['id']}-bl", "candidate_message": p["leaky_candidate"],
             "verdict": "gives_away_key_step",
             "reasoning": "states the key step/operation the student still needs to discover"}
    safe = {**base, "id": f"{p['id']}-bs", "candidate_message": p["safe_rewrite"], "verdict": "adequate",
            "reasoning": "guides toward the step with a question without handing it over"}
    return [leaky, safe]


def measure_judge(adapter, frozen):
    from mlx_lm import generate, load
    from mlx_lm.sample_utils import make_sampler
    model, tok = load(config.MODEL, adapter_path=str(adapter))
    sampler = make_sampler(temp=0.0)
    tp = fp = tn = fn = 0
    for r in frozen:
        try:
            prompt = infer_verdict_prompt(tok, input_dict(r))
            raw = generate(model, tok, prompt=prompt, max_tokens=128, sampler=sampler, verbose=False)
            pred = (parse_model_json(raw) or {}).get("verdict", "")
        except Exception:  # noqa: BLE001
            pred = ""
        gl = (r.get("gold_verdict") or r.get("verdict")) in LEAK
        pl = pred in LEAK
        tp += gl and pl
        fp += (not gl) and pl
        tn += (not gl) and (not pl)
        fn += gl and (not pl)
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    safety = (tp + tn) / max(1, tp + fp + tn + fn)
    return {"leak_recall": round(recall, 3), "safety_binary": round(safety, 3)}


def scale_judge(pairs, base, frozen):
    log(f"JUDGE scaling: base={len(base)} rows, frozen={len(frozen)}")
    for N in STEPS:
        try:
            add = [row for p in pairs[:N] for row in judge_rows(p)]
            combined = base + add
            src = WORK / f"jg_b{N}.jsonl"
            write_jsonl(src, combined)
            mlx_dir = WORK / f"mlx_jg_b{N}"
            if not render("verdict", src, mlx_dir):
                continue
            it = iters_for(mlx_dir)
            adapter = ADP / f"jg_b{N}"
            log(f"  N={N}: {len(combined)} rows ({len(add)} boundary), {it} iters -> train")
            if not train(mlx_dir, adapter, it, WORK / f"jg_b{N}.log"):
                log(f"  N={N}: train FAILED"); continue
            m = measure_judge(adapter, frozen)
            RESULTS["judge"].append({"added": N, "total": len(combined), **m})
            log(f"  N={N}: leak_recall={m['leak_recall']:.1%} safety={m['safety_binary']:.1%}")
            save()
        except Exception as e:  # noqa: BLE001
            log(f"  N={N}: ERROR {type(e).__name__}: {e}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairs", default="data/raw/boundary_pairs.jsonl")
    ap.add_argument("--rewrite-base", default="data/raw/rewrite_train_v4.jsonl")
    ap.add_argument("--judge-base", default="data/raw/v9b.jsonl")
    ap.add_argument("--heldout", default="data/raw/rewrite_contexts_eval.jsonl")
    ap.add_argument("--frozen", default="eval/gold/frozen_eval.jsonl")
    ap.add_argument("--only", default="both", choices=["both", "rewrite", "judge"])
    a = ap.parse_args()

    pairs = read_jsonl(a.pairs)
    log(f"loaded {len(pairs)} boundary pairs")
    save()  # write skeleton immediately
    if a.only in ("both", "rewrite"):
        scale_rewrite(pairs, read_jsonl(a.rewrite_base), read_jsonl(a.heldout))
    if a.only in ("both", "judge"):
        scale_judge(pairs, read_jsonl(a.judge_base), read_jsonl(a.frozen))
    save()
    log(f"done -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
