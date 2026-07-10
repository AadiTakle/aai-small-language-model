# Socratic Tutor SLM — Experiment & Learnings Report

*Every experiment, why we ran it, and what we understood from it — model by model, decision by
decision. The through-line is deliberately **the growth of understanding**, not the eval number.
Several of the most important entries below moved no metric at all; they changed what we knew.*

---

## 0. How to read this

The project's thesis is **"the dataset is the deliverable"**: get reliable, constrained behavior
out of a small model (Qwen3-1.7B) by engineering the *data and the evaluation*, not by scaling the
model. Read that way, the arc has three acts:

1. **The climb (v1→v6):** learning what kind of *data* makes a small judge good.
2. **The plateau (DPO, v7, v8):** four enhancement bets that all failed to beat v6 — and taught us
   *why*, which is the more valuable output.
3. **The reframe (metrics → meaning):** discovering the "mediocre" model was being measured on the
   wrong axis, and that the real open problem is a precision/recall operating point, not capability.

A recurring pattern: **the negative results were the most informative experiments.** Each is logged
here as `What · Why · Result · What we learned`.

---

## 1. Foundational decisions

### 1.1 Base model: Qwen3-1.7B-4bit, local MLX
- **What:** A 1.7B Qwen3 instruct model, 4-bit, fine-tuned locally on Apple Silicon (MLX QLoRA).
- **Why:** The brief fixes a small open base and the thesis "≈80% of outcome quality is the data."
  Fine-tuning only earns its place where a well-prompted base *can't* already do the behavior.
- **Result:** Held fixed through the entire arc. Every gain came from data, never from model size.
- **Learned:** Committing to a fixed small base *forces* the data lever — and made model size the
  last resort, not the first. This constraint is what produced every real insight below.

### 1.2 The task & the 5-way schema
- **What:** A **judge + rewriter**. Given (problem, solution, conversation, candidate tutor message),
  output strict JSON: a **verdict** ∈ {`adequate`, `gives_final_answer`, `gives_away_key_step`,
  `mismatched_calibration`, `vague_unhelpful`}, grounded reasoning, and — if not adequate — a safe
  rewritten hint that never reveals the answer or the key step.
- **Why:** A pilot probe (below) showed the real failure isn't blanket answer-giving; it's the subtle
  *key-step* leak. Splitting `gives_final_answer` from `gives_away_key_step` encodes that.
- **Result:** Locked as the single source of truth (data rubric = eval criterion = spec).
- **Learned (only fully understood much later):** the 5 labels secretly span **two different axes** —
  an objective **safety** axis (does it leak?) and a fuzzy **quality** axis (adequate/mismatched/
  vague). Conflating them into one accuracy number is what later made a strong model look weak (§5).

### 1.3 Thinking off (`ENABLE_THINKING=False`)
- **What/Why:** Disabled Qwen3's `<think>` trace so the output is a single clean JSON object.
- **Learned:** A pre-training constraint chosen to serve strict schema compliance — and, much later,
  the thing v8 tried to reverse, with instructive consequences (§4.3).

### 1.4 The evaluation (built before training)
- **What:** A hand-seeded gold set (n=10) that stays *untrained-on* as the clean cross-version
  anchor, growing to a leakage-checked **frozen set** (n=103 → 306), scored on a 6-criterion 0–2
  rubric, always **base vs. tuned vs. a frontier model**.
- **Why:** The brief mandates an eval built before training. We discovered the hard way that the
  *eval itself* had to be iterated nearly as hard as the model (§3.5).
- **Learned:** The instrument is part of the experiment. A held-out, leakage-checked, frontier-
  anchored eval is what let every later "did it actually help?" question be answered honestly.

### 1.5 The pilot probe (why the taxonomy is shaped the way it is)
- **What:** 8 topics × 7-turn adversarial "get the answer out of the tutor" conversations vs. a strong
  model.
- **Result:** **8/8 tutors eventually caved**, and **100% of violations were `gives_away_key_step`** —
  zero were blatant `gives_final_answer`.
- **Learned:** The dangerous leak is the *disguised* one (a key step handed over mid-explanation),
  which set data-generation weighting toward that class and shaped the rewrite-safety eval to catch
  isomorphic-example leaks, not just literal numbers. This insight recurs at the very end (§6).

---

## 2. The data-centric climb (v1 → v6)

### 2.1 v1 — first real data (200 synthetic examples)
- **Why:** Get real base-vs-tuned numbers on the board.
- **Result:** verdict 55%→**90%**, schema 75%→100%, calibration 50%→100% (n=20).
- **Learned:** Fine-tuning clears the base model's reliability gap (invalid JSON, wrong verdicts)
  decisively. The behavior *is* learnable from a small, targeted set.

