"""Regenerate the rest of the rewrite targets in the human-curated style (human-anchored distill).

The user reviewed a small set (data/raw/human_rewrites.jsonl) in the curation feed. Those become
(a) gold as-is and (b) few-shot exemplars + a distilled style guide that steer gpt-5.6 to rewrite
the remaining contexts to the same human standard — far faster than curating all ~1k by hand.

Output: data/raw/rewrite_train_curated.jsonl  (23 human golds + steered regenerations), same schema
as rewrite_train.jsonl (verdict / reason / target_rewrite), ready for render_split --task rewrite.

Usage:
  python scripts/overnight/curate_regen.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from overnight.split_common import (  # noqa: E402
    FRONTIER, REWRITE_SYSTEM, build_rewrite_user_prompt, clean_hint, gate_chat, input_dict,
    parallel_map, rewrite_leaks,
)

# Distilled from the human corrections (see analysis): the standard to hold gpt-5.6 to.
STYLE_GUIDE = """You are held to the standard of a set of HUMAN-CURATED rewrites. Match their voice and rules:
1. AFFIRM first — briefly acknowledge what the student got right ("Great intuition!", "You correctly
   found 40 weeks") in a warm, encouraging teacher voice, before guiding.
2. NEVER name the exact operation or arithmetic to perform. Refer to the step indirectly so the
   STUDENT chooses it: write "what do you get when you do that?" or "what is the discounted price?",
   NOT "what is 80 divided by 4?" or "what is 20 - 5?". Naming the operation hands over the key step.
3. If the student is off-track or miscalibrated, explicitly name WHERE the confusion is and point them
   to re-read or reconsider that specific part of the problem.
4. Ask exactly ONE guiding question. Never state the final answer.
5. Scaffold enough to genuinely help — a clear, well-scaffolded question beats a terse one.

Below are real human-approved rewrites. Produce a rewrite of the SAME quality and voice."""


def exemplars_block(gold_rows):
    lines = []
    for r in gold_rows:
        flagged = (r.get("candidate_message") or "")[:160]
        lines.append(f'- [{r.get("verdict")}] flagged: "{flagged}"\n  ideal rewrite: "{r.get("rewrite")}"')
    return "EXAMPLES (the standard to match):\n" + "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contexts", default="data/raw/rewrite_train.jsonl")
    ap.add_argument("--human", default="data/raw/human_rewrites.jsonl")
    ap.add_argument("--out", default="data/raw/rewrite_train_curated.jsonl")
    ap.add_argument("--teacher", default="gpt-5.6")
    ap.add_argument("--chunk", type=int, default=150)
    a = ap.parse_args()

    contexts = read_jsonl(a.contexts)
    human = read_jsonl(a.human)
    human_by_id = {r.get("id"): r for r in human}
    mid = FRONTIER[a.teacher]

    system = REWRITE_SYSTEM + "\n\n" + STYLE_GUIDE + "\n\n" + exemplars_block(human)

    todo = [c for c in contexts if c.get("id") not in human_by_id]
    print(f"[regen] contexts={len(contexts)} human-gold={len(human_by_id)} to-regenerate={len(todo)} "
          f"| teacher={a.teacher} | {len(human)} few-shot exemplars", file=sys.stderr)

    def regen(c):
        inp = input_dict(c)
        user = build_rewrite_user_prompt(inp, c.get("verdict") or "", c.get("reason") or "")
        hint = clean_hint(gate_chat(mid, system, user, temp=0.4))
        if hint and rewrite_leaks(hint, c):
            strict = user + "\n\nCRITICAL: do not name the final answer or the exact operation to perform."
            h2 = clean_hint(gate_chat(mid, system, strict, temp=0.2))
            hint = h2 or hint
        return hint

    # human golds first (as-is)
    rows = []
    for c in contexts:
        if c.get("id") in human_by_id:
            hr = human_by_id[c["id"]]
            rows.append({**{k: c.get(k) for k in ("id", "source", "problem", "correct_solution",
                        "final_answer", "key_step", "conversation_history", "candidate_message",
                        "verdict", "reason")},
                        "target_rewrite": hr.get("rewrite"), "teacher": a.teacher,
                        "curated_by": "human", "decision": hr.get("decision")})

    # steered regenerations (chunk-checkpointed)
    kept, dropped = len(rows), 0
    for i in range(0, len(todo), a.chunk):
        part = todo[i:i + a.chunk]
        hints = parallel_map(regen, part, workers=6)
        for c, h in zip(part, hints):
            if not (h and h.strip()) or rewrite_leaks(h, c):
                dropped += 1
                continue
            rows.append({**{k: c.get(k) for k in ("id", "source", "problem", "correct_solution",
                        "final_answer", "key_step", "conversation_history", "candidate_message",
                        "verdict", "reason")},
                        "target_rewrite": h.strip(), "teacher": a.teacher,
                        "curated_by": "gpt5.6-styled", "decision": None})
            kept += 1
        write_jsonl(a.out, rows)  # checkpoint
        print(f"[regen]   {min(i + a.chunk, len(todo))}/{len(todo)}  kept={kept} dropped={dropped}",
              file=sys.stderr, flush=True)

    print(f"[regen] DONE {len(rows)} rows ({len(human_by_id)} human + {kept - len(human_by_id)} styled, "
          f"{dropped} dropped) -> {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
