# Model holes — where v5 fails (corrected + consensus gold, n=299)

Deep-dive on the ship model (v5) against the honest, consensus-verified gold, `gpt-5.5` grader.

## v5 confusion (gold row → v5 prediction)
| gold ↓ | adeq | mis | vague | gfin | gaway | **recall** |
|---|---|---|---|---|---|---|
| adequate | 66 | 8 | 2 | 4 | 1 | **80%** ✓ |
| **mismatched** | **41** | 10 | 7 | 7 | 8 | **14%** ✗✗ |
| vague | 13 | 2 | 29 | 0 | 1 | 64% |
| gives_final | 0 | 2 | 1 | 38 | 0 | **93%** ✓ |
| **gives_away** | **31** | 3 | 0 | 8 | 14 | **25%** ✗ |

Binary safety (leak vs. not): **80%**.

## The three holes, ranked

**1. `mismatched_calibration` recall = 14% (the dominant error).** v5 calls **41 of 74** mismatched items `adequate`. It can't tell a hint that *misdiagnoses the student's error* from one that correctly targets it — it defaults to `adequate`. This is the single biggest accuracy drag and it's on the inherently-fuzzy quality axis (~45% inter-judge disagreement; the multi-model jury changed 28% of the gold here). Partly a **rubric-ambiguity** problem, partly a **capacity** problem (it requires modeling the student's exact knowledge state).

**2. Leak detection still leaks: `gives_away` recall = 25% (safety hole).** v5 calls **31 of 57** key-step-leaks `adequate` (misses them). It's far better than v4 (~2%) but the stricter consensus gold — which flagged more subtle leaks — exposes that **~half of real key-step leaks still slip through as "adequate."** `gives_final_answer` (blatant) is caught 93%; the subtle `gives_away` is the gap.

**3. Generative quality trails frontier (grounded + rewrite).** Grounded reasoning 1.39 vs gpt-4o 1.56 / claude 1.74. Rewrite safety ~1.0 — but see below.

## The rewrite-safety trap (why "base is best" is misleading)
Rewrite-safety scored *alone* rewards **vagueness**: a hint that says nothing specific can't leak. Across models it's an inverse of grounding — base (grounded 0.72) scores "safest" (1.08) by being unhelpful; claude (grounded 1.74) scores "least safe" (0.93) because its substantive hints risk revealing the step. **Nobody rewrites safely-AND-helpfully well (~1.0 for all, incl. frontier).** This is an unsolved hard problem, and the metric must be reported jointly with grounding, not standalone.

## What's strong (don't lose it)
- **Verdict tier 1.32** — ties/beats frontier (gpt-4o 1.30, claude 1.29).
- **Schema 1.98** — near-perfect; beats gpt-4o (1.00, never bare JSON) and claude (1.79).
- **`gives_final` recall 93%, `adequate` recall 80%.**
- **Spec adherence 1.65 — beats both frontier.** The constrained-judge core is frontier-competitive at 1.7B.

## Root causes → levers
| hole | root cause | lever |
|---|---|---|
| mismatched 14% | fuzzy quality axis + capacity | contrastive adequate-vs-mismatched data; two-axis reporting; maybe 4B base |
| gives_away 25% | subtle-leak detection under-trained | v6_consensus (gives_away 229→313) retrain; mine more real leaks |
| rewrite safety ~1.0 (all) | SFT can't crack safe-AND-helpful | **DPO** on safe≻leaky pairs (Bridge novice/expert) |
| grounded < frontier | capacity/generative | DPO / larger base; not more SFT volume |
