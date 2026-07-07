# Tiered rubric eval — Socratic Tutor Judge/Rewriter

_Judge: **OpenAI gpt-4.1**. Scale 0-2 (mean tier per criterion). n=115 gold items._

## Per-criterion (0-2 mean)
Criterion | base | tuned | Δ
---|---|---|---
Verdict correctness | 1.12 | 1.85 | +0.73
Grounded reasoning | 1.13 | 1.70 | +0.57
Rewrite safety | 1.40 | 1.56 | +0.16
Schema compliance | 1.74 | 1.99 | +0.25
Calibration robustness | 0.80 | 1.60 | +0.80
Consistency | 1.81 | 1.89 | +0.08

## Appendix A rollup (0-2 mean per dimension)
Dimension | base | tuned | Δ
---|---|---|---
Spec adherence | 1.43 | 1.92 | +0.49
Task quality | 1.26 | 1.63 | +0.37
Robustness | 0.80 | 1.60 | +0.80
Consistency | 1.81 | 1.89 | +0.08

## Error analysis
The tuned model's remaining weak cells: **Verdict correctness** 1.85 (1×tier0, 15×tier1); **Grounded reasoning** 1.70 (4×tier0, 26×tier1); **Rewrite safety** 1.56 (9×tier0, 12×tier1); **Schema compliance** 1.99 (0×tier0, 1×tier1); **Calibration robustness** 1.60 (0×tier0, 0×tier1); **Consistency** 1.89 (0×tier0, 13×tier1).
Denominators — rewrite-safety scored over 68 non-adequate items; calibration over 11 adversarial items in 10 pair-group(s).
