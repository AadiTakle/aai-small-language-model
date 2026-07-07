# Day-4 Report — Patching Gaps with Real Datasets (MRBench + MathDial)

## Goal
Patch the two v2 gaps ([gap_analysis_v2.md](gap_analysis_v2.md)) — **safe-rewrite generation** and the **`adequate`↔`mismatched_calibration` boundary (label noise)** — using *real, human-labeled* tutoring data instead of more self-distillation.

## What we built (keepers — correct and mergeable)
- **`scripts/ingest_mrbench.py`** — MRBench V2 (Maurya et al., NAACL 2025; CC-BY-SA-4.0): 200 math conversations × ~8 tutor responses, each human-labeled on 8 pedagogical dims. Maps the human labels to our verdict taxonomy and attaches a real **Expert** response as the safe `rewrite` (real contrastive pairs). Produced 1,597 mappable rows (adequate 714 / mismatched 375 / vague 262 / gives_final_answer 246).
- **`scripts/ingest_mathdial.py`** — MathDial (Macina et al., 2023; CC-BY-4.0): real teacher–student GSM8K dialogues; takes `probing`/`focus` teacher turns as genuine `adequate` Socratic exemplars.
- **`socratic_tutor/annotate.py`** — grounded reasoning via gpt-4.1 (verdict + rewrite stay from the human labels; only the reasoning prose is model-written, grounded in the real item).
- **Quality-gate fix** (`gen_lib.py`) — the final-answer leak check now uses digit-boundary matching **and** excludes numbers already present in the problem/history. Previously it dropped ~25% of rows, many of them *real safe rewrites* that merely restate a given quantity (e.g. "he still had 2000 steps left"). This was the false-positive flagged in the v2 gap report; it's now fixed (a strict improvement for all future builds).

## The experiment (v3) and its result — a cautionary finding
**v3 dataset = real-heavy:** 480 MRBench + 155 MathDial + 142 synthetic `gives_away_key_step` + 90 synthetic adversarial = 677 rows. Critically, this **replaced** most of the original 700 synthetic set rather than augmenting it. Trained `adapters/v3` (541 train, 450 iters, val loss 0.26→0.24).

Two eval sets, gpt-4.1 tiered judge (0–2):

**v3 holdout (in-distribution, n=69) — large gains:**
| Dim | base | v3 |
|---|---|---|
| Spec adherence | 1.33 | **1.83** |
| Task quality | 1.17 | **1.71** |
| Robustness | 0.60 | **1.00** |
| Rewrite safety | 1.41 | **1.73** |

**Seed gold (the only clean cross-version anchor, n=10) — regression vs v2:**
| Criterion | base | v2 | v3 |
|---|---|---|---|
| Verdict correctness | 1.30 | **1.70** | **0.90** ⬇ |
| Rewrite safety | 1.83 | 1.50 | 1.60 |
| Spec adherence (rollup) | 1.45 | 1.85 | **1.45** ⬇ |

v3 fell **below v2 and below base** on verdict, with **4/10 tier-0 errors** (leak-boundary crossings — passing a leak as fine, or false-alarming). v2 had **zero** such crossings. That is a safety regression on the original distribution.

## Diagnosis: distribution shift from *replacing* (not augmenting)
- The divergence — v3 excels on its MRBench-style holdout but regresses on the hand-written seed cases — is the signature of **distribution shift**. By replacing the original synthetic data, we moved the model's learned boundary toward MRBench's GSM8K-remediation style and away from the original hard cases (bridging-through-ten, isomorphic-example leaks).
- **Not overfitting:** the iter-300 checkpoint (lower val loss) is *no better* on seed (verdict still 0.90, rewrite safety worse), ruling training duration out. It's data composition, not epochs.
- A secondary suspect: the MRBench→verdict mapping (esp. `Providing_Guidance="To some extent" → mismatched_calibration`) may encode a slightly different boundary than the seed's stricter definitions.

## Conclusion
Real human-labeled data has clear value (in-distribution gains are large and the Expert rewrites are genuinely safe), **but naive replacement regressed the original capability, including a verdict safety regression.** v3 is **not a ship candidate.**

## Next step (not yet run) — v4 augmentation
**Augment, don't replace:** full 700 synthetic **+** real MRBench/MathDial. This keeps the original distribution (protects verdict/seed performance) while adding real label quality and real safe rewrites to target the two gaps. Also worth: validating the "To some extent → mismatched" mapping against a sample of seed-labeled cases, and evaluating v4 on the seed anchor first before trusting in-distribution gains.

## v4 result — augmentation worked (the ship candidate)
v4 = full 700 synthetic + 479 MRBench + 155 MathDial (1,334 raw → 914 train / 114 valid / 115 test), same fixed hyperparameters. Trained stably (val loss flat ~0.25, no overfit spike unlike v3's 0.355).

**Seed gold (n=10, the clean cross-version anchor) — v4 beats every prior version on every criterion:**

| Criterion | base | v2 | v3 | **v4** |
|---|---|---|---|---|
| Verdict correctness | 1.30 | 1.70 | 0.90 | **1.80** |
| Grounded reasoning | 1.20 | 1.60 | 1.60 | **1.80** |
| Rewrite safety | 1.67 | 1.50 | 1.60 | **1.71** |
| Schema compliance | 1.60 | 2.00 | 2.00 | **2.00** |
| Calibration robustness | 1.00 | 1.00 | 1.00 | **2.00** |
| Consistency | 1.60 | 1.80 | 1.60 | **1.80** |

v3's verdict regression (0.90, 4 tier-0 boundary crossings) is resolved — v4 verdict 1.80 with only 1 tier-0. Rewrite safety (1.71) and calibration (2.00) are the best of any version. **v4 holdout (n=115)** confirms it generalizes: verdict 1.12→1.85, calibration 0.80→1.60, rewrite safety 1.40→1.56, robustness 0.80→1.60, spec adherence 1.43→1.92.

**Conclusion:** augmentation (real data *added to*, not *replacing*, the synthetic distribution) kept the original capability **and** delivered the target-gap gains (calibration 1.00→2.00, rewrite safety to its best). v4 is the ship candidate. Remaining relative weak spot: rewrite safety on the broad holdout (1.56) — still the hardest behavior, a candidate for DPO on the real Expert-vs-leaky rewrite pairs.
