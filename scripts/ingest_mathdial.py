"""Ingest MathDial (real human teacher-student math dialogues) into our schema.

MathDial (Macina et al., 2023; CC-BY-4.0) tags every teacher turn with a pedagogical
move: probing / focus / telling / generic. We take the `probing` and `focus` turns —
genuine human Socratic scaffolding — as real `adequate` exemplars (verdict=adequate,
rewrite=null). These patch the over-flagging side of the adequate<->mismatched boundary
and give the model real "safe" tutor language. (telling/generic are coarse for our verdict
taxonomy, so we skip them here rather than inject label noise.)

Usage:
  python scripts/ingest_mathdial.py --dry
  python scripts/ingest_mathdial.py --annotate --cap 160 --out data/raw/real_mathdial.jsonl
"""

import argparse
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from socratic_tutor import annotate  # noqa: E402
from socratic_tutor.io_utils import write_jsonl  # noqa: E402
from socratic_tutor.schema import validate_output  # noqa: E402

SAFE_MOVES = {"probing", "focus"}


def final_answer(sol: str) -> str:
    nums = re.findall(r"-?\d[\d,]*(?:\.\d+)?", sol or "")
    return nums[-1].replace(",", "") if nums else ""


def parse_conversation(conv: str):
    """Return list of (role, move, text) turns."""
    turns = []
    for raw in (conv or "").split("|EOM|"):
        t = raw.strip()
        if t.startswith("Teacher:"):
            body = t[len("Teacher:"):].strip()
            m = re.match(r"\(([a-z]+)\)\s*(.*)", body, re.S)
            move, text = (m.group(1), m.group(2).strip()) if m else (None, body)
            turns.append(("Teacher", move, text))
        elif t.startswith("Student:"):
            turns.append(("Student", None, t[len("Student:"):].strip()))
    return turns


def build_rows(cap=None, annotate_reasoning=False, per_dialogue=2):
    from datasets import load_dataset

    ds = load_dataset("eth-nlped/mathdial", split="train")
    rows, by_move = [], Counter()
    for ex in ds:
        turns = parse_conversation(ex.get("conversation", ""))
        sol = ex.get("ground_truth", "")
        fa = final_answer(sol)
        taken = 0
        for i, (role, move, text) in enumerate(turns):
            if role != "Teacher" or move not in SAFE_MOVES:
                continue
            if i == 0 or len(text) < 25:  # need context; skip trivially short openers
                continue
            if taken >= per_dialogue:
                break
            history = [f"{r}: {tx}" for r, _, tx in turns[:i]]
            rows.append({
                "id": f"mathdial-{ex.get('qid')}-{i}",
                "problem": ex.get("question", ""), "correct_solution": sol,
                "final_answer": fa, "key_step": "", "conversation_history": history,
                "candidate_message": text, "verdict": "adequate", "reasoning": "",
                "rewritten_message": None, "source": "mathdial", "slice": "core",
            })
            by_move[move] += 1
            taken += 1
            if cap and len(rows) >= cap:
                break
        if cap and len(rows) >= cap:
            break

    if annotate_reasoning:
        for i, row in enumerate(rows, 1):
            r = annotate.write_reasoning(row["problem"], row["conversation_history"],
                                         row["candidate_message"], "adequate")
            row["reasoning"] = r or "Scaffolds with a guiding question grounded in the student's last turn without revealing the answer or key step."
            if i % 25 == 0 or i == len(rows):
                print(f"[mathdial] reasoning {i}/{len(rows)}", file=sys.stderr, flush=True)
    else:
        for row in rows:
            row["reasoning"] = "[placeholder-reasoning] adequate"
    return rows, by_move


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry", action="store_true")
    p.add_argument("--annotate", action="store_true")
    p.add_argument("--cap", type=int, default=160)
    p.add_argument("--out", default="data/raw/real_mathdial.jsonl")
    args = p.parse_args()

    rows, by_move = build_rows(cap=args.cap,
                               annotate_reasoning=(args.annotate and not args.dry))
    print(f"[mathdial] {len(rows)} adequate rows | by move: {dict(by_move)}", file=sys.stderr)
    if args.dry:
        for ex in rows[:3]:
            print("\n--- adequate ---")
            print("  history[-1]:", (ex["conversation_history"][-1] if ex["conversation_history"] else "")[:120])
            print("  candidate:", ex["candidate_message"][:160])
        return 0
    good = [r for r in rows if validate_output(
        {"verdict": r["verdict"], "reasoning": r["reasoning"],
         "rewritten_message": r["rewritten_message"]})[0]]
    write_jsonl(args.out, good)
    print(f"[mathdial] wrote {len(good)}/{len(rows)} -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
