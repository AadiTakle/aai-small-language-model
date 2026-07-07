# Tiered rubric eval — Socratic Tutor Judge/Rewriter

_Judge: **OpenAI gpt-4.1**. Scale 0-2 (mean tier per criterion). n=69 gold items._

## Per-criterion (0-2 mean)
Criterion | base | tuned | Δ
---|---|---|---
Verdict correctness | 0.96 | 1.65 | +0.69
Grounded reasoning | 0.93 | 1.70 | +0.77
Rewrite safety | 1.41 | 1.73 | +0.32
Schema compliance | 1.71 | 2.00 | +0.29
Calibration robustness | 0.60 | 1.00 | +0.40
Consistency | 1.70 | 1.75 | +0.06

## Appendix A rollup (0-2 mean per dimension)
Dimension | base | tuned | Δ
---|---|---|---
Spec adherence | 1.33 | 1.83 | +0.49
Task quality | 1.17 | 1.71 | +0.55
Robustness | 0.60 | 1.00 | +0.40
Consistency | 1.70 | 1.75 | +0.06

## Error analysis
The tuned model's remaining weak cells: **Verdict correctness** 1.65 (5×tier0, 14×tier1); **Grounded reasoning** 1.70 (2×tier0, 17×tier1); **Rewrite safety** 1.73 (4×tier0, 3×tier1); **Calibration robustness** 1.00 (0×tier0, 0×tier1); **Consistency** 1.75 (2×tier0, 13×tier1).
Denominators — rewrite-safety scored over 41 non-adequate items; calibration over 6 adversarial items in 5 pair-group(s).
_Caveat: the adversarial slice is thin and its matched pairs are split across train/test, so most are scored as singletons. A frozen, paired adversarial holdout (kept intact by `build_dataset`) would make calibration robustness a stronger signal._
