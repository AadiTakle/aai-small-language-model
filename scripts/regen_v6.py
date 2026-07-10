"""Regenerate stale reasoning/rewritten_message for `needs_regen` rows in v6_consensus.jsonl.

These rows had their `verdict` changed by apply_rulings.py (human-ruled consensus) but kept
their OLD reasoning/rewritten_message, which no longer justifies the now-correct verdict.
Unlike relabel_training.py's v4->v5 pipeline, there is NO judge pass here -- verdict is
already final -- so this goes straight to regeneration.

Pipeline:
  --prep    : batch the needs_regen rows + write criteria.md, for Claude-subagent dispatch.
              [subagents write regen_out_XX.jsonl into the same dir]
  --assemble: merge regen_out_*.jsonl back into v6_consensus.jsonl (backup first), leak-gate
              non-adequate rewrites via _heuristic_safe, clear needs_regen on success, report.
              Rows that fail the leak-gate or have no regen output are DROPPED (not kept stale).

Usage:
  python scripts/regen_v6.py --prep --batches 8
  python scripts/regen_v6.py --assemble
"""

import argparse
import glob
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.prompts import SYSTEM_PROMPT  # noqa: E402
from socratic_tutor.rubric import _heuristic_safe  # noqa: E402  reuse the leak check
from reconcile_review import REVIEWER_CRITERIA  # noqa: E402

TRAIN = "data/raw/v6_consensus.jsonl"
RV = "eval/gold/review/regen-v6"
ROW_FIELDS = ("id", "problem", "correct_solution", "final_answer", "key_step",
              "conversation_history", "candidate_message", "verdict")


def prep(batches):
    rows = read_jsonl(TRAIN)
    pending = [r for r in rows if r.get("needs_regen")]
    os.makedirs(RV, exist_ok=True)

    crit = [
        "# Regenerate TRAINING targets for v6_consensus.jsonl `needs_regen` rows", "",
        "Each row below already has a FINAL, CORRECT `verdict` (set by a human-ruled consensus "
        "process -- do NOT second-guess or change it). Its `reasoning` and `rewritten_message` "
        "are STALE -- left over from a prior, now-incorrect verdict -- and must be regenerated "
        "from scratch so they actually justify the given verdict.", "",
        "## Base taxonomy", SYSTEM_PROMPT, "",
        "## OPERATIVE CRITERIA (the standard the verdict was ruled against)", REVIEWER_CRITERIA, "",
        "## For EACH row produce:",
        "- `reasoning`: one-to-two sentences that JUSTIFY the given `verdict`, citing a SPECIFIC "
        "detail from the problem / solution / conversation / candidate message (never a bare "
        "label, never generic filler).",
        "- `rewritten_message`: REQUIRED whenever verdict != \"adequate\" -- a SAFE Socratic hint "
        "that (a) NEVER states the final answer, (b) NEVER hands over the key step/insight or the "
        "pivotal relationship, (c) points the student toward WHERE their mistake is and asks them "
        "to find/fix it, (d) is grounded in the student's most recent message. It must NOT contain "
        "the final_answer and must NOT restate the key_step.",
        "  When verdict == \"adequate\": set `rewritten_message` to null (adequate candidate "
        "messages are not rewritten).", "",
        "## OUTPUT (strict)",
        "Write to the output path given in your task prompt as JSONL -- exactly ONE line per "
        "input row, no prose, no markdown fences:",
        '  {"id": "<row id>", "reasoning": "<...>", "rewritten_message": "<...>" | null}',
        "Cover every id exactly once.",
    ]
    with open(f"{RV}/criteria.md", "w") as f:
        f.write("\n".join(crit))

    per = (len(pending) + batches - 1) // batches
    nb = 0
    for k in range(batches):
        chunk = pending[k * per:(k + 1) * per]
        if not chunk:
            continue
        write_jsonl(f"{RV}/batch_{k:02d}.jsonl", [{f: r.get(f) for f in ROW_FIELDS} for r in chunk])
        nb += 1
    print(f"[prep] {len(pending)} needs_regen rows -> {nb} batches (~{per} each)", file=sys.stderr)
    print(f"[prep] verdict dist: {dict(Counter(r['verdict'] for r in pending))}", file=sys.stderr)
    print(f"[prep] wrote {RV}/criteria.md + batch_00..{nb-1:02d}.jsonl", file=sys.stderr)
    return 0


def assemble():
    rows = read_jsonl(TRAIN)
    regen = {}
    bad = 0
    for f in sorted(glob.glob(f"{RV}/regen_out_*.jsonl")):
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
                if o.get("id"):
                    regen[o["id"]] = o
                else:
                    bad += 1
            except Exception:
                bad += 1

    out, dropped = [], []
    n_kept = n_adeq = n_regen = 0
    for row in rows:
        if not row.get("needs_regen"):
            out.append(row)
            n_kept += 1
            continue
        g = regen.get(row["id"])
        if not g:
            dropped.append((row["id"], "no_regen_output"))
            continue
        new = dict(row)
        new["reasoning"] = (g.get("reasoning") or "").strip()
        if not new["reasoning"]:
            dropped.append((row["id"], "empty_reasoning"))
            continue
        if row["verdict"] == "adequate":
            new["rewritten_message"] = None
            new.pop("needs_regen", None)
            new["relabeled"] = new.get("relabeled") or "regenerated"
            out.append(new)
            n_adeq += 1
        else:
            rw = (g.get("rewritten_message") or "").strip()
            if not rw:
                dropped.append((row["id"], "missing_rewrite"))
                continue
            if not _heuristic_safe(row, {"rewritten_message": rw}):  # leak gate
                dropped.append((row["id"], "rewrite_leaks"))
                continue
            new["rewritten_message"] = rw
            new.pop("needs_regen", None)
            new["relabeled"] = new.get("relabeled") or "regenerated"
            out.append(new)
            n_regen += 1

    print(f"[assemble] regen_out lines read: {len(regen)} (bad={bad})")
    print(f"[assemble] {len(rows)} -> {len(out)} rows "
          f"(kept {n_kept}, resolved-adequate {n_adeq}, regenerated {n_regen})")
    print(f"[assemble] dropped {len(dropped)}: {Counter(d[1] for d in dropped)}")
    if dropped:
        json.dump(dropped, open(f"{RV}/dropped.json", "w"), indent=2)
        print(f"[assemble] wrote {RV}/dropped.json")

    still_pending = [r["id"] for r in out if r.get("needs_regen")]
    if still_pending:
        print(f"[assemble] WARNING {len(still_pending)} rows still flagged needs_regen after merge")

    bak = TRAIN.replace(".jsonl", ".pre_regen.bak.jsonl")
    if not os.path.exists(bak):
        write_jsonl(bak, rows)
    write_jsonl(TRAIN, out)
    print(f"[assemble] wrote {TRAIN} (backup {bak})")
    print(f"[assemble] new verdict dist: {dict(Counter(r['verdict'] for r in out))}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prep", action="store_true")
    ap.add_argument("--assemble", action="store_true")
    ap.add_argument("--batches", type=int, default=8)
    a = ap.parse_args()
    if a.prep:
        return prep(a.batches)
    if a.assemble:
        return assemble()
    ap.error("pass --prep or --assemble")


if __name__ == "__main__":
    raise SystemExit(main())
