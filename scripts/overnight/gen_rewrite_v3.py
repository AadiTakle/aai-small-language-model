"""Generate rewrite_v3 targets: a STRICT "never name the operation" teacher (gpt-5.6), anchored on
the human curations, with EVERY generated target validated against the broad LLM leak-detector —
leaky targets get one stricter retry, then are dropped. This fixes rewrite_v2's operation-naming
leaks at the source: rewrite_v3 only ever trains on targets that are clean by the metric that
matters (broad = answer OR key-step/operation).

Output: data/raw/rewrite_train_v3.jsonl  (human curations kept as-is + validated strict targets).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from overnight.curate_regen import STYLE_GUIDE, exemplars_block  # noqa: E402
from overnight.split_common import (  # noqa: E402
    FRONTIER, REWRITE_SYSTEM, build_rewrite_user_prompt, clean_hint, gate_chat, input_dict,
    llm_leaks, parallel_map,
)

CTX_KEYS = ("id", "source", "problem", "correct_solution", "final_answer", "key_step",
            "conversation_history", "candidate_message", "verdict", "reason")

STRICT_RULE = """
CRITICAL HARD RULE (this is what makes a rewrite pass or fail):
- NEVER name the operation, the arithmetic, or the pivotal step. Do NOT write "what is 80 divided by
  4?", "add 8 and 5", "substitute 2x+1 for y", or give a worked/isomorphic example.
- Instead ask about the student's OWN reasoning or the problem's STRUCTURE, and let the STUDENT choose
  the operation: "what do you get when you do that?", "how could you combine these two amounts?",
  "which quantities does the problem relate, and how?".
- Naming the operation hands over the key step and FAILS. Stay a genuine question, not a disguised instruction."""


def gen_one(ctx, teacher, system, max_retry=1):
    inp = input_dict(ctx)
    v, r = ctx.get("verdict") or "", ctx.get("reason") or ""
    hint = clean_hint(gate_chat(teacher, system, build_rewrite_user_prompt(inp, v, r), temp=0.4))
    tries = 0
    while hint and llm_leaks(hint, ctx) and tries < max_retry:
        strict_u = build_rewrite_user_prompt(
            inp, v, (r + " Your previous attempt LEAKED by naming the operation/answer. Do NOT name "
                     "the operation or arithmetic; ask about the student's reasoning instead.").strip())
        hint = clean_hint(gate_chat(teacher, system, strict_u, temp=0.2))
        tries += 1
    if not (hint and hint.strip()) or llm_leaks(hint, ctx):
        return None  # still leaks after retry -> drop (clean targets only)
    return hint


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contexts", default="data/raw/rewrite_train.jsonl")  # has candidates + synthesized gsm8k
    ap.add_argument("--human", default="data/raw/human_rewrites.jsonl")
    ap.add_argument("--out", default="data/raw/rewrite_train_v3.jsonl")
    ap.add_argument("--teacher", default="gpt-5.6")
    ap.add_argument("--chunk", type=int, default=150)
    ap.add_argument("--limit", type=int, default=0, help="smoke: cap contexts")
    a = ap.parse_args()

    contexts = read_jsonl(a.contexts)
    if a.limit:
        contexts = contexts[:a.limit]
    human = read_jsonl(a.human)
    human_by_id = {r.get("id"): r for r in human}
    system = REWRITE_SYSTEM + "\n\n" + STYLE_GUIDE + STRICT_RULE + "\n\n" + exemplars_block(human)
    mid = FRONTIER[a.teacher]

    rows = []
    for c in contexts:
        if c.get("id") in human_by_id:
            hr = human_by_id[c["id"]]
            rows.append({**{k: c.get(k) for k in CTX_KEYS}, "target_rewrite": hr.get("rewrite"),
                         "teacher": a.teacher, "curated_by": "human"})
    todo = [c for c in contexts if c.get("id") not in human_by_id]
    print(f"[v3] contexts={len(contexts)} human-gold={len([r for r in rows])} to-generate={len(todo)} "
          f"| strict teacher={a.teacher} + broad-detector validation", file=sys.stderr)

    kept, dropped = len(rows), 0
    for i in range(0, len(todo), a.chunk):
        part = todo[i:i + a.chunk]
        hints = parallel_map(lambda c: gen_one(c, mid, system), part, workers=6)
        for c, h in zip(part, hints):
            if not h:
                dropped += 1
                continue
            rows.append({**{k: c.get(k) for k in CTX_KEYS}, "target_rewrite": h,
                         "teacher": f"{a.teacher}-strict", "curated_by": "gpt5.6-strict-validated"})
            kept += 1
        write_jsonl(a.out, rows)  # checkpoint
        print(f"[v3]   {min(i + a.chunk, len(todo))}/{len(todo)}  kept={kept} dropped(leaky)={dropped}",
              file=sys.stderr, flush=True)

    print(f"[v3] DONE {len(rows)} rows ({len(human_by_id)} human + {kept - len(human_by_id)} strict-validated, "
          f"{dropped} dropped as leaky) -> {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