### 2.2 v2 — does more data help? (200 → 700)
- **Why:** Test the quantity-vs-quality question directly.
- **Result:** Headline metrics held (verdict ~90%, schema 100%) but **v2 did not clearly beat v1**;
  rewrite-safety even dipped. A gap analysis pinpointed two real weaknesses: (a) the model *re-leaks
  the key step inside its own "safe" rewrite*, and (b) it over-flags fine scaffolding as
  `mismatched_calibration`.
- **Learned:** **Volume is not the lever.** 3.5× the data didn't move the needle — this is where the
  "quality/composition over quantity" thesis stopped being a slogan and became evidence, and it
  redirected all further work toward *targeted* data.

### 2.3 v3 — real human data, but *replacing* synthetic
- **What:** Ingested real tutoring data (MRBench, MathDial), mapped human labels to our taxonomy, used
  real "Expert" responses as genuine safe rewrites — and **replaced** most of the synthetic set.
- **Why:** Attack v2's two gaps with real data instead of more self-distillation.
- **Result:** Big gains *in-distribution* (MRBench-style holdout) but a **regression on the clean seed
  anchor** (verdict tier 1.70 → **0.90**, with 4 leak-boundary errors where v2 had zero). We ruled out
  overfitting (a lower-loss checkpoint was no better). **v3 was explicitly not shipped.**
- **Learned — the "augment, don't replace" finding:** replacing the training distribution caused
  distribution shift that *regressed a safety capability the model already had*. New data being good
  in isolation doesn't make it safe to swap in. This is one of the two pillars of the whole arc.

### 2.4 v4 — augmentation (the ship candidate)
- **What:** Full 700 synthetic **+** the real data on top (≈1,334 rows). Same hyperparameters as v3.
- **Result:** Beat every prior version on the seed anchor (verdict tier **1.80**; calibration
  1.0→2.0), frozen verdict accuracy **59.2%** — ahead of GPT-4o, near Claude. Trained stably.
- **Learned:** Directly confirmed §2.3: *adding* real data preserved the original capability **and**
  delivered the target-gap gains. Composition (augment vs. replace) determines whether new data helps
  or hurts, independent of the data's quality.

### 2.5 v5 — the eval-correction + relabel (the biggest data-centric win)
- **What:** Three linked steps: (1) **corrected the gold set** — human + calibrated-LLM review found
  it had been *systematically mislabeling key-step leaks as `adequate`* (`gives_away_key_step` gold
  1→40; 92/306 labels changed); (2) **re-scored v4 on the corrected gold** with no retraining —
  isolating the cause; (3) **relabeled the training data** to the corrected standard (222/1,334 flips)
  and retrained — **data-only change**.
- **Why:** v4 was leak-blind (`gives_away_key_step` recall 2%). Was that a 1.7B capability limit or a
  label problem? Step (2) answered it *before* spending a retrain.
- **Result:** key-step-leak recall **2% → 35%** exact (**~17×**), any-leak detection 15% → 58% — while
  **overall verdict accuracy was statistically unchanged**.
- **Learned — the pillar finding:** the model's leak-blindness was **mislabeled training targets, not
  model size.** Relabeling the *same-size* set fixed it. This is the single strongest confirmation of
  the project thesis, and the reason "the number didn't move but we learned a lot" is literally true
  here: aggregate accuracy was flat while the safety-critical behavior improved 17×.

### 2.6 The prompt-masking ablation (negative, informative)
- **What/Why:** ~90% of the training loss lands on the prompt, not the target JSON. Hypothesis:
  masking the prompt (loss on the assistant JSON only) should sharpen the signal.
- **Result:** Leak recall **regressed** under masking (58% → 35%).
- **Learned:** The "wasted" full-sequence loss is doing real work — it's a mini in-domain LM objective
  that helps the downstream judgment. A plausible mechanistic hypothesis, falsified by experiment
  rather than assumed. We kept the text/no-mask format.

### 2.7 v6 — consensus relabel + balancing (the ship model)
- **What:** A **3-model jury** (GPT-4.1 + Claude-opus + Gemini-2.5-pro) re-audited the training labels
  (`gives_away_key_step` 229 → 313, catching ~100 more mislabeled leaks) and the gold set; plus class
  balancing to fix the `adequate`-dominance bias. Retrained → **v6**.
- **Why:** Push label correctness and class balance further — the two levers v5 proved matter.
- **Result:** v6 is the **best model on record**: frozen verdict **61.7%** (beating v4/v5, GPT-4o
  51–52%, Claude ~54–59% depending on grader), the shipped adapter.
- **Learned:** A multi-model jury catches label errors a single judge (or single human pass) misses —
  and, critically, the jury's *disagreement pattern* was itself a finding: **28% of jury-vs-gold
  disagreement, almost all on the fuzzy quality axis** (adequate/mismatched/vague), while the safety
  axis was high-agreement. This is the empirical seed of the reframe in §5.

