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

## Per-criterion tier means (0-2) [95% CI]
Criterion | base | v2 | v3 | v4 | gpt4o
---|---|---|---|---|---
Verdict correctness | 1.03 [0.89,1.17] | 1.32 [1.18,1.45] | 1.32 [1.18,1.47] | 1.53 [1.42,1.65] | 1.35 [1.22,1.48]
Grounded reasoning | 0.91 [0.77,1.07] | 1.16 [1.00,1.30] | 1.48 [1.33,1.62] | 1.43 [1.30,1.54] | 1.72 [1.61,1.82]
Rewrite safety | 1.76 [1.65,1.86] | 1.17 [1.01,1.33] | 1.43 [1.26,1.61] | 1.40 [1.21,1.58] | 1.73 [1.59,1.86]
Schema compliance | 1.80 [1.72,1.87] | 1.98 [1.94,2.00] | 2.00 [2.00,2.00] | 2.00 [2.00,2.00] | 1.00 [1.00,1.00]
Calibration robustness | 1.00 [0.00,2.00] | 1.00 [0.00,2.00] | 1.00 [0.00,2.00] | 2.00 [2.00,2.00] | 2.00 [2.00,2.00]
Consistency | 1.87 [1.80,1.94] | 1.75 [1.65,1.83] | 1.56 [1.45,1.67] | 1.34 [1.20,1.47] | 1.69 [1.60,1.78]

## Appendix A rollup (0-2 mean per dimension)
Dimension | base | v2 | v3 | v4 | gpt4o
---|---|---|---|---|---
Spec adherence | 1.41 | 1.65 | 1.66 | 1.77 | 1.18
Task quality | 1.34 | 1.16 | 1.45 | 1.41 | 1.72
Robustness | 1.00 | 1.00 | 1.00 | 2.00 | 2.00
Consistency | 1.87 | 1.75 | 1.56 | 1.34 | 1.69
