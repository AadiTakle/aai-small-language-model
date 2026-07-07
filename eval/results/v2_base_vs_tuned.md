# Eval results — Socratic Tutor Judge/Rewriter

Metric | base | tuned | Δ
---|---|---|---
Verdict accuracy | 51.5% | 89.7% | +38.2
Grounded reasoning (heuristic) | 83.8% | 100.0% | +16.2
Rewrite safety (heuristic) | 100.0% | 82.8% | -17.2
Schema compliance | 61.8% | 100.0% | +38.2
Calibration robustness | 20.0% | 60.0% | +40.0

_n = 68 gold items; rewrite-safety over non-adequate items only; calibration over the adversarial slice._
