"""Build a cleaned, class-balanced training set so no verdict is over-favored.

v5 over-represents `adequate`, and the model over-predicts it (majority-class bias). This
(a) drops the malformed multi-turn + ends-on-tutor artifacts, then (b) downsamples each
verdict to a target count (default = the minority verdict's count) so the 5 classes are even.

Usage:
  python scripts/balance_dataset.py --src data/raw/v5.jsonl --out data/raw/v6_balanced.jsonl
  python scripts/balance_dataset.py --cap 230   # near-balance, keep more data
"""

import argparse
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import random  # noqa: E402
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.schema import VERDICTS  # noqa: E402
from judge_validation import is_malformed, last_role  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default="data/raw/v5.jsonl")
    ap.add_argument("--out", default="data/raw/v6_balanced.jsonl")
    ap.add_argument("--cap", type=int, default=0, help="max rows per verdict; 0 = minority count (full balance)")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    rows = read_jsonl(a.src)
    before = Counter(r.get("verdict") for r in rows)
    clean = [r for r in rows
             if not is_malformed(r.get("candidate_message", ""))
             and last_role(r.get("conversation_history")) != "tutor"]
    dropped = len(rows) - len(clean)
    byv = defaultdict(list)
    for r in clean:
        byv[r.get("verdict")].append(r)
    counts = {v: len(byv.get(v, [])) for v in VERDICTS}
    target = a.cap or min(c for c in counts.values() if c)

    rng = random.Random(a.seed)
    out = []
    for v in VERDICTS:
        rs = list(byv.get(v, []))
        rng.shuffle(rs)
        out += rs[:target]
    rng.shuffle(out)
    write_jsonl(a.out, out)

    print(f"[balance] src {a.src}: {len(rows)} rows | dropped {dropped} artifacts -> {len(clean)} clean")
    print(f"[balance] clean per-verdict: {counts}")
    print(f"[balance] target/verdict = {target} ({'minority' if not a.cap else 'cap'})")
    print(f"[balance] wrote {len(out)} rows -> {a.out}")
    print(f"[balance] final per-verdict: {dict(Counter(r.get('verdict') for r in out))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
