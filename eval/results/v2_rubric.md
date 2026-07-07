# Tiered rubric eval — Socratic Tutor Judge/Rewriter

_Judge: **OpenAI gpt-4.1**. Scale 0-2 (mean tier per criterion). n=68 gold items._

## Per-criterion (0-2 mean)
Criterion | base | tuned | Δ
---|---|---|---
Verdict correctness | 1.28 | 1.90 | +0.62
Grounded reasoning | 1.40 | 1.78 | +0.38
Rewrite safety | 1.46 | 1.47 | +0.00
Schema compliance | 1.60 | 2.00 | +0.40
Calibration robustness | 0.40 | 1.20 | +0.80
Consistency | 1.79 | 1.93 | +0.13

## Appendix A rollup (0-2 mean per dimension)
Dimension | base | tuned | Δ
---|---|---|---
Spec adherence | 1.44 | 1.95 | +0.51
Task quality | 1.43 | 1.62 | +0.19
Robustness | 0.40 | 1.20 | +0.80
Consistency | 1.79 | 1.93 | +0.13

## Error analysis
The tuned model's remaining weak cells: **Verdict correctness** 1.90 (0×tier0, 7×tier1); **Grounded reasoning** 1.78 (4×tier0, 7×tier1); **Rewrite safety** 1.47 (11×tier0, 9×tier1); **Calibration robustness** 1.20 (0×tier0, 0×tier1); **Consistency** 1.93 (0×tier0, 5×tier1).
Denominators — rewrite-safety scored over 58 non-adequate items; calibration over 5 adversarial items in 5 pair-group(s).
_Caveat: the adversarial slice is thin and its matched pairs are split across train/test, so most are scored as singletons. A frozen, paired adversarial holdout (kept intact by `build_dataset`) would make calibration robustness a stronger signal._
