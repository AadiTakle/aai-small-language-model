#!/usr/bin/env python3
"""v8: generate concise <think> reasoning traces (gpt-5.5) for each training row, to teach the
1.7B to reason-then-answer.

Distillation/rationalization: given the case + its CORRECT (v6) verdict, gpt-5.5 writes a few
sentences of first-person reasoning that work through the taxonomy and arrive at that verdict.
These become the <think> block of the v8 SFT targets (consumed by build_dataset.py --traces).
Traces are kept concise so think + JSON fit comfortably in the eval token budget.

Usage:
  python scripts/gen_think_traces.py               # -> data/raw/v8_traces.jsonl
  python scripts/gen_think_traces.py --limit 3     # smoke
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.prompts import build_user_prompt  # noqa: E402
from gen_lib import passes_quality_gate  # noqa: E402
from relabel_v7 import _client, _gate_call, preflight, _run_parallel  # noqa: E402  reuse gateway wrapper

SRC = "data/raw/v6_consensus.jsonl"
OUT = "data/raw/v8_traces.jsonl"

SYS = (
    "You produce a CONCISE step-by-step REASONING TRACE for a K-12 math-tutoring verdict — the "
    "private thinking a careful grader does before deciding. Write 3-6 first-person sentences that "
    "work through the case (what the student's latest message shows, what the candidate tutor "
    "message actually does, which taxonomy category that fits and why) and ARRIVE at the given "
    "verdict. Reason as if deriving it; do NOT say the verdict was provided. Output ONLY the "
    "reasoning prose — no JSON, no headings, no restating the answer verdict as a label."
)


def _input(row):
    return {k: row.get(k) for k in ("problem", "correct_solution", "conversation_history", "candidate_message")}


def gen(rows):
    client = _client()

    def one(row):
        user = (build_user_prompt(_input(row))
                + f"\n\nThe correct verdict for this candidate message is: {row.get('verdict')}.\n"
                  "Write the concise reasoning trace that leads to it.")
        txt = (_gate_call(client, SYS, user) or "").strip()
        # strip any stray think tags / code fences the model might add
        txt = txt.replace("<think>", "").replace("</think>", "").strip("`").strip()
        return txt if len(txt) >= 20 else None

    return _run_parallel(one, rows, "trace")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--limit", type=int, default=0, help="smoke: only N rows")
    a = ap.parse_args()

    err = preflight()
    if err:
        print(f"[traces] PREFLIGHT FAILED — gateway unusable: {err}", file=sys.stderr)
        return 3

    rows = [r for r in read_jsonl(a.src) if passes_quality_gate(r)[0]]
    if a.limit:
        rows = rows[:a.limit]
    print(f"[traces] generating reasoning traces for {len(rows)} gated rows via gpt-5.5 ...", file=sys.stderr)

    traces = gen(rows)
    out = [{"id": r["id"], "trace": t} for r, t in zip(rows, traces) if t]
    write_jsonl(a.out, out)
    print(f"[traces] wrote {len(out)}/{len(rows)} traces -> {a.out}", file=sys.stderr)
    if a.limit:
        for o in out[:3]:
            print(f"--- {o['id']} ---\n{o['trace'][:500]}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
