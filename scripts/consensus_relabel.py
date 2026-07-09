"""Multi-model CONSENSUS relabeling — audit every label with a cross-family jury.

A panel of independent frontier models (default: gpt-4.1 + claude-opus-4-8 + gemini-2.5-pro,
three different providers) each labels every item, applying the project's calibrated standard
(calibration.md). Then per item:
  - CONFIRM       : jury majority agrees with the CURRENT label.
  - CHANGE        : jury majority agrees on a DIFFERENT label (consensus says current is wrong).
  - NO_CONSENSUS  : no majority (e.g. 3-way split) -> flag for a human, keep current.

Writes a full vote report + a NO_CONSENSUS list + a CHANGES list (both for human review). With
--apply, applies CHANGE items to a copy of the dataset (verdict field := jury majority; for the
gold set, clears gold_rewrite when a verdict becomes `adequate`). Training-target regeneration
(reasoning + safe rewrite for flipped rows) is a SEPARATE step. Backs up the original.

Usage:
  python scripts/consensus_relabel.py --dataset eval/gold/frozen_eval.jsonl --label-field gold_verdict \
     --out-prefix eval/gold/review/consensus/frozen --apply
  python scripts/consensus_relabel.py --dataset data/raw/v5.jsonl --label-field verdict \
     --out-prefix eval/gold/review/consensus/train           # report only (regen handles apply)
"""

import argparse
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.prompts import build_user_prompt  # noqa: E402
from socratic_tutor.schema import VERDICTS  # noqa: E402

PANEL = ["openai-group/gpt-4.1", "claude-group/claude-opus-4-8", "gemini-group/gemini-2.5-pro"]
CALIB = open("eval/gold/review/recon-train/calibration.md").read()
SYS = (CALIB + "\n\n## THIS CALL: reply with EXACTLY ONE of these five words and nothing else: "
       + ", ".join(VERDICTS) + ".")


def _input(row):
    return {x: row.get(x) for x in ("problem", "correct_solution", "conversation_history", "candidate_message")}


def _parse(text):
    t = (text or "").lower()
    hits = [(t.index(v), v) for v in VERDICTS if v in t]
    return min(hits)[1] if hits else None


def label_all(rows, models):
    from openai import OpenAI
    client = OpenAI(timeout=60, max_retries=4)
    tasks = [(i, m) for i in range(len(rows)) for m in models]

    def one(t):
        i, m = t
        msgs = [{"role": "system", "content": SYS},
                {"role": "user", "content": build_user_prompt(_input(rows[i]))}]
        for kw in ({"temperature": 0}, {}):  # some reasoning models (e.g. claude-opus-4-8) reject temperature
            for _ in range(2):
                try:
                    r = client.chat.completions.create(model=m, max_tokens=2000, messages=msgs, **kw)
                    v = _parse(r.choices[0].message.content)
                    if v:
                        return (i, m, v)
                except Exception:  # noqa: BLE001
                    break  # drop to the no-temperature variant
        return (i, m, None)

    votes = [dict() for _ in rows]
    done = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        for i, m, v in ex.map(one, tasks):
            votes[i][m] = v
            done += 1
            if done % 100 == 0 or done == len(tasks):
                print(f"[consensus] {done}/{len(tasks)} model-calls", file=sys.stderr, flush=True)
    return votes


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--label-field", required=True)  # gold_verdict | verdict
    ap.add_argument("--out-prefix", required=True)
    ap.add_argument("--models", default=",".join(PANEL))
    ap.add_argument("--apply", action="store_true", help="write dataset with CHANGE items applied (+ backup)")
    a = ap.parse_args()
    models = [m.strip() for m in a.models.split(",")]
    os.makedirs(os.path.dirname(a.out_prefix), exist_ok=True)

    rows = read_jsonl(a.dataset)
    print(f"[consensus] {len(rows)} items x {len(models)} models = {len(rows)*len(models)} calls "
          f"| panel: {models}", file=sys.stderr)
    votes = label_all(rows, models)

    report, flagged, changes = [], [], []
    cat_ct = Counter()
    for row, vt in zip(rows, votes):
        cur = row.get(a.label_field)
        valid = [v for v in vt.values() if v in VERDICTS]
        top, n = (Counter(valid).most_common(1)[0] if valid else (None, 0))
        strict_majority = n > len(models) / 2  # >=2 of 3
        if not strict_majority:
            cat = "NO_CONSENSUS"
        elif top == cur:
            cat = "CONFIRM"
        else:
            cat = "CHANGE"
        cat_ct[cat] += 1
        rec = {"id": row.get("id"), "current": cur, "votes": vt, "majority": top,
               "n_agree": n, "n_models": len(models), "category": cat}
        report.append(rec)
        if cat == "NO_CONSENSUS":
            flagged.append({**rec, "problem": row.get("problem", "")[:160],
                            "candidate_message": row.get("candidate_message", "")[:240]})
        if cat == "CHANGE":
            changes.append(rec)

    json.dump({"dataset": a.dataset, "label_field": a.label_field, "models": models,
               "n": len(rows), "categories": dict(cat_ct), "items": report},
              open(f"{a.out_prefix}_report.json", "w"), indent=2)
    write_jsonl(f"{a.out_prefix}_flagged.jsonl", flagged)
    write_jsonl(f"{a.out_prefix}_changes.jsonl", changes)

    print(f"[consensus] {dict(cat_ct)}")
    print(f"[consensus] CHANGE transitions (current -> jury majority):")
    for (c, m), k in Counter((r["current"], r["majority"]) for r in changes).most_common():
        print(f"    {k:4d}  {c} -> {m}")
    print(f"[consensus] wrote {a.out_prefix}_report.json + _flagged.jsonl ({len(flagged)}) + _changes.jsonl ({len(changes)})")

    if a.apply:
        bak = a.dataset.replace(".jsonl", ".pre_consensus.bak.jsonl")
        if not os.path.exists(bak):
            write_jsonl(bak, rows)
        chg = {r["id"]: r["majority"] for r in changes}
        for row in rows:
            nv = chg.get(row.get("id"))
            if nv:
                row[a.label_field] = nv
                if a.label_field == "gold_verdict" and nv == "adequate":
                    row["gold_rewrite"] = ""
        write_jsonl(a.dataset, rows)
        print(f"[consensus] APPLIED {len(chg)} changes to {a.dataset} (backup {bak})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
