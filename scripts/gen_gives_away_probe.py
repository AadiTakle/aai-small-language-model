"""Generate a small, clearly-labeled SYNTHETIC held-out probe for the gives_away_key_step
category (which no clean human-labeled source covers). gpt-4.1 fabricates diverse K-12
scenarios where the candidate tutor message hands over the KEY STEP. Output is a gold set
(gold_verdict = gives_away_key_step) with a safe reference rewrite.

This is self-authored test data — weaker evidence than the human-labeled frozen set; the
report labels it as such. A leakage check confirms none of it appears in training.

Usage: python scripts/gen_gives_away_probe.py --n 20 --out eval/gold/gives_away_probe.jsonl
"""

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402

BANDS = ["K-2", "3-5", "6-8", "9-12"]
TRAIN_FILES = ["data/raw/all.jsonl", "data/raw/v3.jsonl", "data/raw/v4.jsonl",
               "data/raw/real_mrbench.jsonl", "data/mlx/train.jsonl"]

SYS = (
    "You create evaluation items for a math-tutoring judge. Produce ONE realistic K-12 math "
    "tutoring scenario in which the CANDIDATE tutor message commits the 'gives_away_key_step' "
    "failure: it does NOT state the final numeric answer, but it hands over the single "
    "insight/technique/operation-choice that makes the rest trivial (e.g. names the operation, "
    "performs the pivotal decomposition, or gives a worked isomorphic step). "
    'Return ONLY JSON: {"problem","correct_solution","final_answer","key_step",'
    '"conversation_history":["Student: ...","Tutor: ...", "..."],"candidate_message",'
    '"gold_rewrite","gold_reasoning"}. '
    "gold_rewrite must be a SAFE Socratic hint that does NOT leak the answer or key step. "
    "gold_reasoning must cite the specific phrase in candidate_message that leaks the key step."
)


def gen_one(client, band):
    delays = [2, 5, 10, 20, 40]
    waited = 0.0
    for i in range(len(delays) + 1):
        try:
            r = client.chat.completions.create(
                model=os.environ.get("OPENAI_JUDGE_MODEL", "gpt-4.1"), temperature=0.7,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": SYS},
                          {"role": "user", "content": f"Grade band: {band}. Make the math appropriate for {band}."}])
            return json.loads(r.choices[0].message.content)
        except Exception:
            if i >= len(delays) or waited >= 120:
                return None
            time.sleep(delays[i]); waited += delays[i]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--out", default="eval/gold/gives_away_probe.jsonl")
    a = ap.parse_args()
    from openai import OpenAI
    client = OpenAI()

    rows = []
    for i in range(a.n):
        band = BANDS[i % len(BANDS)]
        d = gen_one(client, band)
        if not d or not d.get("candidate_message"):
            continue
        rows.append({
            "id": f"probe-gak-{band}-{i:02d}", "problem": d.get("problem", ""),
            "correct_solution": d.get("correct_solution", ""), "final_answer": str(d.get("final_answer", "")),
            "key_step": d.get("key_step", ""), "conversation_history": d.get("conversation_history") or [],
            "candidate_message": d.get("candidate_message", ""), "gold_verdict": "gives_away_key_step",
            "gold_reasoning": d.get("gold_reasoning", ""), "gold_rewrite": d.get("gold_rewrite", ""),
            "slice": "synthetic_gives_away", "source": "synthetic-probe",
        })
        print(f"[probe] {len(rows)} generated ({band})", file=sys.stderr, flush=True)

    # leakage check vs training
    blob = ""
    for f in TRAIN_FILES:
        if os.path.exists(f):
            blob += "\n".join(json.dumps(x) for x in read_jsonl(f))
    leaked = [r["id"] for r in rows if r["candidate_message"].strip() and r["candidate_message"].strip() in blob]
    rows = [r for r in rows if r["id"] not in set(leaked)]

    write_jsonl(a.out, rows)
    # gold-stripped inputs (so subagent harnesses can't see the label)
    write_jsonl(a.out.replace(".jsonl", "_inputs.jsonl"),
                [{k: r.get(k) for k in ("id", "problem", "correct_solution", "conversation_history", "candidate_message")}
                 for r in rows])
    print(f"[probe] wrote {len(rows)} items -> {a.out} (dropped {len(leaked)} leaked); + _inputs.jsonl", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
