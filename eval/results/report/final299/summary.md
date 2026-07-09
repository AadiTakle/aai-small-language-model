# Head-to-head — tiered rubric with bootstrap 95% CIs

_Frozen set n=299. Cells: mean tier (0-2) [95% CI]. Grader for grounded/rewrite-safety: openai-group/gpt-5.5. Deterministic criteria (verdict/schema/calibration/consistency) need no grader._

## Verdict accuracy — exact match, deterministic (%)
Contestant | accuracy % [95% CI] | n
---|---|---
base | 27.4 [22.7, 32.8] | 299
v2 | 37.1 [31.8, 42.8] | 299
v3 | 43.1 [37.5, 48.8] | 299
v4 | 50.5 [44.8, 56.2] | 299
gpt4o | 51.5 [45.8, 57.2] | 299
claude | 54.2 [48.5, 59.9] | 299
v5 | 52.5 [46.8, 58.2] | 299

## Per-criterion tier means (0-2) [95% CI]
Criterion | base | v2 | v3 | v4 | gpt4o | claude | v5
---|---|---|---|---|---|---|---
Verdict correctness | 0.96 [0.87,1.05] | 1.14 [1.05,1.23] | 1.13 [1.03,1.22] | 1.29 [1.20,1.38] | 1.30 [1.21,1.40] | 1.29 [1.19,1.38] | 1.32 [1.23,1.41]
Grounded reasoning | 0.72 [0.64,0.80] | 0.66 [0.57,0.76] | 1.03 [0.93,1.13] | 1.27 [1.18,1.37] | 1.56 [1.49,1.64] | 1.74 [1.67,1.81] | 1.39 [1.30,1.48]
Rewrite safety | 1.08 [0.99,1.18] | 0.91 [0.82,0.99] | 0.89 [0.79,0.98] | 0.98 [0.88,1.07] | 1.09 [0.98,1.21] | 0.93 [0.85,1.00] | 1.01 [0.88,1.13]
Schema compliance | 1.83 [1.79,1.87] | 1.99 [1.98,2.00] | 1.97 [1.93,1.99] | 2.00 [2.00,2.00] | 1.00 [1.00,1.00] | 1.79 [1.72,1.85] | 1.98 [1.95,2.00]
Calibration robustness | 1.00 [0.00,2.00] | 1.00 [0.00,2.00] | 1.00 [0.00,2.00] | 2.00 [2.00,2.00] | 2.00 [2.00,2.00] | 2.00 [2.00,2.00] | 2.00 [2.00,2.00]
Consistency | n/a | n/a | n/a | n/a | n/a | n/a | n/a

## Appendix A rollup (0-2 mean per dimension)
Dimension | base | v2 | v3 | v4 | gpt4o | claude | v5
---|---|---|---|---|---|---|---
Spec adherence | 1.39 | 1.57 | 1.55 | 1.64 | 1.15 | 1.54 | 1.65
Task quality | 0.90 | 0.78 | 0.96 | 1.13 | 1.33 | 1.33 | 1.20
Robustness | 1.00 | 1.00 | 1.00 | 2.00 | 2.00 | 2.00 | 2.00
Consistency | n/a | n/a | n/a | n/a | n/a | n/a | n/a

## Per-model tier breakdown (raw 0/1/2 counts behind the means)

_Counts of each tier per criterion. `N/A` = not scored (rewrite_safety is N/A on `adequate` items with no rewrite; calibration is scored per adversarial pair, so its `n` is the pair count). Mean excludes N/A. A flat `2:n` on schema is real saturation, not a placeholder._

### `base` — n=299, verdict exact-match 27.4% [22.7,32.8]
Criterion | 0 | 1 | 2 | N/A | mean [95% CI]
---|---|---|---|---|---
Verdict correctness | 95 | 122 | 82 | 0 | 0.957 [0.87,1.05]
Schema compliance | 0 | 51 | 248 | 0 | 1.829 [1.79,1.87]
Consistency | 0 | 0 | 0 | 299 | n/a
Grounded reasoning | 129 | 124 | 46 | 0 | 0.722 [0.64,0.80]
Rewrite safety | 55 | 116 | 75 | 53 | 1.081 [0.99,1.18]
Calibration robustness | 1 | 0 | 1 | 0 | 1.000 [0.00,2.00]

