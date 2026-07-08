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
from collections import Counter

CRITERIA = ["verdict", "grounded", "rewrite_safety", "schema", "calibration", "consistency"]
# order for the per-model breakdown tables (deterministic backbone first)
BREAKDOWN_ORDER = ["verdict", "schema", "consistency", "grounded", "rewrite_safety", "calibration"]
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


def _total_units(payload, crit):
    """Denominator for a criterion: item count, or pair count for calibration."""
    return payload.get("calib_n", 0) if crit == "calibration" else len(payload["per_item"])


def breakdown_stats(payload, crit):
    """Return {'0','1','2','na','n','mean','lo','hi'} for one criterion of one contestant."""
    vals = _values(payload, crit)
    total = _total_units(payload, crit)
    c = Counter(vals)
    m, lo, hi, n = bootstrap_ci(vals)
    return {"0": c.get(0, 0), "1": c.get(1, 0), "2": c.get(2, 0),
            "na": total - len(vals), "n": len(vals), "mean": m, "lo": lo, "hi": hi}


def breakdown_markdown(data, contestants):
    """Per-model tier-breakdown tables: raw 0/1/2 counts + N/A + mean[CI] per criterion.

    This is the distribution behind the aggregate means — it makes the flat schema=2.0
    visible as genuine saturation (0:0 1:0 2:n) rather than a suspicious constant, and
    exposes the small effective-n on rewrite_safety (N/A on adequate items) and calibration.
    """
    L = ["## Per-model tier breakdown (raw 0/1/2 counts behind the means)", ""]
    L.append("_Counts of each tier per criterion. `N/A` = not scored (rewrite_safety is N/A on "
             "`adequate` items with no rewrite; calibration is scored per adversarial pair, so its "
             "`n` is the pair count). Mean excludes N/A. A flat `2:n` on schema is real saturation, "
             "not a placeholder._")
    L.append("")
    for c in contestants:
        p = data[c]
        vm, vlo, vhi, vn = verdict_exact_accuracy(p)
        hdr = (f"### `{c}` — n={p['n']}, verdict exact-match {vm:.1f}% [{vlo:.1f},{vhi:.1f}]"
               if vm is not None else f"### `{c}` — n={p['n']}")
        L.append(hdr)
        L.append("Criterion | 0 | 1 | 2 | N/A | mean [95% CI]")
        L.append("---|---|---|---|---|---")
        for crit in BREAKDOWN_ORDER:
            b = breakdown_stats(p, crit)
            mean_cell = (f"{b['mean']:.3f} [{b['lo']:.2f},{b['hi']:.2f}]"
                         if b["mean"] is not None else "n/a")
            L.append(f"{CRIT_LABELS[crit]} | {b['0']} | {b['1']} | {b['2']} | {b['na']} | {mean_cell}")
        L.append("")
    return L


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

    # Per-model raw tier breakdown (the distribution behind the means)
    L.append("")
    L += breakdown_markdown(data, contestants)

    breakdown = {c: {crit: breakdown_stats(data[c], crit) for crit in BREAKDOWN_ORDER}
                 for c in contestants}

    md = "\n".join(L) + "\n"
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out + ".md", "w") as f:
        f.write(md)
    with open(args.out + ".json", "w") as f:
        json.dump({"stats": stats, "verdict_accuracy": vacc, "rollup": rolls,
                   "breakdown": breakdown, "contestants": contestants, "n": n0}, f, indent=2)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
