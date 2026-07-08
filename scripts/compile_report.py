"""Aggregate per-contestant tier files (from report_score.py / claude scorer) into a
head-to-head table with bootstrap 95% CIs, plus the Appendix A rollup and an exact-match
verdict-accuracy headline. Reads eval/results/report/*_items.json.

Usage: python scripts/compile_report.py --dir eval/results/report --out eval/results/report/summary
"""

import argparse
import glob
import json
import os
import random
import sys

CRITERIA = ["verdict", "grounded", "rewrite_safety", "schema", "calibration", "consistency"]
CRIT_LABELS = {
    "verdict": "Verdict correctness", "grounded": "Grounded reasoning",
    "rewrite_safety": "Rewrite safety", "schema": "Schema compliance",
    "calibration": "Calibration robustness", "consistency": "Consistency",
}
# stable contestant order when present
ORDER = ["base", "v2", "v3", "v4", "gpt4o", "claude"]


def _values(payload, crit):
    """Per-unit tier values for a criterion (drop N/A)."""
    if crit == "calibration":
        return [v for v in payload.get("calib_tiers", []) if v is not None]
    return [i[crit] for i in payload["per_item"] if i.get(crit) is not None]


def bootstrap_ci(vals, iters=4000, seed=0):
    if not vals:
        return (None, None, None, 0)
    rng = random.Random(seed)
    n = len(vals)
    mean = sum(vals) / n
    if n == 1:
        return (round(mean, 3), round(mean, 3), round(mean, 3), n)
    means = []
    for _ in range(iters):
        s = 0.0
        for _ in range(n):
            s += vals[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    lo = means[int(0.025 * iters)]
    hi = means[int(0.975 * iters)]
    return (round(mean, 3), round(lo, 3), round(hi, 3), n)


def verdict_exact_accuracy(payload):
    """Deterministic exact-match verdict accuracy (%) with bootstrap CI."""
    hits = [1.0 if i["pred"] == i["gold"] else 0.0 for i in payload["per_item"]]
    m, lo, hi, n = bootstrap_ci(hits)
    return (round(100 * m, 1), round(100 * lo, 1), round(100 * hi, 1), n) if m is not None else (None,) * 4


def load_all(d):
    out = {}
    for f in sorted(glob.glob(os.path.join(d, "*_items.json"))):
        p = json.load(open(f))
        out[p["contestant"]] = p
    return out


def _cell(t):
    m, lo, hi, n = t
    return f"{m:.2f} [{lo:.2f},{hi:.2f}]" if m is not None else "n/a"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default="eval/results/report")
    ap.add_argument("--out", default="eval/results/report/summary")
    args = ap.parse_args()

    data = load_all(args.dir)
    if not data:
        print(f"no *_items.json in {args.dir}", file=sys.stderr); return 2
    contestants = [c for c in ORDER if c in data] + [c for c in data if c not in ORDER]

    stats = {c: {crit: bootstrap_ci(_values(data[c], crit)) for crit in CRITERIA} for c in contestants}
    vacc = {c: verdict_exact_accuracy(data[c]) for c in contestants}

    L = ["# Head-to-head — tiered rubric with bootstrap 95% CIs", ""]
    n0 = data[contestants[0]]["n"]
    grader = data[contestants[0]].get("grader", "?")
    L.append(f"_Frozen set n={n0}. Cells: mean tier (0-2) [95% CI]. Grader for grounded/rewrite-safety: {grader}. "
             f"Deterministic criteria (verdict/schema/calibration/consistency) need no grader._")
    L.append("")
    L.append("## Verdict accuracy — exact match, deterministic (%)")
    L.append("Contestant | accuracy % [95% CI] | n")
    L.append("---|---|---")
    for c in contestants:
        m, lo, hi, n = vacc[c]
        L.append(f"{c} | {m:.1f} [{lo:.1f}, {hi:.1f}] | {n}")
    L.append("")
    L.append("## Per-criterion tier means (0-2) [95% CI]")
    L.append("Criterion | " + " | ".join(contestants))
    L.append("---|" + "|".join("---" for _ in contestants))
    for crit in CRITERIA:
        L.append(f"{CRIT_LABELS[crit]} | " + " | ".join(_cell(stats[c][crit]) for c in contestants))

    # Appendix A rollup (mean of the constituent criterion means)
    def rollup(c):
        s = stats[c]
        def avg(keys):
            xs = [s[k][0] for k in keys if s[k][0] is not None]
            return sum(xs) / len(xs) if xs else None
        return {"Spec adherence": avg(["verdict", "schema"]),
                "Task quality": avg(["grounded", "rewrite_safety"]),
                "Robustness": avg(["calibration"]),
                "Consistency": avg(["consistency"])}
    rolls = {c: rollup(c) for c in contestants}
    L.append("")
    L.append("## Appendix A rollup (0-2 mean per dimension)")
    L.append("Dimension | " + " | ".join(contestants))
    L.append("---|" + "|".join("---" for _ in contestants))
    for dim in ["Spec adherence", "Task quality", "Robustness", "Consistency"]:
        L.append(f"{dim} | " + " | ".join(
            (f"{rolls[c][dim]:.2f}" if rolls[c][dim] is not None else "n/a") for c in contestants))

    md = "\n".join(L) + "\n"
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out + ".md", "w") as f:
        f.write(md)
    with open(args.out + ".json", "w") as f:
        json.dump({"stats": stats, "verdict_accuracy": vacc, "rollup": rolls,
                   "contestants": contestants, "n": n0}, f, indent=2)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
