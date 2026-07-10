#!/usr/bin/env python3
"""Tier-1 leak-recall experiment: self-consistency vote-count threshold sweep on v6 (NO retraining).

Draws v6's leak-detection precision/recall CURVE by sampling k completions at temp>0 and predicting
"leak" when >= m of k samples say leak (m=1 = OR = max recall ... m=k = unanimous = max precision).
If recall reaches ~70% at acceptable precision, leak recall is a tunable THRESHOLD problem (a free,
shippable inference-time win); if the curve stays flat/low, the miss is SYSTEMATIC -> needs targeted
data (Tier 2). Baseline = greedy (temp=0) = v6's current shipped behavior (should reproduce ~60% R).

Usage: python scripts/eval_self_consistency.py --k 5 --temp 0.7 [--limit N]
"""

import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl  # noqa: E402
from socratic_tutor.prompts import build_inference_prompt  # noqa: E402
from socratic_tutor.schema import parse_model_json  # noqa: E402

LEAK = {"gives_final_answer", "gives_away_key_step"}
FROZEN = str(config.GOLD_DIR / "frozen_eval.jsonl")
OUT = str(config.RESULTS_DIR / "v6_self_consistency")


def _input(row):
    return {k: row.get(k) for k in ("problem", "correct_solution", "conversation_history", "candidate_message")}


def _agg_verdict(samples, m):
    """Aggregate k sample-verdicts at leak-vote threshold m: >=m leak votes -> leak (majority leak
    type, tie -> gives_away_key_step, the harder-to-catch one); else majority among the non-leak samples."""
    leaks = [s for s in samples if s in LEAK]
    if len(leaks) >= m:
        c = Counter(leaks)
        return max(c.items(), key=lambda kv: (kv[1], kv[0] == "gives_away_key_step"))[0]
    nonleak = [s for s in samples if s and s not in LEAK]
    if nonleak:
        return Counter(nonleak).most_common(1)[0][0]
    valid = [s for s in samples if s]
    return Counter(valid).most_common(1)[0][0] if valid else None


def _prf(pred_leak, gold_leak):
    tp = sum(1 for p, g in zip(pred_leak, gold_leak) if p and g)
    fp = sum(1 for p, g in zip(pred_leak, gold_leak) if p and not g)
    fn = sum(1 for p, g in zip(pred_leak, gold_leak) if not p and g)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return prec, rec, f1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adapter", default="adapters/v6")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--temp", type=float, default=0.7)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=512)
    a = ap.parse_args()

    from mlx_lm import generate, load
    from mlx_lm.sample_utils import make_sampler

    gold = read_jsonl(FROZEN)
    if a.limit:
        gold = gold[:a.limit]
    model, tok = load(config.MODEL, adapter_path=a.adapter)
    greedy = make_sampler(temp=0.0)
    sampler = make_sampler(temp=a.temp)

    def one(inp, samp):
        out = generate(model, tok, prompt=build_inference_prompt(tok, inp),
                       max_tokens=a.max_tokens, sampler=samp, verbose=False)
        return (parse_model_json(out) or {}).get("verdict")

    rows = []
    for i, row in enumerate(gold, 1):
        inp = _input(row)
        gd = one(inp, greedy)
        ss = [one(inp, sampler) for _ in range(a.k)]
        rows.append({"id": row.get("id"), "gold": row.get("gold_verdict"), "greedy": gd, "samples": ss})
        if i % 20 == 0 or i == len(gold):
            print(f"[sc] {i}/{len(gold)}", file=sys.stderr, flush=True)

    gold_leak = [r["gold"] in LEAK for r in rows]
    n = len(rows)

    def report_row(label, preds):
        pred_leak = [p in LEAK for p in preds]
        p, r, f = _prf(pred_leak, gold_leak)
        sb = sum((pr in LEAK) == (rw["gold"] in LEAK) for pr, rw in zip(preds, rows)) / n
        v5 = sum(pr == rw["gold"] for pr, rw in zip(preds, rows)) / n
        return f"| {label} | {p:.1%} | {r:.1%} | {f:.1%} | {sb:.1%} | {v5:.1%} |"

    L = ["# v6 self-consistency leak-recall sweep (no retraining)", "",
         f"n={n} | k={a.k} @ temp={a.temp} | adapter={a.adapter} | thinking={config.ENABLE_THINKING}", "",
         "vote>=m/k: predict LEAK if at least m of k samples say leak (m=1 = OR = max recall).", "",
         "| setting | leak P | leak R | leak F1 | safety-binary | 5-way |", "|---|---|---|---|---|---|"]
    L.append(report_row("greedy (baseline = v6)", [r["greedy"] for r in rows]))
    for m in range(1, a.k + 1):
        L.append(report_row(f"vote>={m}/{a.k}", [_agg_verdict(r["samples"], m) for r in rows]))
    md = "\n".join(L) + "\n"
    with open(OUT + ".md", "w") as f:
        f.write(md)
    json.dump(rows, open(OUT + ".json", "w"), indent=2)
    print(md)
    print(f"[sc] wrote {OUT}.md / .json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
