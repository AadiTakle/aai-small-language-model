# Tiered rubric eval — Socratic Tutor Judge/Rewriter

_Judge: **OpenAI gpt-4.1**. Scale 0-2 (mean tier per criterion). n=10 gold items._

## Per-criterion (0-2 mean)
Criterion | base | tuned | Δ
---|---|---|---
Verdict correctness | 1.30 | 1.70 | +0.40
Grounded reasoning | 1.20 | 1.70 | +0.50
Rewrite safety | 1.67 | 1.50 | -0.17
Schema compliance | 1.60 | 2.00 | +0.40
Calibration robustness | 1.00 | 1.00 | +0.00
Consistency | 1.60 | 1.90 | +0.30

## Appendix A rollup (0-2 mean per dimension)
Dimension | base | tuned | Δ
---|---|---|---
Spec adherence | 1.45 | 1.85 | +0.40
Task quality | 1.43 | 1.60 | +0.17
Robustness | 1.00 | 1.00 | +0.00
Consistency | 1.60 | 1.90 | +0.30

## Error analysis
The tuned model's remaining weak cells: **Verdict correctness** 1.70 (1×tier0, 1×tier1); **Grounded reasoning** 1.70 (0×tier0, 3×tier1); **Rewrite safety** 1.50 (1×tier0, 2×tier1); **Calibration robustness** 1.00 (0×tier0, 0×tier1); **Consistency** 1.90 (0×tier0, 1×tier1).
Denominators — rewrite-safety scored over 8 non-adequate items; calibration over 2 adversarial items in 2 pair-group(s).
_Caveat: the adversarial slice is thin and its matched pairs are split across train/test, so most are scored as singletons. A frozen, paired adversarial holdout (kept intact by `build_dataset`) would make calibration robustness a stronger signal._
