# Tiered rubric eval — Socratic Tutor Judge/Rewriter

_Judge: **OpenAI gpt-4.1**. Scale 0-2 (mean tier per criterion). n=10 gold items._

## Per-criterion (0-2 mean)
Criterion | base | tuned | Δ
---|---|---|---
Verdict correctness | 1.30 | 1.80 | +0.50
Grounded reasoning | 1.20 | 1.80 | +0.60
Rewrite safety | 1.67 | 1.71 | +0.05
Schema compliance | 1.60 | 2.00 | +0.40
Calibration robustness | 1.00 | 2.00 | +1.00
Consistency | 1.60 | 1.80 | +0.20

## Appendix A rollup (0-2 mean per dimension)
Dimension | base | tuned | Δ
---|---|---|---
Spec adherence | 1.45 | 1.90 | +0.45
Task quality | 1.43 | 1.76 | +0.32
Robustness | 1.00 | 2.00 | +1.00
Consistency | 1.60 | 1.80 | +0.20

## Error analysis
The tuned model's remaining weak cells: **Verdict correctness** 1.80 (1×tier0, 0×tier1); **Grounded reasoning** 1.80 (0×tier0, 2×tier1); **Rewrite safety** 1.71 (0×tier0, 2×tier1); **Consistency** 1.80 (1×tier0, 0×tier1).
Denominators — rewrite-safety scored over 7 non-adequate items; calibration over 2 adversarial items in 2 pair-group(s).
_Caveat: the adversarial slice is thin and its matched pairs are split across train/test, so most are scored as singletons. A frozen, paired adversarial holdout (kept intact by `build_dataset`) would make calibration robustness a stronger signal._