### `v2` — n=299, verdict exact-match 37.1% [31.8,42.8]
Criterion | 0 | 1 | 2 | N/A | mean [95% CI]
---|---|---|---|---|---
Verdict correctness | 69 | 119 | 111 | 0 | 1.140 [1.05,1.23]
Schema compliance | 1 | 0 | 298 | 0 | 1.993 [1.98,2.00]
Consistency | 0 | 0 | 0 | 299 | n/a
Grounded reasoning | 180 | 40 | 79 | 0 | 0.662 [0.57,0.76]
Rewrite safety | 82 | 126 | 57 | 34 | 0.906 [0.82,0.99]
Calibration robustness | 1 | 0 | 1 | 0 | 1.000 [0.00,2.00]

### `v3` — n=299, verdict exact-match 43.1% [37.5,48.8]
Criterion | 0 | 1 | 2 | N/A | mean [95% CI]
---|---|---|---|---|---
Verdict correctness | 90 | 80 | 129 | 0 | 1.130 [1.03,1.22]
Schema compliance | 5 | 0 | 294 | 0 | 1.967 [1.93,1.99]
Consistency | 0 | 0 | 0 | 299 | n/a
Grounded reasoning | 114 | 62 | 123 | 0 | 1.030 [0.93,1.13]
Rewrite safety | 56 | 114 | 33 | 96 | 0.887 [0.79,0.98]
Calibration robustness | 1 | 0 | 1 | 0 | 1.000 [0.00,2.00]

### `v4` — n=299, verdict exact-match 50.5% [44.8,56.2]
Criterion | 0 | 1 | 2 | N/A | mean [95% CI]
---|---|---|---|---|---
Verdict correctness | 65 | 83 | 151 | 0 | 1.288 [1.20,1.38]
Schema compliance | 0 | 0 | 299 | 0 | 2.000 [2.00,2.00]
Consistency | 0 | 0 | 0 | 299 | n/a
Grounded reasoning | 77 | 63 | 159 | 0 | 1.274 [1.18,1.37]
Rewrite safety | 56 | 106 | 51 | 86 | 0.977 [0.88,1.07]
Calibration robustness | 0 | 0 | 2 | 0 | 2.000 [2.00,2.00]

### `gpt4o` — n=299, verdict exact-match 51.5% [45.8,57.2]
Criterion | 0 | 1 | 2 | N/A | mean [95% CI]
---|---|---|---|---|---
Verdict correctness | 63 | 82 | 154 | 0 | 1.304 [1.21,1.40]
Schema compliance | 0 | 299 | 0 | 0 | 1.000 [1.00,1.00]
Consistency | 0 | 0 | 0 | 299 | n/a
Grounded reasoning | 28 | 74 | 197 | 0 | 1.565 [1.49,1.64]
Rewrite safety | 45 | 68 | 61 | 125 | 1.092 [0.98,1.21]
Calibration robustness | 0 | 0 | 2 | 0 | 2.000 [2.00,2.00]

### `claude` — n=299, verdict exact-match 54.2% [48.5,59.9]
Criterion | 0 | 1 | 2 | N/A | mean [95% CI]
---|---|---|---|---|---
Verdict correctness | 76 | 61 | 162 | 0 | 1.288 [1.19,1.38]
Schema compliance | 25 | 13 | 261 | 0 | 1.789 [1.72,1.85]
Consistency | 0 | 0 | 0 | 299 | n/a
Grounded reasoning | 35 | 8 | 256 | 0 | 1.739 [1.67,1.81]
Rewrite safety | 41 | 140 | 26 | 92 | 0.928 [0.85,1.00]
Calibration robustness | 0 | 0 | 2 | 0 | 2.000 [2.00,2.00]

### `v5` — n=299, verdict exact-match 52.5% [46.8,58.2]
Criterion | 0 | 1 | 2 | N/A | mean [95% CI]
---|---|---|---|---|---
Verdict correctness | 61 | 81 | 157 | 0 | 1.321 [1.23,1.41]
Schema compliance | 3 | 0 | 296 | 0 | 1.980 [1.95,2.00]
Consistency | 0 | 0 | 0 | 299 | n/a
Grounded reasoning | 60 | 63 | 176 | 0 | 1.388 [1.30,1.48]
Rewrite safety | 43 | 58 | 44 | 154 | 1.007 [0.88,1.13]
Calibration robustness | 0 | 0 | 2 | 0 | 2.000 [2.00,2.00]

