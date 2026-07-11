"""Task 1 eval: verdict performance on the frozen set for base / judge_v1 / v6 / frontier.

Each model uses its native prompt: base + judge_v1 + frontier get the verdict-only system
(VERDICT_SYSTEM); v6 gets the full combined system it was trained on (we read only its verdict).
Metrics: 5-way accuracy, safety-binary accuracy, and leak precision/recall/F1
(LEAK = {gives_final_answer, gives_away_key_step}) — the project's safety axis.

Usage:
  python scripts/overnight/eval_verdict.py --frontier opus-4.8,gpt-5.6 --out eval/results/overnight/verdict_eval
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl  # noqa: E402
from socratic_tutor.prompts import SYSTEM_PROMPT, build_inference_prompt, build_user_prompt  # noqa: E402
from socratic_tutor.schema import VERDICT_SET, parse_model_json  # noqa: E402
from overnight.split_common import (  # noqa: E402
    FRONTIER, LEAK, VERDICT_SYSTEM, gate_chat, infer_verdict_prompt, input_dict, parallel_map,
)


def extract_verdict(raw: str):
    o = parse_model_json(raw)
    if o and o.get("verdict") in VERDICT_SET:
        return o["verdict"]
    m = re.search(r'"verdict"\s*:\s*"([a-z_]+)"', raw or "")
    return m.group(1) if (m and m.group(1) in VERDICT_SET) else None


def metrics(preds: dict, gold: list) -> dict:
    n = len(gold)
    gl = [r.get("gold_verdict") in LEAK for r in gold]
    pl = [preds.get(r["id"]) in LEAK for r in gold]
    tp = sum(1 for p, g in zip(pl, gl) if p and g)
    fp = sum(1 for p, g in zip(pl, gl) if p and not g)
    fn = sum(1 for p, g in zip(pl, gl) if not p and g)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    sb = sum(1 for p, g in zip(pl, gl) if p == g) / n
    acc = sum(1 for r in gold if preds.get(r["id"]) == r.get("gold_verdict")) / n
    parsed = sum(1 for r in gold if preds.get(r["id"]) in VERDICT_SET) / n
    return {"acc5": acc, "safety_binary": sb, "leak_p": prec, "leak_r": rec, "leak_f1": f1,
            "parse_rate": parsed, "leak_fp": fp, "leak_fn": fn}


def mlx_preds(adapter, mode, gold, max_tokens):
    from mlx_lm import generate, load
    from mlx_lm.sample_utils import make_sampler
    model, tok = load(config.MODEL, adapter_path=adapter)
    sampler = make_sampler(temp=0.0)
    preds = {}
    for i, r in enumerate(gold, 1):
        inp = input_dict(r)
        prompt = infer_verdict_prompt(tok, inp) if mode == "verdict" else build_inference_prompt(tok, inp)
        raw = generate(model, tok, prompt=prompt, max_tokens=max_tokens, sampler=sampler, verbose=False)
        preds[r["id"]] = extract_verdict(raw)
        if i % 60 == 0:
            print(f"    ...{i}/{len(gold)}", file=sys.stderr, flush=True)
    return preds


def frontier_preds(model_id, gold):
    def one(r):
        return (r["id"], extract_verdict(gate_chat(model_id, VERDICT_SYSTEM, build_user_prompt(input_dict(r)))))
    return {k: v for k, v in parallel_map(one, gold, workers=6) if k}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frozen", default=str(config.GOLD_DIR / "frozen_eval.jsonl"))
    ap.add_argument("--out", default="eval/results/overnight/verdict_eval")
    ap.add_argument("--models", default="base,judge_v1,v6")
    ap.add_argument("--frontier", default="opus-4.8,gpt-5.6")
    a = ap.parse_args()

    gold = read_jsonl(a.frozen)
    print(f"[eval-verdict] frozen n={len(gold)}", file=sys.stderr)
    results = {}

    specs = {
        "base": (None, "verdict", 200),
        "judge_v1": ("adapters/judge_v1", "verdict", 200),
        "judge_full": ("adapters/judge_full", "verdict", 200),   # verdict-only, full natural-mix pool
        "combined_bal": ("adapters/combined_bal", "full", 160),  # combined objective, SAME balanced 725 (split isolation)
        "combined_full": ("adapters/combined_full", "full", 160),  # combined objective, natural-mix full pool
        "v6": ("adapters/v6", "full", 160),
    }
    for m in a.models.split(","):
        m = m.strip()
        if m not in specs:
            continue
        adapter, mode, mt = specs[m]
        if adapter and not (REPO / adapter).exists():
            print(f"[eval-verdict] SKIP {m}: {adapter} missing", file=sys.stderr)
            continue
        print(f"[eval-verdict] {m}: MLX ({adapter or 'base'}, {mode}, mt={mt}) ...", file=sys.stderr)
        results[m] = metrics(mlx_preds(adapter, mode, gold, mt), gold)

    for fk in [x.strip() for x in a.frontier.split(",") if x.strip()]:
        if fk not in FRONTIER:
            continue
        print(f"[eval-verdict] {fk}: frontier {FRONTIER[fk]} ...", file=sys.stderr)
        results[fk] = metrics(frontier_preds(FRONTIER[fk], gold), gold)

    pref = ["base", "judge_v1", "judge_full", "combined_bal", "combined_full", "v6"]
    order = [k for k in pref if k in results] + [k for k in results if k not in pref]
    L = [f"# Task 1 — verdict eval (frozen n={len(gold)}) | base={config.MODEL}", "",
         "| model | 5-way acc | safety-binary | leak recall | leak precision | leak F1 | parse |",
         "|---|---|---|---|---|---|---|"]
    for k in order:
        m = results[k]
        L.append(f"| {k} | {m['acc5']:.1%} | {m['safety_binary']:.1%} | {m['leak_r']:.1%} | "
                 f"{m['leak_p']:.1%} | {m['leak_f1']:.1%} | {m['parse_rate']:.0%} |")
    md = "\n".join(L) + "\n"
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out + ".md").write_text(md, encoding="utf-8")
    Path(a.out + ".json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(md)
    print(f"[eval-verdict] wrote {a.out}.md/.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
