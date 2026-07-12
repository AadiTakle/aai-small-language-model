"""Phase 4a: synthesize leak/safe minimal PAIRS straddling the boundary, from gold train contexts
(gpt-5.6), each validated by the SHARPENED detector. Each pair for one context:
  - leaky : a tutor message that HANDS OVER the key step/operation (must trip llm_leaks_sharp)
  - safe  : a Socratic hint nudging toward the SAME step via a question (must pass llm_leaks_sharp)
Feeds the judge (leaky -> gives_away_key_step, safe -> adequate) and the rewrite model
(leaky flagged -> safe target). Output: data/raw/boundary_pairs.jsonl.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.schema import parse_model_json  # noqa: E402
from overnight.split_common import gate_chat, input_dict, llm_leaks_sharp, parallel_map  # noqa: E402

GEN_SYS = """You generate a MATCHED PAIR of tutor messages for a K-12 math problem the student is \
STILL solving. The pair teaches a judge the exact line between leaking the solution and not.

Given the problem, its solution (reference only), the key step, and the conversation, return JSON:
- "leaky": a tutor message that HANDS OVER the single key step/operation that makes the rest trivial \
(tells the student the specific next move to make), WITHOUT stating the final numeric answer.
- "safe": a Socratic hint that nudges the student toward the SAME step via ONE guiding question, \
WITHOUT naming the operation/step and WITHOUT directly correcting them.

Both one or two sentences, grounded in the student's latest message. The two must differ ONLY in \
whether they hand over the step. Return ONLY {"leaky": "...", "safe": "..."} and nothing else."""

GEN_MODEL = "openai-group/gpt-5.6-sol"


def gen_pair(row):
    inp = input_dict(row)
    hist = "\n".join(f"- {h}" for h in (inp["conversation_history"] or [])) or "(none yet)"
    user = (
        f"PROBLEM:\n{inp['problem']}\n\n"
        f"CORRECT SOLUTION (reference only — never reveal):\n{inp['correct_solution']}\n\n"
        f"KEY STEP (the pivotal move the student must make):\n{row.get('key_step','')}\n\n"
        f"CONVERSATION SO FAR:\n{hist}\n\n"
        "Return the JSON pair now."
    )
    o = parse_model_json(gate_chat(GEN_MODEL, GEN_SYS, user, temp=0.7)) or {}
    leaky = (o.get("leaky") or "").strip()
    safe = (o.get("safe") or "").strip()
    if not (leaky and safe):
        return None
    # sharp-validate the pair: the leaky one MUST leak, the safe one MUST NOT
    if not llm_leaks_sharp(leaky, row):
        return None
    if llm_leaks_sharp(safe, row):
        return None
    keep = {k: row.get(k) for k in
            ("id", "problem", "correct_solution", "conversation_history", "final_answer", "key_step", "source")}
    return {**keep, "leaky_candidate": leaky, "safe_rewrite": safe}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contexts", default="data/raw/rewrite_contexts_train.jsonl")
    ap.add_argument("--pool", type=int, default=800, help="max contexts to attempt")
    ap.add_argument("--n-target", type=int, default=450, help="stop once this many validated pairs")
    ap.add_argument("--out", default="data/raw/boundary_pairs.jsonl")
    a = ap.parse_args()

    rows = read_jsonl(a.contexts)[:a.pool]
    print(f"[boundary] generating pairs on {len(rows)} contexts (target {a.n_target} validated) ...",
          file=sys.stderr, flush=True)
    got = [p for p in parallel_map(gen_pair, rows, workers=6) if p]
    got = got[:a.n_target]
    write_jsonl(a.out, got)
    print(f"[boundary] wrote {len(got)} validated leak/safe pairs -> {a.out} "
          f"(from {len(rows)} contexts, {100*len(got)//max(1,len(rows))}% yield)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
