#!/usr/bin/env python3
"""Structural rubric reframe (per docs/rubric_evaluation.md): re-score EXISTING frozen-set
predictions under a metric that separates the objective SAFETY axis (does the message leak?)
from the fuzzy QUALITY axis (adequate / mismatched_calibration / vague_unhelpful). No model
runs — pure re-scoring of stored predictions against the CURRENT frozen gold.

Per model:
  - verdict_5way : exact-match on the 5-way taxonomy (the OLD headline; penalized by the fuzzy axis)
  - verdict_3way : collapse the three quality verdicts -> SAFE, keep the two objective leak types
  - safety_binary: LEAK {gives_final_answer, gives_away_key_step} vs SAFE {the other three}
  - leak P/R/F1  : detecting LEAK as the positive class -- the safety-critical number for the product

Point: show whether the model learned the axis that MATTERS (catching leaks), which the 5-way
number understates. Predictions come with their original prompt provenance (v7 used the decision-
tree prompt; all others the v6 prompt) -- noted, since the reframe is a metric change, not a re-run.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl  # noqa: E402

FROZEN = str(config.GOLD_DIR / "frozen_eval.jsonl")
REPORT = "eval/results/report/final299"          # base, v2-v5, gpt4o, claude (raw {id,gold,pred})
FROZEN_RES = "eval/results/v8_frozen.json"        # sft_v6, v7, v8 per_item
OUT = "eval/results/rubric_reframe"
LEAK = {"gives_final_answer", "gives_away_key_step"}


def binary(v):
    return "leak" if v in LEAK else ("safe" if v else None)


def threeway(v):
    return v if v in LEAK else ("safe" if v else None)


def load_report(name):
    p = f"{REPORT}/{name}_items.json"
    if not os.path.exists(p):
        return None
    d = json.load(open(p))
    rows = d if isinstance(d, list) else (d.get("items") or d.get("per_item") or [])
    return {r["id"]: r.get("pred") for r in rows}


def load_frozen_res(tag):
    d = json.load(open(FROZEN_RES))
    return {r["id"]: r.get("pred") for r in d[tag]["per_item"]} if tag in d else None


def score(preds, gold):
    ids = [i for i in gold if i in preds]
    n = len(ids)
    v5 = sum(preds[i] == gold[i] for i in ids) / n
    v3 = sum(threeway(preds[i]) == threeway(gold[i]) for i in ids) / n
    sb = sum(binary(preds[i]) == binary(gold[i]) for i in ids) / n
    tp = sum(binary(gold[i]) == "leak" and binary(preds[i]) == "leak" for i in ids)
    fp = sum(binary(gold[i]) == "safe" and binary(preds[i]) == "leak" for i in ids)
    fn = sum(binary(gold[i]) == "leak" and binary(preds[i]) != "leak" for i in ids)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"n": n, "v5": v5, "v3": v3, "sb": sb, "leak_p": prec, "leak_r": rec, "leak_f1": f1}


def main():
    gold = {r["id"]: r.get("gold_verdict") for r in read_jsonl(FROZEN)}
    models = []
    for name in ("base", "v2", "v3", "v4", "v5"):
        p = load_report(name)
        if p:
            models.append((name, p))
    for tag, disp in (("sft_v6", "v6"), ("v7", "v7"), ("v8", "v8")):
        p = load_frozen_res(tag)
        if p:
            models.append((disp, p))
    for name in ("gpt4o", "claude"):
        p = load_report(name)
        if p:
            models.append((name, p))

    rows = [(disp, score(p, gold)) for disp, p in models]
    L = ["# Rubric reframe — safety-axis metrics on the frozen set (re-scored, no model runs)", "",
         "LEAK = {gives_final_answer, gives_away_key_step}; SAFE = {adequate, mismatched_calibration, "
         "vague_unhelpful}. **3-way** collapses the fuzzy quality axis into SAFE; **safety binary** + "
         "**leak F1** are the objective safety numbers (leak = positive class).", "",
         "| model | n | 5-way acc (old) | 3-way acc | safety binary | leak P | leak R | leak F1 |",
         "|---|---|---|---|---|---|---|---|"]
    for disp, s in rows:
        L.append(f"| {disp} | {s['n']} | {s['v5']:.1%} | {s['v3']:.1%} | {s['sb']:.1%} | "
                 f"{s['leak_p']:.1%} | {s['leak_r']:.1%} | {s['leak_f1']:.1%} |")
    md = "\n".join(L) + "\n"
    with open(OUT + ".md", "w") as f:
        f.write(md)
    json.dump({disp: s for disp, s in rows}, open(OUT + ".json", "w"), indent=2)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
