"""Validate human curations against the broad LLM leak-detector; write the CLEAN subset.

Used as rewrite_v4's few-shot steering exemplars + gold — steer/train only on human hints that are
clean by the metric that matters (a few human 'write-better' hints still name the operation, e.g.
'what operation would undo the division by 3'; those shouldn't steer the teacher)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from overnight.split_common import llm_leaks, parallel_map  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default="data/raw/human_rewrites.jsonl")
    ap.add_argument("--out", default="data/raw/human_rewrites_clean.jsonl")
    a = ap.parse_args()
    rows = read_jsonl(a.src)
    flags = parallel_map(lambda r: llm_leaks(r.get("rewrite", ""), r), rows, workers=6)
    clean = [r for r, f in zip(rows, flags) if not f]
    write_jsonl(a.out, clean)
    print(f"[validate-human] {len(clean)}/{len(rows)} human hints clean "
          f"({len(rows) - len(clean)} leaky excluded from steering) -> {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
