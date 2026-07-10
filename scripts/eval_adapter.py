#!/usr/bin/env python3
"""Eval ANY adapter on the frozen set; print the safety-axis + standard metrics and Δ vs v6 (1.7B).

For the Qwen3-4B scale test (docs/scale_test_qwen3_4b.md) and one-off adapter evals. Set config.MODEL
to the base the adapter was trained on (e.g. mlx-community/Qwen3-4B-4bit) before running; for a
thinking-trained adapter set config.ENABLE_THINKING=True and pass --max-tokens 1024.

Usage:
  python scripts/eval_adapter.py --adapter adapters/v6-4b --tag v6-4b
  python scripts/eval_adapter.py --adapter adapters/v8-4b --tag v8-4b --max-tokens 1024
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl  # noqa: E402
import eval_harness  # noqa: E402

FROZEN = str(config.GOLD_DIR / "frozen_eval.jsonl")
PRIOR = "eval/results/v8_frozen.json"  # stored sft_v6 (1.7B) per_item for the Δ baseline
LEAK = {"gives_final_answer", "gives_away_key_step"}


def _metrics(preds, gold_rows):
    gl = [r.get("gold_verdict") in LEAK for r in gold_rows]
    pl = [p in LEAK for p in preds]
    tp = sum(1 for p, g in zip(pl, gl) if p and g)
    fp = sum(1 for p, g in zip(pl, gl) if p and not g)
    fn = sum(1 for p, g in zip(pl, gl) if not p and g)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    sb = sum((p in LEAK) == (r.get("gold_verdict") in LEAK) for p, r in zip(preds, gold_rows)) / len(gold_rows)
    v5 = sum(p == r.get("gold_verdict") for p, r in zip(preds, gold_rows)) / len(gold_rows)
    return {"leak_p": prec, "leak_r": rec, "leak_f1": f1, "safety_binary": sb, "v5": v5}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--max-tokens", type=int, default=512)
    a = ap.parse_args()

    gold = read_jsonl(FROZEN)
    print(f"[eval] {a.tag}: {config.MODEL} + {a.adapter} on {len(gold)} frozen items "
          f"(thinking={config.ENABLE_THINKING}, max_tokens={a.max_tokens}) ...", file=sys.stderr)
    res = eval_harness.evaluate(gold, eval_harness.mlx_runner(config.MODEL, a.adapter, a.max_tokens))
    pred = {d["id"]: d["pred"] for d in res["per_item"]}
    m = _metrics([pred.get(r["id"]) for r in gold], gold)

    base = None
    if os.path.exists(PRIOR):
        pr = json.load(open(PRIOR))
        if "sft_v6" in pr:
            p6 = {d["id"]: d["pred"] for d in pr["sft_v6"]["per_item"]}
            if all(r["id"] in p6 for r in gold):
                base = _metrics([p6.get(r["id"]) for r in gold], gold)

    L = [f"# {a.tag} vs v6 (1.7B) — frozen n={len(gold)} | base={config.MODEL}", "",
         f"| metric | v6 (1.7B) | {a.tag} | Δ |", "|---|---|---|---|"]
    for k, label in (("leak_r", "leak recall"), ("leak_p", "leak precision"), ("leak_f1", "leak F1"),
                     ("safety_binary", "safety-binary"), ("v5", "5-way")):
        if base:
            L.append(f"| {label} | {base[k]:.1%} | {m[k]:.1%} | {m[k]-base[k]:+.1%} |")
        else:
            L.append(f"| {label} | ? | {m[k]:.1%} | |")
    md = "\n".join(L) + "\n"
    out = f"eval/results/{a.tag}_frozen"
    with open(out + ".md", "w") as f:
        f.write(md)
    json.dump({"model": config.MODEL, "adapter": a.adapter, "metrics": m, "v6_1p7b": base},
              open(out + ".json", "w"), indent=2)
    print(md)
    print(f"[eval] wrote {out}.md / .json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
