"""Multi-axis, label-SAFE balancing of the verdict training set (Task 1).

Per the overnight spec: balance not only on verdict but also on deterministic axes (candidate
length, conversation turns, problem #numbers, topic, grade band) — WITHOUT editing any row
(resample only, so every gold verdict stays valid by construction).

Method:
  1. Load source (v9b = the current data), drop quality-gate failures + malformed/ends-on-tutor
     artifacts, and EXCLUDE any id in the frozen eval set (no train/eval leakage).
  2. Hard-balance verdict: equal count per verdict (= minority count, or --per-verdict).
  3. Within each verdict, select that quota by ROUND-ROBIN over composite secondary cells
     (band x topic x len x turns x nnum) so the secondary-axis marginals come out ~flat:
     rare cells are fully kept, over-represented cells are downsampled.
  4. Report before/after marginals for every axis + coverage gaps. Never fabricates/edits data.

Usage:
  python scripts/overnight/balance_multiaxis.py --src data/raw/v9b.jsonl \
      --holdout eval/gold/frozen_eval.jsonl --out data/raw/verdict_balanced.jsonl \
      --report eval/results/overnight/balance_report.md
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.schema import VERDICTS  # noqa: E402
from gen_lib import passes_quality_gate  # noqa: E402
from judge_validation import is_malformed, last_role  # noqa: E402
from overnight.split_common import features  # noqa: E402

AXES = ["verdict", "band", "topic", "len", "turns", "nnum"]
SECONDARY = ["band", "topic", "len", "turns", "nnum"]


def _marginals(rows_feats):
    return {ax: dict(sorted(Counter(f[ax] for f in rows_feats).items())) for ax in AXES}


def _fmt_marginals(m):
    lines = []
    for ax in AXES:
        cells = ", ".join(f"{k}={v}" for k, v in m[ax].items())
        lines.append(f"- **{ax}**: {cells}")
    return "\n".join(lines)


def select_stratified(rows, quota, rng):
    """Round-robin over composite secondary cells to flatten secondary marginals."""
    cells = defaultdict(list)
    for r in rows:
        f = features(r)
        cells[(f["band"], f["topic"], f["len"], f["turns"], f["nnum"])].append(r)
    for c in cells.values():
        rng.shuffle(c)
    keys = list(cells.keys())
    rng.shuffle(keys)
    selected = []
    progressed = True
    while len(selected) < quota and progressed:
        progressed = False
        for k in keys:
            if cells[k]:
                selected.append(cells[k].pop())
                progressed = True
                if len(selected) >= quota:
                    break
    return selected


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default="data/raw/v9b.jsonl")
    ap.add_argument("--holdout", default="eval/gold/frozen_eval.jsonl",
                    help="Exclude these ids from the training pool (no eval leakage).")
    ap.add_argument("--out", default="data/raw/verdict_balanced.jsonl")
    ap.add_argument("--report", default="eval/results/overnight/balance_report.md")
    ap.add_argument("--per-verdict", type=int, default=0, help="0 = minority count (full balance)")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    rows = read_jsonl(a.src)
    n_raw = len(rows)

    def _norm(s):
        return re.sub(r"\s+", " ", (s or "").strip().lower())

    hold_ids, hold_text = set(), set()
    if a.holdout and os.path.exists(a.holdout):
        h = read_jsonl(a.holdout)
        hold_ids = {r.get("id") for r in h}
        hold_text = {_norm(r.get("candidate_message")) for r in h}

    clean, n_gate, n_art, n_hold = [], 0, 0, 0
    for r in rows:
        if r.get("id") in hold_ids or _norm(r.get("candidate_message")) in hold_text:
            n_hold += 1
            continue
        if not passes_quality_gate(r)[0]:
            n_gate += 1
            continue
        if is_malformed(r.get("candidate_message", "")) or last_role(r.get("conversation_history")) == "tutor":
            n_art += 1
            continue
        clean.append(r)

    before = _marginals([features(r) for r in clean])
    byv = defaultdict(list)
    for r in clean:
        byv[r.get("verdict")].append(r)
    counts = {v: len(byv.get(v, [])) for v in VERDICTS}
    target = a.per_verdict or min(c for c in counts.values() if c)

    rng = random.Random(a.seed)
    out = []
    for v in VERDICTS:
        out += select_stratified(list(byv.get(v, [])), target, rng)
    rng.shuffle(out)
    write_jsonl(a.out, out)
    after = _marginals([features(r) for r in out])

    # coverage gaps: (band x topic) cells that are thin/empty in the balanced set
    bt = Counter((features(r)["band"], features(r)["topic"]) for r in out)
    gaps = [f"{b}/{t}" for (b, t), c in sorted(bt.items()) if c < 3]

    rep = [
        "# Task 1 — verdict dataset balancing (label-safe resample)", "",
        f"Source: `{a.src}` ({n_raw} raw). Excluded: {n_hold} frozen-eval ids, "
        f"{n_gate} gate-fails, {n_art} malformed/ends-on-tutor artifacts -> **{len(clean)} clean pool**.", "",
        f"Balance: hard-equal verdict at **{target}/verdict** "
        f"({'minority' if not a.per_verdict else 'cap'}) -> **{len(out)} rows**. "
        "Secondary axes flattened by round-robin over band x topic x len x turns x nnum cells.", "",
        f"Clean per-verdict (pre-balance): {counts}", "",
        "## BEFORE (clean pool marginals)", _fmt_marginals(before), "",
        "## AFTER (balanced set marginals)", _fmt_marginals(after), "",
        f"## Coverage gaps (band/topic cells with <3 rows): {gaps if gaps else 'none'}", "",
        "_No row content was edited; balancing is pure resampling, so every gold verdict stays valid._",
    ]
    Path(a.report).parent.mkdir(parents=True, exist_ok=True)
    Path(a.report).write_text("\n".join(rep) + "\n", encoding="utf-8")

    print(f"[balance] {a.src}: {n_raw} raw -> {len(clean)} clean "
          f"(excluded {n_hold} holdout / {n_gate} gate / {n_art} artifact)")
    print(f"[balance] per-verdict target={target} -> {len(out)} rows -> {a.out}")
    print(f"[balance] AFTER marginals:")
    for ax in AXES:
        print(f"    {ax}: {after[ax]}")
    print(f"[balance] coverage gaps (<3): {gaps if gaps else 'none'}")
    print(f"[balance] report -> {a.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
