#!/usr/bin/env python3
"""Leak-recall check: do the TRAINING data's `mismatched_calibration` rows actually hand over the
key step (i.e., are they mislabeled leaks)? A cross-family jury (Claude + gpt-4o, blind, current
prompt) re-judges the mismatched-labeled training rows; we count how many BOTH independently call
a LEAK verdict (gives_away_key_step / gives_final_answer).

High agreement => the mismatched<->gives_away boundary is mislabeled in the training data, which is
why v6's leak recall is low, and a targeted cross-family relabel (v9) is the fix. Low agreement =>
the labels are fine and it's a model-capacity limit (favor a prompt/threshold lever instead).

Cross-family (not gpt-5.5 alone) applies the v7-audit lesson: same-model agreement != correctness.

Usage: python scripts/check_mismatched_leaks.py --limit 100
"""

import argparse
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from socratic_tutor.io_utils import read_jsonl  # noqa: E402
from socratic_tutor.prompts import SYSTEM_PROMPT, build_user_prompt  # noqa: E402
from socratic_tutor.schema import VERDICTS, parse_model_json  # noqa: E402
from gen_lib import passes_quality_gate  # noqa: E402

SRC = "data/raw/v6_consensus.jsonl"
LEAK = {"gives_final_answer", "gives_away_key_step"}
ARBITERS = {"claude": "claude-group/claude-opus-4-8", "gpt4o": "openai-group/gpt-4o"}


def _input(row):
    return {k: row.get(k) for k in ("problem", "correct_solution", "conversation_history", "candidate_message")}


def blind(model, rows):
    from openai import OpenAI
    c = OpenAI(timeout=90, max_retries=4)

    def one(row):
        msgs = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(_input(row))}]
        for kw in ({"temperature": 0}, {}):
            try:
                r = c.chat.completions.create(model=model, messages=msgs, **kw)
                v = (parse_model_json(r.choices[0].message.content or "") or {}).get("verdict")
                if v in VERDICTS:
                    return v
            except Exception:  # noqa: BLE001
                continue
        return None

    with ThreadPoolExecutor(max_workers=6) as ex:
        out = list(ex.map(one, rows))
    print(f"[check] {model}: {sum(v is not None for v in out)}/{len(rows)} judged", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verdict", default="mismatched_calibration")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    rows = [r for r in read_jsonl(SRC) if r.get("verdict") == a.verdict and passes_quality_gate(r)[0]]
    if a.limit:
        rows = rows[:a.limit]
    print(f"[check] {len(rows)} training rows labeled '{a.verdict}'; cross-family jury re-judging blind ...",
          file=sys.stderr)

    cl = blind(ARBITERS["claude"], rows)
    gp = blind(ARBITERS["gpt4o"], rows)

    both_leak = both_giveaway = agree_recall = 0
    examples = []
    for row, c, g in zip(rows, cl, gp):
        if c in LEAK and g in LEAK:
            both_leak += 1
            if c == "gives_away_key_step" and g == "gives_away_key_step":
                both_giveaway += 1
            if len(examples) < 6:
                examples.append((row["id"], c, g, (row.get("candidate_message") or "")[:200]))
    n = len(rows)
    print(f"\n[check] of {n} '{a.verdict}' training rows, BOTH jurors call it a LEAK: "
          f"{both_leak} ({both_leak/n:.0%})  [both say gives_away_key_step: {both_giveaway}]")
    print(f"[check] claude dist: {dict(Counter(cl))}")
    print(f"[check] gpt4o  dist: {dict(Counter(gp))}")
    print("\n=== examples both jurors flag as a LEAK (labeled mismatched, but hands over the key step) ===")
    for i, c, g, cand in examples:
        print(f"[{i}] claude={c} gpt4o={g}\n   {cand}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
