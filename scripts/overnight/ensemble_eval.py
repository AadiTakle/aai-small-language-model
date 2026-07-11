"""Ensemble-union verdict eval (recall-first): flag as leak if ANY member model says leak.

When the judge only TRIGGERS a rewrite, leak recall is the ship metric and false positives are
cheap — so unioning a high-recall model (judge_full) with a high-precision one (v6) should push
recall past either alone. Reports each member + the union on the frozen set.

Usage:
  python scripts/overnight/ensemble_eval.py --members judge_full,v6 --out eval/results/overnight/ensemble_eval
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl  # noqa: E402
from overnight.split_common import LEAK  # noqa: E402
from overnight.eval_verdict import mlx_preds  # noqa: E402

SPECS = {
    "judge_full": ("adapters/judge_full", "verdict", 200),
    "v6": ("adapters/v6", "full", 160),
    "combined_bal": ("adapters/combined_bal", "full", 160),
    "combined_full": ("adapters/combined_full", "full", 160),
    "judge_v1": ("adapters/judge_v1", "verdict", 200),
}


def bin_metrics(is_leak, gold):
    gl = [r.get("gold_verdict") in LEAK for r in gold]
    pl = [is_leak(r["id"]) for r in gold]
    tp = sum(1 for p, g in zip(pl, gl) if p and g)
    fp = sum(1 for p, g in zip(pl, gl) if p and not g)
    fn = sum(1 for p, g in zip(pl, gl) if not p and g)
    rec = tp / (tp + fn) if tp + fn else 0.0
    prec = tp / (tp + fp) if tp + fp else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    sb = sum(1 for p, g in zip(pl, gl) if p == g) / len(gold)
    return {"leak_r": rec, "leak_p": prec, "leak_f1": f1, "safety_binary": sb, "fp": fp, "fn": fn}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frozen", default=str(config.GOLD_DIR / "frozen_eval.jsonl"))
    ap.add_argument("--members", default="judge_full,v6")
    ap.add_argument("--out", default="eval/results/overnight/ensemble_eval")
    a = ap.parse_args()

    gold = read_jsonl(a.frozen)
    members = [m.strip() for m in a.members.split(",") if m.strip() in SPECS and (REPO / SPECS[m.strip()][0]).exists()]
    print(f"[ensemble] members={members} frozen n={len(gold)}", file=sys.stderr)
    preds = {}
    for m in members:
        ad, mode, mt = SPECS[m]
        print(f"[ensemble] {m} ...", file=sys.stderr)
        preds[m] = mlx_preds(ad, mode, gold, mt)

    rows = [(m, bin_metrics(lambda i, n=m: preds[n].get(i) in LEAK, gold)) for m in members]
    rows.append((f"UNION({'|'.join(members)})",
                 bin_metrics(lambda i: any(preds[n].get(i) in LEAK for n in members), gold)))

    L = [f"# Ensemble-union verdict eval (frozen n={len(gold)}) — recall-first", "",
         "| model | leak recall | leak precision | leak F1 | safety-binary | false-pos | missed-leaks |",
         "|---|---|---|---|---|---|---|"]
    for name, m in rows:
        L.append(f"| {name} | {m['leak_r']:.1%} | {m['leak_p']:.1%} | {m['leak_f1']:.1%} | "
                 f"{m['safety_binary']:.1%} | {m['fp']} | {m['fn']} |")
    md = "\n".join(L) + "\n"
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out + ".md").write_text(md, encoding="utf-8")
    Path(a.out + ".json").write_text(json.dumps({n: m for n, m in rows}, indent=2), encoding="utf-8")
    print(md)
    print(f"[ensemble] wrote {a.out}.md/.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
