"""Diagnostic: which leaks does the detector miss? Confirms whether the recall bottleneck is
gives_away_key_step. Runs the adapter on the frozen set, finds gold-leak items it calls non-leak,
and breaks them down by gold verdict + what it called them instead + examples.

Usage:
  python scripts/overnight/diag_missed_leaks.py --adapter adapters/judge_full --mode verdict
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl  # noqa: E402
from overnight.split_common import LEAK  # noqa: E402
from overnight.eval_verdict import mlx_preds  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adapter", default="adapters/judge_full")
    ap.add_argument("--mode", default="verdict")
    ap.add_argument("--out", default="eval/results/overnight/diag_missed_leaks")
    a = ap.parse_args()

    gold = read_jsonl(str(config.GOLD_DIR / "frozen_eval.jsonl"))
    print(f"[diag] {a.adapter} on frozen n={len(gold)} ...", file=sys.stderr)
    preds = mlx_preds(a.adapter, a.mode, gold, 200)
    leaks = [r for r in gold if r.get("gold_verdict") in LEAK]
    missed = [r for r in leaks if preds.get(r["id"]) not in LEAK]
    by_gold = Counter(r["gold_verdict"] for r in missed)
    called = Counter(preds.get(r["id"]) for r in missed)

    L = [f"# Diagnostic — `{a.adapter}` missed leaks (frozen n={len(gold)})", "",
         f"Total leaks: {len(leaks)} | caught: {len(leaks) - len(missed)} | "
         f"**MISSED: {len(missed)}** (leak recall {100 * (len(leaks) - len(missed)) / len(leaks):.0f}%)", "",
         "## Missed leaks by gold verdict (which leak type is the bottleneck)", ""]
    for v in ("gives_away_key_step", "gives_final_answer"):
        tot = sum(1 for r in leaks if r["gold_verdict"] == v)
        mis = by_gold.get(v, 0)
        L.append(f"- **{v}**: missed {mis}/{tot} (recall {100 * (tot - mis) / tot:.0f}%)" if tot else f"- {v}: n/a")
    L += ["", "## What the detector called the missed leaks instead", ""]
    for k, c in called.most_common():
        L.append(f"- {k}: {c}")
    L += ["", "## Examples (missed leaks)", ""]
    for r in missed[:8]:
        L.append(f"- [{r['gold_verdict']} → {preds.get(r['id'])}] \"{(r.get('candidate_message') or '')[:150]}\"")
    md = "\n".join(L) + "\n"
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out + ".md").write_text(md, encoding="utf-8")
    print(md)
    print(f"[diag] wrote {a.out}.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
