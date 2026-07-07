#!/usr/bin/env python3
"""Summarize + validate a raw dataset (a file or a directory of *.jsonl shards).

Reports totals, verdict/band/slice distributions, quality-gate pass rate (with the
first few failure reasons), duplicate ids, and rewrite-safety flags — everything needed
to review a large generated dataset at a glance.

Usage:
    python scripts/dataset_stats.py data/raw/v1.jsonl
    python scripts/dataset_stats.py data/raw            # all *.jsonl in the dir
    python scripts/dataset_stats.py data/raw --md eval/results/dataset_stats.md
"""

from __future__ import annotations

import argparse
import glob
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from socratic_tutor.io_utils import read_jsonl
from gen_lib import passes_quality_gate


def _collect(path: str) -> list[dict]:
    p = Path(path)
    files = sorted(glob.glob(str(p / "*.jsonl"))) if p.is_dir() else [str(p)]
    rows = []
    for f in files:
        for r in read_jsonl(f):
            r.setdefault("_shard", Path(f).name)
            rows.append(r)
    return rows


def summarize(rows: list[dict]) -> str:
    n = len(rows)
    verdicts = Counter(r.get("verdict") for r in rows)
    bands = Counter(r.get("band") for r in rows)
    slices = Counter(r.get("slice", "core") for r in rows)
    shards = Counter(r.get("_shard") for r in rows)

    ids = [r.get("id") for r in rows]
    dup_ids = [i for i, c in Counter(ids).items() if c > 1]

    passed, fail_reasons = 0, Counter()
    for r in rows:
        ok, errs = passes_quality_gate(r)
        if ok:
            passed += 1
        else:
            for e in errs:
                fail_reasons[e] += 1

    def dist(counter: Counter) -> str:
        return ", ".join(f"{k}={v}" for k, v in sorted(counter.items(), key=lambda x: str(x[0])))

    L = ["# Dataset stats", ""]
    L.append(f"- total examples: **{n}**")
    L.append(f"- gate pass: **{passed}/{n}** ({round(100*passed/n,1) if n else 0}%)")
    L.append(f"- duplicate ids: **{len(dup_ids)}**" + (f" ({dup_ids[:5]}...)" if dup_ids else ""))
    L.append(f"- shards: {dist(shards)}")
    L.append(f"- verdict distribution: {dist(verdicts)}")
    L.append(f"- band distribution: {dist(bands)}")
    L.append(f"- slice distribution: {dist(slices)}")
    if fail_reasons:
        L.append("")
        L.append("## Gate failure reasons")
        for reason, c in fail_reasons.most_common():
            L.append(f"- {c}x: {reason}")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", help="A .jsonl file or a directory of *.jsonl shards")
    ap.add_argument("--md", default=None, help="Also write the report to this markdown path")
    args = ap.parse_args()

    rows = _collect(args.path)
    if not rows:
        print(f"No rows found at {args.path}", file=sys.stderr)
        return 2
    report = summarize(rows)
    print(report)
    if args.md:
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md).write_text(report, encoding="utf-8")
        print(f"[stats] wrote {args.md}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
