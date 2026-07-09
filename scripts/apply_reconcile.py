"""Apply the reconciled golden-set edits: USER + CONFIRMED edits (from proposed_edits.json)
plus the human's rulings on the borderline SUPPORTED/TENTATIVE items (ruling_results.json).

Default is --dry-run (prints the full plan, mutates nothing). Pass --apply to write:
 - backs up frozen_eval.jsonl -> frozen_eval.pre_reconcile.bak.jsonl
 - updates gold_verdict per the final map; clears gold_rewrite when a verdict becomes `adequate`
 - regenerates frozen_eval_inputs.jsonl
 - writes an auditable change log -> eval/gold/review/reconcile_applied.json

Usage:
  python scripts/apply_reconcile.py --rulings /path/ruling_results.json            # dry-run
  python scripts/apply_reconcile.py --rulings /path/ruling_results.json --apply
"""

import argparse
import glob
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.schema import VERDICTS  # noqa: E402

EDITS = "eval/gold/review/proposed_edits.json"
FROZEN = "eval/gold/frozen_eval.jsonl"
BACKUP = "eval/gold/frozen_eval.pre_reconcile.bak.jsonl"
INPUTS = "eval/gold/frozen_eval_inputs.jsonl"
LOG = "eval/gold/review/reconcile_applied.json"
APPLY_TIERS = {"USER", "CONFIRMED"}  # auto-apply; SUPPORTED/TENTATIVE come from human rulings


def _find_rulings(path):
    if path and os.path.exists(path):
        return path
    c = glob.glob(os.path.expanduser("~/Downloads/ruling_results*.json"))
    if not c:
        raise SystemExit("no ruling_results*.json found; pass --rulings PATH")
    return max(c, key=os.path.getmtime)


def build_final_map(edits, rulings):
    """id -> {old, new, source}. Returns (final, unruled_ids)."""
    final = {}
    for e in edits:
        if e["tier"] in APPLY_TIERS:
            final[e["id"]] = {"old": e["old"], "new": e["new"], "source": e["tier"]}
    unruled = []
    for x in rulings:
        r = x.get("ruling")
        if not r:
            unruled.append(x["id"])
            continue
        if r not in VERDICTS:
            unruled.append(x["id"])
            continue
        if r != x["gold"]:  # kept-gold rulings are no-ops
            src = "RULING-accept" if r == x.get("proposed") else "RULING-override"
            final[x["id"]] = {"old": x["gold"], "new": r, "source": src}
    return final, unruled


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--edits", default=EDITS)
    ap.add_argument("--frozen", default=FROZEN)
    ap.add_argument("--rulings", default=None)
    ap.add_argument("--apply", action="store_true", help="actually write (default is dry-run)")
    a = ap.parse_args()

    proposed = json.load(open(a.edits))
    edits, rewrite_flags = proposed["edits"], proposed.get("rewrite_flags", [])
    rpath = _find_rulings(a.rulings)
    rulings = json.load(open(rpath))
    ritems = rulings.get("items", rulings)

    final, unruled = build_final_map(edits, ritems)
    frozen = read_jsonl(a.frozen)
    fmap = {r["id"]: r for r in frozen}

    # validate every target exists in frozen
    missing = [iid for iid in final if iid not in fmap]
    before = Counter(r["gold_verdict"] for r in frozen)

    changes, rewrite_cleared = [], []
    for iid, ch in final.items():
        row = fmap.get(iid)
        if not row:
            continue
        cur = row.get("gold_verdict")
        if cur != ch["new"]:
            entry = {"id": iid, "old": cur, "new": ch["new"], "source": ch["source"]}
            if ch["new"] == "adequate" and (row.get("gold_rewrite") or "").strip():
                entry["gold_rewrite_cleared"] = True
                rewrite_cleared.append(iid)
            changes.append(entry)

    after = Counter(before)
    for c in changes:
        after[c["old"]] -= 1
        after[c["new"]] += 1

    by_src = Counter(c["source"] for c in changes)
    trans = Counter((c["old"], c["new"]) for c in changes)
    print(f"[apply] rulings file: {rpath}")
    print(f"[apply] final edits to write: {len(changes)}  (by source: {dict(by_src)})")
    if unruled:
        print(f"[apply] WARNING: {len(unruled)} borderline items were left UNRULED -> keeping gold: {unruled}")
    if missing:
        print(f"[apply] WARNING: {len(missing)} edit ids not found in frozen (skipped): {missing[:5]}")
    print(f"[apply] gold_rewrite cleared (verdict->adequate): {len(rewrite_cleared)}")
    print(f"[apply] rewrite-unsafe flags to handle separately: {len(rewrite_flags)} {rewrite_flags}")
    print("\n[apply] gold verdict distribution:")
    for v in VERDICTS:
        print(f"    {v:26s} {before.get(v,0):3d} -> {after.get(v,0):3d}  ({after.get(v,0)-before.get(v,0):+d})")
    print("\n[apply] transitions (old -> new):")
    for (o, n), c in trans.most_common():
        print(f"    {c:3d}  {o} -> {n}")

    if not a.apply:
        print("\n[apply] DRY-RUN — nothing written. Re-run with --apply to commit these changes.")
        return 0

    # ---- write ----
    if not os.path.exists(BACKUP):
        write_jsonl(BACKUP, frozen)  # one-time snapshot of the pre-reconcile gold
        print(f"[apply] backed up original -> {BACKUP}")
    else:
        print(f"[apply] backup already exists ({BACKUP}); leaving it (original preserved)")
    chg = {c["id"]: c for c in changes}
    for row in frozen:
        c = chg.get(row["id"])
        if not c:
            continue
        row["gold_verdict"] = c["new"]
        if c.get("gold_rewrite_cleared"):
            row["gold_rewrite"] = ""
    write_jsonl(a.frozen, frozen)
    write_jsonl(INPUTS, [{k: r.get(k) for k in
                ("id", "problem", "correct_solution", "conversation_history", "candidate_message")}
                for r in frozen])
    json.dump({"rulings_file": rpath, "n_changes": len(changes), "by_source": dict(by_src),
               "unruled": unruled, "missing": missing, "rewrite_flags": rewrite_flags,
               "before": dict(before), "after": dict(after), "changes": changes},
              open(LOG, "w"), indent=2)
    print(f"\n[apply] WROTE {len(changes)} changes to {a.frozen}")
    print(f"[apply] regenerated {INPUTS}; change log -> {LOG}")
    print("[apply] NOTE: report/model numbers must be re-scored on the corrected gold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
