"""Apply human rulings (consensus_rulings.json from build_consensus_ruling_ui.py) to a dataset.

Filters to the requested bucket(s), then per item:
  - ruling set and != current  -> CHANGE the label (label-field := ruling).
  - drop == true               -> DROP the row from the dataset.
  - ruling == current          -> keep (no-op).
  - unruled                    -> skipped (warned).

For gold (label-field gold_verdict): a change to `adequate` clears gold_rewrite.
For training (label-field verdict): any verdict change marks the row needs_regen=True
(its reasoning + rewritten_message are now stale and must be regenerated before retraining).
Backs up the dataset first. Idempotent-ish: re-running with the same rulings is a no-op after
the first apply (changed rows already match).

Usage:
  # gold (both gold buckets) -> triggers a re-score afterwards
  python scripts/apply_rulings.py --rulings ~/Downloads/consensus_rulings.json \
     --buckets gold-override,gold-noconsensus --dataset eval/gold/frozen_eval.jsonl --label-field gold_verdict
  # training rulings -> fold into the v6 training source
  python scripts/apply_rulings.py --rulings ~/Downloads/consensus_rulings.json \
     --buckets train-noconsensus --dataset data/raw/v6_consensus.jsonl --label-field verdict
"""

import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.schema import VERDICTS  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rulings", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--label-field", required=True)  # gold_verdict | verdict
    ap.add_argument("--buckets", required=True, help="comma-separated bucket names to apply")
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    a = ap.parse_args()
    buckets = {b.strip() for b in a.buckets.split(",")}

    rulings = json.load(open(os.path.expanduser(a.rulings)))["items"]
    scoped = [r for r in rulings if r.get("bucket") in buckets]
    changes, drops, unruled, kept = {}, set(), [], 0
    for r in scoped:
        rid, ruling, drop = r["id"], r.get("ruling"), r.get("drop")
        if drop:
            drops.add(rid)
        elif ruling and ruling in VERDICTS and ruling != r.get("current"):
            changes[rid] = ruling
        elif ruling:
            kept += 1
        else:
            unruled.append(rid)

    print(f"[apply] buckets={sorted(buckets)} | scoped={len(scoped)}: "
          f"{len(changes)} change, {len(drops)} drop, {kept} keep, {len(unruled)} UNRULED", file=sys.stderr)
    if changes:
        print("[apply] label changes (current -> ruled):")
        cur = {r["id"]: r.get("current") for r in scoped}
        for (c, n), k in Counter((cur[i], v) for i, v in changes.items()).most_common():
            print(f"    {k:3d}  {c} -> {n}")
    if unruled:
        print(f"[apply] WARNING {len(unruled)} scoped items were never ruled (left untouched): {unruled[:8]}", file=sys.stderr)

    rows = read_jsonl(a.dataset)
    ids = {row.get("id") for row in rows}
    missing = (set(changes) | drops) - ids
    if missing:
        print(f"[apply] WARNING {len(missing)} ruled ids not found in dataset: {list(missing)[:8]}", file=sys.stderr)

    out, n_drop, n_chg = [], 0, 0
    for row in rows:
        rid = row.get("id")
        if rid in drops:
            n_drop += 1
            continue
        if rid in changes:
            nv = changes[rid]
            row[a.label_field] = nv
            if a.label_field == "gold_verdict" and nv == "adequate":
                row["gold_rewrite"] = ""
            if a.label_field == "verdict":
                row["needs_regen"] = True  # reasoning + rewrite now stale
            n_chg += 1
        out.append(row)

    dist = Counter(row.get(a.label_field) for row in out)
    print(f"[apply] result: {len(rows)} -> {len(out)} rows ({n_chg} relabeled, {n_drop} dropped)")
    print(f"[apply] new {a.label_field} dist: {dict(dist)}")

    if a.dry_run:
        print("[apply] --dry-run: nothing written.", file=sys.stderr)
        return 0
    bak = a.dataset.replace(".jsonl", ".pre_ruling.bak.jsonl")
    if not os.path.exists(bak):
        write_jsonl(bak, rows)
    write_jsonl(a.dataset, out)
    print(f"[apply] wrote {a.dataset} (backup {bak})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