### 2.8 The n=306 gap-loop — the "SFT-add frontier" (negative)
- **What:** An autonomous loop that picks a weak metric, generates ~80 targeted examples, retrains,
  and accepts/reverts on paired statistical significance against the frozen anchor.
- **Result:** At the higher-powered n=306, **0 accepts** — adding targeted rows did nothing, and
  *adding imitation rewrite data actively hurt* rewrite-safety.
- **Learned — the mirror of v5:** relabeling existing rows fixed a 17× gap (§2.5), but *adding* rows
  to an already-saturated small model did nothing or regressed it. Together these bound the data
  lever precisely: **correctness and composition move the needle; raw volume does not.** The optimal
  set is ~1,000–1,500 *clean, balanced, correctly-labeled* rows — not more.

---

## 3. The plateau — four enhancement bets that failed (and why that's the point)

By v6 we had a strong data-centric model and had exhausted what *more/relabeled SFT data* could do.
The next four experiments each tried a "cleverer" training method. **All four failed to beat v6** —
and each failure sharpened the same conclusion: at 1.7B, added complexity doesn't beat clean data.

### 3.1 DPO v1 (preference optimization)
- **Why:** Rewrite-safety had plateaued; DPO was the sanctioned lever to push it.
- **What:** Reference-free DPO on ~357 preference pairs, via a Colab/CUDA round-trip (MLX has no DPO
  trainer).
- **Result:** **Regressed** — verdict 61.7% → 54.4% (−7.3), rewrite-safety −3.5.
- **Learned:** Two lessons. (a) The **preference signal was attached to the wrong thing** — pairs
  varied only the *rewrite*, holding the verdict fixed, so DPO tuned rewrite phrasing while the
  verdict drifted. (b) Narrow preference tuning on a small model imposes an "alignment tax" that
  degrades untargeted capabilities. Don't ship; the failure was signal-design, not just the algorithm.

### 3.2 v7 — decision-tree relabel
- **Why:** Attack the quality-axis error (fuzzy `mismatched`/`adequate` boundary) by adding an
  explicit ordered decision procedure to the prompt and relabeling the quality-axis verdicts with
  gpt-5.5.
- **Result:** **Regressed** — verdict 61.7% → 56.4%. Then a **blind cross-family jury** (Claude +
  gpt-4o) adjudicated the v6-vs-v7 disagreements: it sided with the *original gold* 16-to-2 and matched
  the frozen gold more than either model.
- **Learned:** The relabel **over-flipped** — and the root cause was a method flaw: the "conservative"
  gate used the *same model* (gpt-5.5) for both the guided and verify passes, so agreement
  rubber-stamped its own bias. **Same-model agreement ≠ correctness — use a cross-family jury.** Also:
  the gold was *not* poor; the fuzzy axis is genuinely hard (frontier models split ~60% of the time).

### 3.3 v8 — thinking / chain-of-thought
- **Why:** The single untried, orthogonal lever — teach the model to *reason* before the verdict.
  Probes confirmed inference-time thinking couldn't be tested on the (thinking-off-trained) v6, so we
  distilled 1,144 gpt-5.5 reasoning traces and **trained** v8 with a real `<think>` block. Isolated:
  same data/prompt/config, thinking the only change.
- **Result:** **Regressed hardest** — verdict 61.7% → 50.3% (−11.4). Schema stayed clean (99%), so it
  emits valid JSON — it's just *confidently wrong more often*.
- **Learned:** A classic **small-model chain-of-thought failure** — a 1.7B generates a plausible-but-
  shaky trace and talks itself out of the correct verdict. *(Honest caveat, per the literature: this
  is task-dependent, not a universal law — CoT can help small models on some judging tasks. It hurts
  ours because the task is self-verification, which is sycophancy-prone. See the Brainlift.)* The
  reasoning lever, if it's real, needs scale.

### 3.4 The meta-lesson of the plateau
Four rigorous negatives (DPO, v7, v7-audit, v8) converge: **v6 is at the practical ceiling of a
1.7B for this task, and clean data beats every clever training trick at this scale.** That is a
genuine, defensible finding — and it reframed the question from "how do we raise the number?" to
"are we even measuring the right thing?"

---

## 4. The reframe — from metrics to meaning (the biggest understanding leap)

- **What:** Re-scored *every* model's existing predictions under a metric that **separates the
  objective safety axis** (leak vs. safe) **from the fuzzy quality axis** — reporting binary-safety
  accuracy and leak-detection precision/recall/F1. No model was retrained; only the scoring changed.
- **Why:** The jury-disagreement pattern (§2.7) + the v7 audit both said the quality axis is near-
  irreducibly ambiguous. If ~half the "error" lives in a distinction even Claude and GPT-4o can't
  agree on, the 5-way accuracy is measuring noise as much as skill.
