# Head-to-head — tiered rubric with bootstrap 95% CIs

_Frozen set n=103. Cells: mean tier (0-2) [95% CI]. Grader for grounded/rewrite-safety: gpt-4.1. Deterministic criteria (verdict/schema/calibration/consistency) need no grader._

## Verdict accuracy — exact match, deterministic (%)
Contestant | accuracy % [95% CI] | n
---|---|---
base | 28.2 [19.4, 36.9] | 103
v2 | 44.7 [35.0, 54.4] | 103
v3 | 50.5 [40.8, 60.2] | 103
v4 | 59.2 [49.5, 68.9] | 103
gpt4o | 45.6 [35.9, 55.3] | 103
claude | 62.1 [52.4, 70.9] | 103

## Per-criterion tier means (0-2) [95% CI]
Criterion | base | v2 | v3 | v4 | gpt4o | claude
---|---|---|---|---|---|---
Verdict correctness | 1.03 [0.89,1.17] | 1.32 [1.18,1.45] | 1.32 [1.18,1.47] | 1.53 [1.42,1.65] | 1.35 [1.22,1.48] | 1.50 [1.37,1.63]
Grounded reasoning | 0.91 [0.77,1.07] | 1.16 [1.00,1.30] | 1.48 [1.33,1.62] | 1.43 [1.30,1.54] | 1.72 [1.61,1.82] | 1.90 [1.82,1.96]
Rewrite safety | 1.76 [1.65,1.86] | 1.17 [1.01,1.33] | 1.43 [1.26,1.61] | 1.40 [1.21,1.58] | 1.73 [1.59,1.86] | 1.98 [1.93,2.00]
Schema compliance | 1.80 [1.72,1.87] | 1.98 [1.94,2.00] | 2.00 [2.00,2.00] | 2.00 [2.00,2.00] | 1.00 [1.00,1.00] | 1.99 [1.97,2.00]
Calibration robustness | 1.00 [0.00,2.00] | 1.00 [0.00,2.00] | 1.00 [0.00,2.00] | 2.00 [2.00,2.00] | 2.00 [2.00,2.00] | 2.00 [2.00,2.00]
Consistency | 1.87 [1.80,1.94] | 1.75 [1.65,1.83] | 1.56 [1.45,1.67] | 1.34 [1.20,1.47] | 1.69 [1.60,1.78] | n/a

## Appendix A rollup (0-2 mean per dimension)
Dimension | base | v2 | v3 | v4 | gpt4o | claude
---|---|---|---|---|---|---
Spec adherence | 1.41 | 1.65 | 1.66 | 1.77 | 1.18 | 1.75
Task quality | 1.34 | 1.16 | 1.45 | 1.41 | 1.72 | 1.94
Robustness | 1.00 | 1.00 | 1.00 | 2.00 | 2.00 | 2.00
Consistency | 1.87 | 1.75 | 1.56 | 1.34 | 1.69 | n/a

## Per-model tier breakdown (raw 0/1/2 counts behind the means)

_Counts of each tier per criterion. `N/A` = not scored (rewrite_safety is N/A on `adequate` items with no rewrite; calibration is scored per adversarial pair, so its `n` is the pair count). Mean excludes N/A. A flat `2:n` on schema is real saturation, not a placeholder._

### `base` — n=103, verdict exact-match 28.2% [19.4,36.9]
Criterion | 0 | 1 | 2 | N/A | mean [95% CI]
---|---|---|---|---|---
Verdict correctness | 26 | 48 | 29 | 0 | 1.029 [0.89,1.17]
Schema compliance | 0 | 21 | 82 | 0 | 1.796 [1.72,1.87]
Consistency | 1 | 11 | 91 | 0 | 1.874 [1.80,1.94]
Grounded reasoning | 36 | 40 | 27 | 0 | 0.913 [0.77,1.07]
Rewrite safety | 2 | 15 | 64 | 22 | 1.765 [1.65,1.86]
Calibration robustness | 1 | 0 | 1 | 0 | 1.000 [0.00,2.00]

