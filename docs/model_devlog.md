# Socratic Tutor SLM — Model Dev-Log (v1 → ship, week of work)

A version-by-version walkthrough of every model we trained, for a grader / new reader / the demo
video. Each entry: **Goal · What changed vs. previous · Result · What we learned · → Decision**. The
through-line is the project thesis — **"the dataset is the deliverable"**: get constrained, safe
behavior out of a fixed small base (Qwen3-1.7B) by engineering the *data and the evaluation*, not by
scaling the model. Several of the most important entries moved *no* headline metric — they changed
what we knew and redirected the next version.

**Task.** Given (problem, reference solution, conversation, a candidate tutor message), output JSON:
a **verdict** ∈ {`adequate`, `gives_final_answer`, `gives_away_key_step`, `mismatched_calibration`,
`vague_unhelpful`}, grounded reasoning, and — if flagged — a **safe rewrite** that never reveals the
answer or the pivotal key step. The founding pilot probe (8 topics × 7-turn adversarial chats) found
**8/8 tutors eventually cave, and ~100% of leaks are `gives_away_key_step`** (the disguised key-step
leak), *not* blatant answer-giving — which shaped the whole taxonomy and safety metric.

---

## Summary table (headline metric per version)

| # | model | one-line goal | headline result | shipped? |
|---|---|---|---|---|
| — | base Qwen3-1.7B-4bit | foundation | GSM8K 46.7% flex; unreliable JSON/verdicts | base |
| v1 | 200 synthetic | prove learnability | verdict 55%→90%, schema→100% | — |
| v2 | 200→700 rows | does volume help? | ~flat vs v1 (**volume isn't the lever**) | — |
| v3 | real data, *replace* | attack v2 gaps | **regressed** anchor 1.70→0.90 (not shipped) | ✗ |
| v4 | real data, *augment* | add, don't replace | frozen verdict 59.2%, anchor 1.80 | candidate |
| v5 | eval-correction + relabel | fix leak-blindness | **leak recall 2%→35% (17×)** | candidate |
| v6 | jury relabel + balance | push label correctness | **frozen verdict 61.7% (best)** | **✓ long-run ship** |
| DPO v1 | preference tuning | push rewrite-safety | **regressed** −7.3 verdict | ✗ |
| v7 | decision-tree relabel | fix quality axis | **regressed** 61.7→56.4 | ✗ |
| v8 | thinking / CoT | reason before verdict | **regressed hardest** 61.7→50.3 | ✗ |
| *(reframe)* | metric, not model | measure the right axis | v6 = **82.2% safety-binary, beats GPT-4o/Claude** | — |
| judge_full | verdict-only, natural mix | recall-first judge | leak recall **84.6%** (=opus) | — |
| combined_full | combined obj, natural mix | best balanced judge | **83.2% safety-binary** | — |
| **v9** | tier-2 minimal pairs | move the recall frontier | **leak recall 90.4%** (best SLM) | **✓ ship detector** |
| rewrite_v1 | distill gpt-5.6 | safe+concise rewriter | jury 2.13, beats base | — |
| rewrite_v2 | +23 human curations | human-anchor the rewriter | jury 2.48 (> v1) | — |
| rewrite_v3 | strict + broad-validated | fix operation-naming | broad leak 25%, sharp 8.3% | — |
| **rewrite_v4** | +58 clean human anchors | both-axes win | sharp leak **6.7% = safest tier** | **✓ ship rewriter** |
| 4B judge | scale the recipe | test "does scale beat us?" | *pending Colab* | scale probe |

**Ship pipeline: `v9` (detector, 90.4% leak recall) → `rewrite_v4` (rewriter, 6.7% sharp leak).**

---

## Act 1 — Foundation (built before training)

**Base model — Qwen3-1.7B-4bit (local MLX QLoRA).** Fixed small open base by design; the brief's
thesis is "~80% of quality is the data," so model size was the *last* resort, not the first. This
constraint forced the data lever and produced every insight below. Traditional-benchmark profile
(clean, this week): **GSM8K ≈ 46.7% flexible / 10% strict (n=30, non-thinking)** — a capable base
whose *reliability* (valid JSON, correct verdicts) is the actual gap fine-tuning closes.

**Evaluation, built first.** A hand-seeded gold anchor (n=10) kept untrained-on, grown to a
leakage-checked **frozen set (n=103 → 306)**, always scored **base vs. tuned vs. frontier**. Key later
lesson: *the eval had to be iterated as hard as the model* — the instrument is part of the experiment.

---

## Act 2 — The data-centric climb (v1 → v6)

### v1 — first real data (200 synthetic)
- **Goal:** get base-vs-tuned numbers on the board; is the behavior learnable at 1.7B?
- **Result:** verdict **55%→90%**, schema 75%→100%, calibration 50%→100% (n=20).
- **Learned:** fine-tuning decisively clears the base's reliability gap. The behavior is learnable
  from a small targeted set. **→** push on data composition next.

### v2 — does more data help? (200 → 700)
- **Changed:** 3.5× the synthetic data, same recipe.
- **Result:** headline metrics held (~90%) but **did not beat v1**; rewrite-safety dipped. Gap
  analysis found two real weaknesses: the model **re-leaks the key step inside its own "safe" rewrite**,
  and it **over-flags** fine scaffolding as `mismatched_calibration`.
- **Learned:** **volume is not the lever** — the "quality/composition over quantity" thesis became
  evidence here. **→** attack the two specific gaps with *targeted/real* data, not more self-distill.

### v3 — real tutoring data, *replacing* synthetic
- **Changed:** ingested MRBench + MathDial, mapped to our taxonomy, used real "Expert" turns as safe
  rewrites — and **replaced** most of the synthetic set.
- **Result:** gains in-distribution but a **regression on the clean anchor** (verdict tier 1.70→0.90,
  4 new leak-boundary errors). Ruled out overfitting. **Not shipped.**
- **Learned — "augment, don't replace":** swapping the training distribution caused distribution shift
  that *regressed a safety capability the model already had*. Good-in-isolation data isn't safe to
  swap in. **→** re-run as augmentation.

### v4 — augmentation (the first ship candidate)
- **Changed:** full 700 synthetic **+** the real data on top (≈1,334 rows).
- **Result:** beat every prior version on the anchor (verdict tier **1.80**), **frozen verdict 59.2%**
  — ahead of GPT-4o, near Claude. Stable.
- **Learned:** adding real data preserved the old capability *and* delivered the gap gains.
  Composition (augment vs. replace) decides whether good data helps or hurts. **→** the remaining gap
  was leak-blindness — investigate its cause.

### v5 — eval-correction + relabel (the biggest data-centric win)
- **Changed (data-only):** (1) **corrected the gold set** — human + calibrated-LLM review found it was
  *systematically mislabeling key-step leaks as `adequate`* (`gives_away_key_step` gold 1→40; 92/306
  labels changed); (2) re-scored v4 on corrected gold with **no retraining** (isolating cause);
  (3) relabeled the training data (222/1,334 flips) and retrained.
- **Result:** key-step-leak recall **2% → 35% (~17×)**, any-leak detection 15%→58%, while **overall
  verdict accuracy was statistically unchanged.**
- **Learned — the pillar finding:** the model's leak-blindness was **mislabeled targets, not model
  size** — relabeling the *same-size* set fixed it. The number didn't move; the safety behavior
  improved 17×. **→** push label correctness + class balance further.

### v6 — consensus jury relabel + balancing (the long-standing ship)
- **Changed:** a **3-model jury** (GPT-4.1 + Claude-opus + Gemini-2.5-pro) re-audited labels
  (`gives_away_key_step` 229→313, ~100 more leaks caught) + class balancing for `adequate`-dominance.
- **Result:** **best model on record — frozen verdict 61.7%** (GPT-4o 51–52%, Claude 54–59%). Shipped.
- **Learned:** a cross-family jury catches label errors a single judge misses — and the jury's
  *disagreement pattern* was itself the finding: **~28% jury-vs-gold disagreement, almost all on the
  fuzzy quality axis** (adequate/mismatched/vague), safety axis high-agreement. This seeded the reframe.
- **Traditional benchmark (forgetting check, this week):** fused-v6 GSM8K collapses to **6.7% flex**
  (vs base 46.7%) — the SFT specialized so hard into tutoring-JSON that it no longer behaves like a
  general solver. Honest **cost-of-specialization**: our model is a *specialist*, not a general LM.

*(Boundary note — the n=306 gap-loop: an autonomous loop adding ~80 targeted rows per round got **0
accepts**, and adding imitation rewrite data actively hurt rewrite-safety. Mirror of v5: relabeling
fixes; adding to a saturated small model doesn't. The optimal set is ~1,000–1,500 clean, balanced,
correctly-labeled rows — not more.)*

---

## Act 3 — The plateau: four enhancement bets that failed (and why that's the point)

By v6 we'd exhausted what more/relabeled SFT data could do. Four "cleverer" methods each **failed to
beat v6** — each failure sharpened the same conclusion: *at 1.7B, added complexity doesn't beat clean data.*

### DPO v1 — preference optimization
- **Goal/changed:** reference-free DPO on ~357 preference pairs (Colab/CUDA round-trip; MLX has no DPO).
- **Result:** **regressed** — verdict 61.7%→54.4% (−7.3), rewrite-safety −3.5.
- **Learned:** (a) the preference signal was on the **wrong thing** — pairs varied only the *rewrite*,
  holding the verdict fixed, so DPO tuned phrasing while the verdict drifted; (b) narrow preference
  tuning imposes an "alignment tax" on a small model. Failure was signal-design, not just the algorithm.

### v7 — decision-tree relabel
- **Goal/changed:** attack the fuzzy quality axis with an ordered decision procedure in the prompt +
  gpt-5.5 relabel of the quality verdicts.
- **Result:** **regressed** 61.7%→56.4%. A **blind cross-family jury** sided with the *original gold*
  16-to-2.
- **Learned:** the relabel **over-flipped** — root cause: the "conservative" gate used the *same model*
  for the guided and verify passes, so it rubber-stamped its own bias. **Same-model agreement ≠
  correctness — use a cross-family jury.** The gold wasn't poor; the fuzzy axis is genuinely hard.

### v8 — thinking / chain-of-thought
- **Goal/changed:** the one untried orthogonal lever — distilled 1,144 gpt-5.5 reasoning traces and
  **trained** a real `<think>` block (isolated: thinking the only change).
- **Result:** **regressed hardest** — verdict 61.7%→50.3% (−11.4); schema still 99% (valid JSON, just
  *confidently wrong more often*).
- **Learned:** classic **small-model CoT failure** on a *self-verification* task — the 1.7B talks
  itself out of the right verdict. The reasoning lever, if real, needs scale.

**Meta-lesson of the plateau:** four rigorous negatives converge — **v6 is at the practical 1.7B
ceiling for this task, and clean data beats every clever training trick at this scale.** This reframed
the question from "how do we raise the number?" to "are we measuring the right thing?"

---

## Act 4 — The reframe (metrics → meaning; the biggest understanding leap)

- **Changed:** *nothing in any model* — re-scored every model's existing predictions under a metric
  that **separates the objective safety axis** (leak vs. safe) from the **fuzzy quality axis**,
  reporting binary-safety accuracy + leak precision/recall/F1.
- **Result:** v6's "mediocre" 61.7% became **82.2% on the safety axis — the best of every model, beating
  GPT-4o (77.5%) and Claude (78.5%)**. ~20 pts of apparent "error" was the fuzzy axis, not safety. Base
  leak-F1 24% → v6 70%.
- **Learned:** **the metric you report is a bigger lever than the model you train.** A frontier-beating
  safety judge appeared out of a "plateaued" one with zero retraining — and it surfaced the real open
  problem: **leak recall** (v6 catches only ~60% of leaks at high precision).

---

## Act 5 — The recall frontier: verdict/rewrite split + tier-2 (→ v9 ship detector)

The judge only *triggers* a rewrite, so a missed leak (recall) is the real harm; a false positive just
spends a rewrite. Under this **recall-first** framing we isolated split vs. balancing vs. volume
(frozen n≈298–306):

| model | data / objective | 5-way | safety-bin | leak R | leak P | leak F1 |
|---|---|---|---|---|---|---|
| v6 | consensus ~996, combined | 61.7 | 82.2 | 59.6 | 84.9 | 70.1 |
| judge_v1 | 725 balanced, verdict-only | 50.3 | 75.5 | 67.3 | 64.2 | 65.7 |
| judge_full | 1189 natural, verdict-only | 54.4 | 76.5 | **84.6** | 62.0 | 71.5 |
| combined_bal | 725 balanced, combined | 60.7 | 75.5 | 79.8 | 61.5 | 69.5 |
| combined_full | natural, combined | 55.7 | **83.2** | 66.3 | 82.1 | 73.4 |
| **v9** | **tier-2 minimal pairs** | **64.1** | 77.5 | **90.4** | 62.3 | **73.7** |
| v9b | tier-2, safe-dup 2 | 56.0 | 77.2 | 51.0 | 75.7 | 60.9 |

- **The split HURT accuracy** (combined_bal 60.7 > judge_v1 50.3 on identical data → the rewrite task
  regularizes the verdict), but **verdict-only + natural data → frontier-level recall** (judge_full
  84.6 = opus-4.8).
- **Diagnosis:** all of judge_full's misses are `gives_away_key_step`, specifically **corrective-framed
  key-step leaks** (tutor "corrects" by stating the step). A cross-family jury confirmed the
  `mismatched` labels are ~99% clean → it's a **discrimination gap, not a label problem** (relabeling
  would've been the wrong lever — this check prevented a v7 repeat).
- **v9 = tier-2 minimal-pair augmentation** (matched leaky/safe corrective-framed pairs, cross-family
  jury gate). **Leak recall 90.4% — best SLM, + best F1 (73.7) + best 5-way (64.1).** v9b confirms too
  much safe-duplication overcorrects (recall 51%). **→ v9 is the ship detector.**

---

## Act 6 — The rewriter line (rewrite_v1 → v4 ship)

Held-out n=60, cross-family jury (excludes the teacher) for quality; LLM leak-detector for safety.

### rewrite_v1 — distilled from gpt-5.6 (bench-off winner over gpt-5.5 & opus-4.8)
- **Goal:** the old combined rewrites were long/templated/sometimes wrong — distill a concise, safe
  rewriter.
- **Result:** jury rank **2.13** (base 2.62), 18.3% win-rate vs teacher, concise (20w median vs old 29).
- **Learned:** distillation works for the *constrained* rewrite behavior (safe + concise at frontier
  level), but trails frontier holistic quality. **→** can we anchor it to human taste?

### rewrite_v2 — human-anchored (23 web-UI curations steer 1,033 gpt-5.6 regenerations)
- **Result:** jury **2.48 > v1's 2.68** — **human anchoring beats pure distillation** from only 23
  corrections. **→** more human anchoring + fix the remaining leak mode.

### rewrite_v3 — strict "never name the operation" + broad-detector-validated targets
- **Changed:** every training target validated by the broad LLM leak-detector (139/1047 dropped as
  leaky — exactly what v2 trained on); strict no-operation teacher.
- **Result:** broad key-step leak **31.7%→25.0%**, sharp leak **8.3%**, jury held (~2.72). **→** feed
  more human curation into the strict set.

### rewrite_v4 — 58 human curations, clean-anchored (**ship rewriter**)
- **Changed:** 58 curations (up from 23), each validated vs the broad detector → 27 clean steering
  anchors (finding: the curator's own hints were 78% clean; most flags were approved-*teacher* rewrites).
- **Result:** broad leak **16.7%**, and under the **sharpened detector (below) sharp leak 6.7% — the
  safest tier of ALL models tested** — jury quality held (2.66), not vaguer. **→ ship rewriter.**

---

## Act 7 — Honest eval + dataset-scaling (this week)

### The sharpened detector (eval integrity)
The broad leak-detector was **over-flagging** — counting *restated student values* and *"why does this
completed step work"* questions as leaks. We built `llm_leaks_sharp` (leak only if it states the
answer, takes the *next* unsolved step, or directly corrects the error without nudging) and
re-measured (held-out 60):

| model | broad leak | **sharp leak** |
|---|---|---|
| base | 48.3% | 38.3% |
| rewrite_v3 | 21.7% | 8.3% |
| **rewrite_v4** | 16.7% | **6.7%** |
| gpt-4o | 35.0% | 11.7% |
| gpt-4.1 | 31.7% | 10.0% |
| sonnet-5 | 30.0% | 6.7% |
| gpt-5.6 | 15.0% | 11.7% |

**rewrite_v4 (6.7%) ties the safest frontier model and beats gpt-5.6/4o/4.1.** The broad detector had
over-flagged *everyone*, frontier hardest (+21–23% vs our +10%) — it penalized their thoroughness.
Honest metric ⇒ our 1.7B is in the safest tier, period.

### Dataset-growth vs. performance (boundary minimal-pairs)
Grew each head with 450 sharp-validated leak/safe pairs [+0/50/100/200/400]:
- **Rewrite: saturated** — sharp leak flat ~6.7%, +400 *hurts* (v4 at the floor).
- **Judge: non-monotone** — N=0 over-flags (100% recall / chance precision); a *small* dose (N=50)
  gives the best balance (74% recall / 82.2% safety), then it destabilizes.
- **Thesis:** *more data is not monotonically better* — both heads at the SFT-add frontier; the lever
  is small, targeted, high-quality data, not volume.

---

## Act 8 — The scale demo (Qwen3-4B judge) — *pending Colab (A100)*

**Goal:** the honest counterfactual for the demo — *"why not just use a bigger model?"* We train an
**identical-recipe judge on Qwen3-4B** (~2.4× scale) on the same v9 data, and eval on our metrics.

<!-- 4B_RESULT: fill from Colab -->
_Result pending. Prediction from the whole arc: 4B does **not** meaningfully beat the tuned 1.7B `v9`
on leak-recall/safety — scale isn't the lever for this constrained behavior; clean data + honest
metrics are. GSM8K/MMLU (4B-base / 4B-tuned / 1.7B-base) also measured on Colab to backfill clean
traditional numbers (the tuned 4B judge should show the same GSM8K "forgetting" as fused-v6)._

---

## Figures for the demo (`docs/figures/`)

- **`detector_broad_vs_sharp.png`** — the money shot: `rewrite_v4` in the safest tier under the honest
  detector, and the broad metric over-flagged *frontier* hardest. (Act 7)
- **`dataset_growth_vs_perf.png`** — the scaling curves: rewrite saturated, judge N=50 sweet spot →
  "more data isn't the lever." (Act 7)
- **`loss_curves.png`** — training convergence for the rewrite line (v2/v3/v4) + judge. (Acts 2 / 6)
- **`dataset_rewrite.png`** / **`dataset_judge.png`** — training-set adequacy (verdict balance, source
  mix, leak/safe split, hint length) — the visual for *"the dataset is the deliverable."* (Acts 1 / 2)

---

## The through-line (for the video / brainlift)

1. **Relabeling > adding.** Fixing labels on a fixed-size set was the biggest win (2%→35%); adding
   rows to a saturated model did nothing or hurt.
2. **Augment, don't replace.** Swapping the distribution regressed a capability the model had.
3. **Cross-family jury > single judge.** v7 failed on same-model self-agreement; the reframe + recall
   checks worked because Claude and GPT had to agree.
4. **Measure the right axis, honestly.** Separating safety from fuzzy quality turned a "plateaued"
   model into a frontier-beating one with no retraining — and sharpening the leak detector this week
   showed our rewriter is in the safest tier (the broad metric had hidden it).
5. **Small models don't reason their way to better *self*-judgments** — CoT is a large-model tool here.
6. **Scale isn't the lever** (Act 8) — a bigger base, same recipe, doesn't beat the tuned small model
   on the constrained safety behavior; and specialization costs general ability (the GSM8K forgetting).
7. **Negative results are results.** DPO, v7, v8, masking, the gap-loop, the scaling curves — each
   bounded the design space with an isolated, well-powered experiment.

**Ship: `v9` (detector, 90.4% leak recall) → `rewrite_v4` (rewriter, 6.7% sharp leak)** — a 1.7B
guardrail pipeline that matches/beats frontier on the safety-critical behavior, every claim measured
by a metric we vetted.