- **Result:** v6's "mediocre" 61.7% became **82.2% on the safety axis — the best of every model,
  beating GPT-4o (77.5%) and Claude (78.5%).** ~20 points of apparent "error" was the fuzzy axis, not
  safety mistakes. And the model demonstrably *learned* safety: base leak-F1 24% → v6 70%.
- **Learned:** **The metric you report is a bigger lever than the model you train.** The single most
  important shift in the project happened with *zero* change to any model — we changed what we
  measured and a frontier-beating safety judge appeared out of a "plateaued" one. It also surfaced the
  real open problem: leak **recall** (v6 catches only ~60% of leaks at high precision).

---

## 5. Leak recall — the current frontier

### 5.1 Diagnosis: not a label problem
- **What/Why:** v6 misses ~40% of leaks, almost all `gives_away_key_step`, and 27/42 misses it calls
  `mismatched_calibration` — leaks *disguised as gentle corrections* (the pilot's original insight,
  §1.5). We checked whether the training labels carried the same confusion.
- **Result:** A cross-family jury on the `mismatched` training rows found only **~1% are actually
  leaks** — the labels are clean.
- **Learned:** The gap is a genuine **discrimination/coverage limit**, not mislabeled data — so
  relabeling (which would have corrupted correct labels) is the *wrong* lever. This check *prevented*
  a v7-style mistake.

### 5.2 Tier-1: self-consistency (a knob, not a free win)
- **What:** Sample k=5 and predict "leak" if ≥m of 5 say leak — sweeping m draws v6's precision/recall
  curve, no retraining.
- **Result:** OR-toward-leak lifts recall **59.6% → 76.0%**, but precision drops 84.9% → 60.8% (F1
  slips). A trade, not a free win — greedy is F1-optimal.
- **Learned:** Leak recall is *partly* a tunable **operating-point** choice (shippable now as a
  "high-recall safety mode") and *partly* systematic (the precision cost shows the boundary is fuzzy).
  Self-consistency slides along the current frontier; it doesn't move it.

### 5.3 The research fleet + Tier-2 (in progress)
- **What:** Six parallel research agents surveyed training methods (preference variants, distillation,
  recall-oriented training, small-model reasoning, data-centric augmentation, architecture/scale)
  against our state, grounded in current literature.
- **Learned / decided:** relabeling is dead (labels clean); reasoning is dead at 1.7B; the on-thesis
  lever is **minimal-pair contrastive augmentation** — teach the exact boundary v6 misses (corrective-
  framed leaks) with matched leaky/safe pairs. **Tier-2 (v9) is running now** to test whether that
  *moves the frontier* (higher recall at held precision), with a cross-family jury gate and a
  safe-corrective canary to avoid the v7 trap. *(Result pending.)*

---

## 6. Cross-cutting methodology lessons

1. **Relabeling > adding.** Fixing labels on a fixed-size set produced the biggest win (2%→35%);
   adding rows to a saturated model did nothing or hurt. Correctness/composition, not volume.
2. **Augment, don't replace.** New data added to the distribution helps; swapping it in regresses
   capabilities the model already had.
3. **A cross-family jury beats a single judge.** v7 failed because guided+verify were the same model;
   the reframe audit and the leak-recall check worked because Claude+GPT-4o had to *agree*.
   Same-model agreement ≠ correctness.
4. **Measure the right axis.** Separating objective safety from fuzzy quality turned a "plateaued"
   model into a frontier-beating one with no retraining. Know which of your metric's dimensions are
   learnable and which are irreducibly ambiguous.
5. **Small models don't reason their way to better judgments** (for self-verification tasks like this
   one). CoT is a large-model tool here.
6. **Negative results are results.** DPO, v7, v8, masking, the gap-loop — each "failure" bounded the
   design space and is individually defensible with an isolated, well-powered experiment.
7. **Isolate one variable.** v7's confound (prompt + labels at once) is exactly why v8 changed *only*
   thinking — and why its clean −11.4 is trustworthy.

---

## 7. Where the model stands

- **Ship model: v6** — a data-centric 1.7B judge that **beats GPT-4o and Claude on the safety axis
  (82%)**, with a tunable high-recall safety mode available for free.
- **Open problem:** leak recall (60% at high precision) — being attacked by Tier-2 minimal-pair
  augmentation (result pending); if that plateaus, the honest next levers are a discriminative
  classifier head or a scale step to Qwen3-4B/8B.
- **The real deliverable** is this understanding: a rigorously-mapped account of *what makes a small
  safety judge good* (clean, balanced, correctly-labeled data; honest metric design) and *what
  doesn't* (volume, preference optimization, reasoning, at this scale) — most of it learned from
  experiments whose eval numbers never moved.