### `v2` — n=103, verdict exact-match 44.7% [35.0,54.4]
Criterion | 0 | 1 | 2 | N/A | mean [95% CI]
---|---|---|---|---|---
Verdict correctness | 13 | 44 | 46 | 0 | 1.320 [1.18,1.45]
Schema compliance | 1 | 0 | 102 | 0 | 1.981 [1.94,2.00]
Consistency | 2 | 22 | 79 | 0 | 1.748 [1.65,1.83]
Grounded reasoning | 25 | 37 | 41 | 0 | 1.155 [1.00,1.30]
Rewrite safety | 21 | 32 | 36 | 14 | 1.169 [1.01,1.33]
Calibration robustness | 1 | 0 | 1 | 0 | 1.000 [0.00,2.00]

### `v3` — n=103, verdict exact-match 50.5% [40.8,60.2]
Criterion | 0 | 1 | 2 | N/A | mean [95% CI]
---|---|---|---|---|---
Verdict correctness | 19 | 32 | 52 | 0 | 1.320 [1.18,1.47]
Schema compliance | 0 | 0 | 103 | 0 | 2.000 [2.00,2.00]
Consistency | 4 | 37 | 62 | 0 | 1.563 [1.45,1.67]
Grounded reasoning | 16 | 22 | 65 | 0 | 1.476 [1.33,1.62]
Rewrite safety | 13 | 16 | 45 | 29 | 1.432 [1.26,1.61]
Calibration robustness | 1 | 0 | 1 | 0 | 1.000 [0.00,2.00]

### `v4` — n=103, verdict exact-match 59.2% [49.5,68.9]
Criterion | 0 | 1 | 2 | N/A | mean [95% CI]
---|---|---|---|---|---
Verdict correctness | 6 | 36 | 61 | 0 | 1.534 [1.42,1.65]
Schema compliance | 0 | 0 | 103 | 0 | 2.000 [2.00,2.00]
Consistency | 11 | 46 | 46 | 0 | 1.340 [1.20,1.47]
Grounded reasoning | 9 | 41 | 53 | 0 | 1.427 [1.30,1.54]
Rewrite safety | 17 | 13 | 48 | 25 | 1.397 [1.21,1.58]
Calibration robustness | 0 | 0 | 2 | 0 | 2.000 [2.00,2.00]

### `gpt4o` — n=103, verdict exact-match 45.6% [35.9,55.3]
Criterion | 0 | 1 | 2 | N/A | mean [95% CI]
---|---|---|---|---|---
Verdict correctness | 11 | 45 | 47 | 0 | 1.350 [1.22,1.48]
Schema compliance | 0 | 103 | 0 | 0 | 1.000 [1.00,1.00]
Consistency | 0 | 32 | 71 | 0 | 1.689 [1.60,1.78]
Grounded reasoning | 4 | 21 | 78 | 0 | 1.718 [1.61,1.82]
Rewrite safety | 5 | 7 | 51 | 40 | 1.730 [1.59,1.86]
Calibration robustness | 0 | 0 | 2 | 0 | 2.000 [2.00,2.00]

### `claude` — n=103, verdict exact-match 62.1% [52.4,70.9]
Criterion | 0 | 1 | 2 | N/A | mean [95% CI]
---|---|---|---|---|---
Verdict correctness | 12 | 27 | 64 | 0 | 1.505 [1.37,1.63]
Schema compliance | 0 | 1 | 102 | 0 | 1.990 [1.97,2.00]
Consistency | 0 | 0 | 0 | 103 | n/a
Grounded reasoning | 2 | 6 | 95 | 0 | 1.903 [1.82,1.96]
Rewrite safety | 1 | 0 | 79 | 23 | 1.975 [1.93,2.00]
Calibration robustness | 0 | 0 | 2 | 0 | 2.000 [2.00,2.00]

