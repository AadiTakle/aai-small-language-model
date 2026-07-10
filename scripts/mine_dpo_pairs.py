"""Mine DPO preference pairs from already-validated MRBench-derived training rows.

For every non-adequate, currently-trustworthy (needs_regen != True) MRBench-sourced row in
data/raw/v6_consensus.jsonl, the row already encodes a real contrastive pair (see
ingest_mrbench.py's pick_rewrite): a flawed tutor response (`candidate_message`) vs a clean
Expert-derived safe rewrite (`rewritten_message`). We reuse both fields directly -- no new
generation, no new judging:

  chosen_rewrite   = row["rewritten_message"]   (real, Expert-derived, already schema-valid)
  rejected_rewrite = row["candidate_message"]   (real flawed tutor turn -- vague/leaky/etc.)

chosen and rejected share an IDENTICAL verdict + reasoning, differing ONLY in the rewrite, so
the DPO preference signal isolates cleanly onto the rewritten_message continuation instead of
being diffused across also-varying reasoning text.

`source_detail` distinguishes:
  - "bridge_novice"  : id ends in -Novice -- the roadmap's "novice<expert" pairs, tightest
                        match to real elementary-tutoring novice/expert contrast.
  - "bridge_other"    : other non-adequate rows from a Bridge-origin conversation.
  - "mathdial"        : non-adequate rows from a MathDial-origin conversation.

Output rows are UNRENDERED (problem/correct_solution/conversation_history/candidate_message) --
no prompt string or tokenizer applied here. The Colab-side DPO trainer should build the actual
prompt with socratic_tutor.prompts.build_inference_prompt(tokenizer, row) using WHATEVER
tokenizer matches the model it's training, so these pairs stay portable across base-model
sizes instead of baking in this repo's local Qwen3-1.7B chat template.

Usage:
  python scripts/mine_dpo_pairs.py --dry
  python scripts/mine_dpo_pairs.py --out data/dpo/bridge_mathdial_pairs.jsonl
"""

import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402

TRAIN = "data/raw/v6_consensus.jsonl"
MRBENCH_RAW = "data/external/mrbench_v2.json"

FIELDS = ("problem", "correct_solution", "final_answer", "key_step", "conversation_history",
          "candidate_message")


def bridge_conversation_ids():
    data = json.load(open(MRBENCH_RAW))
    return {c["conversation_id"] for c in data if c.get("Data") == "Bridge"}


def classify(row_id, bridge_ids):
    if row_id.endswith("-Novice"):
        return "bridge_novice"
    # id shape: mrb-{conversation_id[:8]}-{model}
    prefix = row_id.split("-")[1] if row_id.startswith("mrb-") else None
    if prefix and any(cid.startswith(prefix) for cid in bridge_ids):
        return "bridge_other"
    return "mathdial"


def mine():
    rows = read_jsonl(TRAIN)
    bridge_ids = bridge_conversation_ids()

    pairs, skipped = [], Counter()
    for row in rows:
        if row.get("source") != "mrbench_v2":
            skipped["not_mrbench"] += 1
            continue
        if row.get("needs_regen"):
            skipped["stale_needs_regen"] += 1
            continue
        if row.get("verdict") == "adequate":
            skipped["adequate_no_rewrite"] += 1
            continue
        chosen = (row.get("rewritten_message") or "").strip()
        rejected = (row.get("candidate_message") or "").strip()
        if not chosen or not rejected:
            skipped["missing_text"] += 1
            continue
        if chosen == rejected:
            skipped["identical_chosen_rejected"] += 1
            continue

        pair = {f: row.get(f, "") for f in FIELDS}
        pair.update({
            "id": row["id"],
            "source_detail": classify(row["id"], bridge_ids),
            "verdict": row["verdict"],
            "reasoning": row.get("reasoning", ""),
            "chosen_rewrite": chosen,
            "rejected_rewrite": rejected,
        })
        pairs.append(pair)

    return pairs, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/dpo/bridge_mathdial_pairs.jsonl")
    ap.add_argument("--dry", action="store_true", help="report only; write nothing")
    a = ap.parse_args()

    pairs, skipped = mine()
    dist = Counter(p["source_detail"] for p in pairs)
    vdist = Counter(p["verdict"] for p in pairs)
    print(f"[mine-dpo] {len(pairs)} pairs mined | by source: {dict(dist)}", file=sys.stderr)
    print(f"[mine-dpo] by verdict: {dict(vdist)}", file=sys.stderr)
    print(f"[mine-dpo] skipped: {dict(skipped)}", file=sys.stderr)

    if a.dry:
        for sd in ("bridge_novice", "bridge_other", "mathdial"):
            ex = next((p for p in pairs if p["source_detail"] == sd), None)
            if ex:
                print(f"\n--- {sd} ({ex['id']}, verdict={ex['verdict']}) ---")
                print("  candidate/rejected:", ex["rejected_rewrite"][:160])
                print("  chosen:            ", ex["chosen_rewrite"][:160])
        print("[mine-dpo] --dry: nothing written.", file=sys.stderr)
        return 0

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    write_jsonl(a.out, pairs)
    print(f"[mine-dpo] wrote {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
