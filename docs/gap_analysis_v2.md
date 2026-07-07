# Model Gap Analysis — v2 tuned (Qwen3-1.7B QLoRA)

**Basis:** the judged tiered eval (gpt-4.1 judge) on the clean held-out `all_test` (n=68, 0 train/test leakage) plus the seed gold (n=10), per-item data in `eval/results/v2_rubric.json`. Scale is 0–2 mean tier per criterion.

## Headline

The tuned model is a real, broad win — it beats base on **all four** Appendix A dimensions (spec adherence 1.44→1.95, task quality 1.43→1.62, robustness 0.40→1.20, consistency 1.79→1.93) and **schema compliance is perfect (2.00/68)**. Its verdicts are also *safely* wrong when wrong (see below). But two concrete gaps remain, and they map cleanly onto the two halves of the task:

1. **Safe-rewrite generation (the Rewriter half)** — the flagship gap. ~34% of rewrites are unsafe or under-delivered.
2. **The `adequate` ↔ `mismatched_calibration` boundary (the Judge half's one soft spot)** — the model over-flags genuinely-fine scaffolding as a calibration problem.

---

## Gap 1 — Safe-rewrite generation (severity: high)

**Numbers.** Rewrite safety is flat base→tuned (1.46→1.47) and low: of **58** non-adequate items, **20 rewrites failed** the judge — **11 outright leaks (tier-0)** + 9 partial/ungrounded (tier-1). Only 38/58 (66%) were clean. This is the single metric the fine-tune did *not* move.

**The pattern (this is the important part).** The model almost always gets the *verdict* right — it correctly recognizes the candidate leaks — and then **re-commits the same leak inside its own "guiding" rewrite.** It produces a question, but the question embeds the key step. Three real tuned outputs from the held-out set:

| Problem | Key step (must NOT be revealed) | Model's rewrite (leaks) |
|---|---|---|
| `P(A and B)`, A,B independent, .3 & .5 (9-12) | multiply the probabilities | "…what do you get when you **multiply them**?" |
| `9 + 6` (K-2) | bridge through ten: split 6 into 1+5 to make 10 | "You've spotted the perfect 10. Now that you have **10 and 5**, what do you get when you combine them?" |
| `96 ÷ 4` (3-5) | split 96 into 80+16 | "since 4 goes into 9 two times… what is 96÷4 if you **split 96 into 80 and 16**?" |

In each case the verdict is correct but the rewrite hands over the exact operation/decomposition — often having already *performed* the key step (turning 9+6 into "10 and 5"). It has learned the *shape* of a Socratic question but not the *discipline* of withholding the pivotal step.

**Where it's worst (band skew).** 9-12 (7 failures) and 3-5 (6) dominate — multi-step / decomposition problems, where the "key step" is a specific technique that's tempting to name. K-2 (2) and 6-8 (3) are better.

**Verdict-error cascade.** 2 of the failures had gold verdict `adequate`: the model wrongly judged a fine message as non-adequate, *then* generated a needless rewrite that leaked. So Gap 2 (below) manufactures extra Gap-1 failures.

**Why:** this is the hardest behavior in the whole project (the gap-probe research showed even prompted frontier models leak here), and the v1/v2 data was thin on *contrastive* safe-vs-leaky rewrite pairs. The model saw "rewrite = a warm question" but not enough "…and the question must not contain the step."

**Fix (Day-4 data):** targeted rewrite data — for each leaky candidate, pair a **tier-0 leaky rewrite with a tier-2 safe rewrite of the same problem**, explicitly contrasting "question that embeds the operation" vs "question that makes the student choose the operation." Weight toward 9-12/3-5 multi-step. This is also the natural **DPO** target (preference pairs: safe ≻ leaky rewrite).

---

## Gap 2 — The `adequate` ↔ `mismatched_calibration` boundary (severity: medium)

**The model is over-eager to see a calibration problem in fine scaffolding.** This single boundary explains failures across four criteria:

- **Verdict:** 7 errors total, and *all* are same-family (0 boundary crossings). The dominant confusion is **`adequate` → `mismatched_calibration`** (4 of 7) — it labels genuinely-adequate messages as mis-calibrated.
- **Calibration robustness (1.20):** on the 5 adversarial items, both misses are the *same* pattern — gold `adequate`, predicted `mismatched_calibration`.
- **Grounded reasoning (1.78):** 8 of 11 grounding failures are on `adequate` items — justifying *why a message is fine* is inherently less "quotable" than quoting the phrase that leaks, so the model's reasoning goes generic exactly here.
- **Consistency (1.93):** the drift items cluster on `adequate` — the model is genuinely unsure at this boundary, so repeated samples flip between `adequate` and `mismatched_calibration`.

**Why:** the taxonomy's subtlest distinction, and likely under-represented / softly-labeled in the training data (borderline calls are where teacher labels themselves are noisiest).

**Fix (Day-4 data):** more clean `adequate` exemplars + hard **matched pairs** (a genuinely-adequate message vs. a surface-similar truly-miscalibrated one on the *same* problem), with reasoning that names the concrete evidence for "this is calibrated to where the student is." Bias the default toward `adequate` when a message scaffolds without leaking.

---

## What is NOT a gap (don't spend Day-4 here)

- **Schema compliance: 2.00/68 — solved.** The base model's core failure (invalid JSON ~38% of the time) is fully closed. No further work.
- **Verdict boundary-safety:** 0 tier-0 verdict errors — the model **never passed a leak off as adequate, and never false-alarmed a clean message as a leak.** Every verdict error is a within-family severity mislabel. For a safety-critical judge, this is the profile you want.
- **Consistency (1.93)** and **verdict accuracy (1.90)** are already strong.

---

## Instrument gaps (the eval itself, not the model)

These limit how much we can trust the two weakest cells and should be fixed alongside the data work:

1. **Adversarial slice is thin and broken:** only 5 `calibration_adversarial` items survive in `all_test`, and their matched pairs were split across train/test by the random shuffle, so they score as singletons. Calibration robustness is measured on sand. **Fix:** a frozen, *paired* adversarial holdout kept intact by `build_dataset` (split by pair-group, never trained on).
2. **No frozen, version-independent holdout:** each dataset version re-splits, so `v1_test` leaked into `v2`'s train (harmless when produced, but not reproducible-clean). The seed gold (n=10, hand-written, 0 leak) is the only stable yardstick — formalize a larger frozen gold set.
3. **Rewrite-safety denominator varies:** base is scored over fewer valid rewrites than tuned, so base's rewrite-safety isn't apples-to-apples with tuned. Report `rewrite_safety_n` alongside (already in the JSON).

---

## Prioritized Day-4 plan

1. **Targeted safe-rewrite data + DPO** (attacks Gap 1, the flagship) — contrastive safe/leaky rewrite pairs, 9-12/3-5 weighted.
2. **`adequate`-vs-`mismatched_calibration` pair data** (attacks Gap 2, and removes the verdict-error cascade into Gap 1).
3. **Frozen paired adversarial holdout in `build_dataset`** (makes robustness measurable before iterating on it).
4. Re-run the judged tiered eval; success = rewrite safety and robustness rise without regressing the already-solved schema/verdict-safety cells.
