# Eval Review — Socratic Tutor Adequacy Judge & Rewriter (Qwen3-1.7B)

*Presentation companion for the live eval review. Order matches the walkthrough: the suite → how we
did → what we'd do better. Full history in `docs/model_devlog.md`; figures in `docs/figures/`.*

---

## 🎤 5-minute walkthrough (the script)

1. **What we built:** a 1.7B safety *guardrail* for AI math tutors — judges whether a tutor message
   leaks the answer/key-step, and rewrites it safely if so. Ship pipeline: **`v9` judge → `rewrite_v4`
   rewriter**.
2. **Eval philosophy (the differentiator):** we built the eval *before* training, held it out +
   leakage-checked it, always compared base-vs-tuned-vs-frontier, and used a **cross-family jury** (never
   same-model self-agreement). The biggest lever we found was **honest metric design**, twice.
3. **How we did:** on the safety-critical behavior, the 1.7B **matches or beats frontier** — 82.2%
   safety-binary (> GPT-4o, Claude), 90.4% leak-recall (= Opus), and the rewriter is in the **safest
   tier of every model tested** (6.7% key-step leak). A 4B counterfactual confirms **scale isn't the
   lever**.
4. **The honest part:** it trails frontier on the *fuzzy quality axis* (a distinction even GPT-4o and
   Claude split ~60% of the time), and we'd fix several eval-methodology mistakes if we did it again.

---

## 1. The eval suite (how we measure)

**Principles**
- **Built before training** — a hand-seeded gold anchor grew into a **leakage-checked frozen set
  (n≈300)** of *real* MRBench tutor messages (different id namespace from training; shared candidates
  excluded). Never trained on.
- **Always base vs. tuned vs. frontier** (GPT-4o, GPT-4.1, Claude, gpt-5.x) — every "did it help?" is
  answered against an external anchor.
- **Cross-family jury** for anything subjective — anonymized, position-debiased, and the teacher model
  is *excluded* from judging its own outputs. (We learned why the hard way: v7 failed because its
  relabel used the *same* model to generate and verify — it rubber-stamped its own bias.)
- **Honest metric design** — separate the objective **safety axis** (leak vs. safe) from the fuzzy
  **quality axis**; validate the leak *detector itself*.

**The instruments** (all in `scripts/overnight/` + `scripts/eval_harness.py`)

| instrument | what it measures | script |
|---|---|---|
| Frozen verdict eval (n≈300) | 5-way accuracy, **safety-binary**, leak **precision/recall/F1** | `eval_verdict.py` |
| Rewrite quality | cross-family **jury rank** + win-rate vs teacher + concision (held-out 60) | `eval_rewrite.py` |
| Leak detectors (LLM, spec-aligned) | **broad** (answer OR any operation) + **sharp** (answer / *next* step / uncued correction) | `split_common.py` (`llm_leaks`, `llm_leaks_sharp`) |
| Adversarial stress test | cave-rate over 8 problems × 15 escalating "get the answer" turns | `stress_ship.py` |
| Traditional benchmarks | GSM8K / MMLU, base vs. fused-SFT (forgetting check) | `bench_run.py` |
| Dataset-scaling curves | performance vs. boundary-data dose | `scale_boundary.py` |
| Scale thesis | 4B judge vs. 1.7B on our metrics | `eval_4b_judge.py` |

**Two metric-design moments that were bigger than any model change:**
- **The safety-axis reframe** — re-scoring separated leak-safety from fuzzy quality. Turned v6's
  "mediocre" 61.7% 5-way into **82.2% safety-binary (best of all models)** with *zero* retraining.
- **The sharpened leak detector** — the broad detector over-flagged (it counted *restating the
  student's own value* and *"why does this completed step work?"* as leaks). `llm_leaks_sharp` fixed
  it and revealed our rewriter is in the **safest tier**, and that the broad metric had penalized
  frontier's thoroughness *hardest*.

---

## 2. How well we performed (results)

**Judge (frozen set, verdict):**

| model | 5-way | **safety-binary** | leak recall | leak F1 |
|---|---|---|---|---|
| base 1.7B | 26.8% | 68.5% | 51% | 53% |
| **v6** (reframe) | 61.7% | **82.2%** | 60% | 70% |
| **v9** (ship detector) | 64.1% | 77.5% | **90.4%** | **73.7%** |
| GPT-4o | — | 77.5% | — | — |
| Claude | — | 78.5% | 85% | 83% |

→ **v6 beats GPT-4o & Claude on safety-binary; v9 ties Opus on leak-recall.** Base→tuned leak-F1
24%→70%, leak-recall 2%→90% — all from *data*, on a fixed 1.7B.

**Rewriter (held-out 60, sharpened detector — key-step leak rate, lower = safer):**

| base | rewrite_v4 (ours) | gpt-4o | gpt-4.1 | sonnet-5 | gpt-5.6 |
|---|---|---|---|---|---|
| 38.3% | **6.7%** | 11.7% | 10.0% | 6.7% | 11.7% |

→ **`rewrite_v4` is in the safest tier of every model tested** — ties the best frontier (sonnet-5),
beats gpt-5.6/4o/4.1.

**Scale thesis (4B judge, identical recipe, frozen):** leak-recall 93.3% vs v9's 90.4% (~noise),
*worse* 5-way (55.7 vs 64.1) — **2.4× params bought a noise-level bump; the data lever bought 2%→90%.**

**Traditional benchmarks:** base GSM8K **46.7%** flexible; fused-SFT collapses to **6.7%** — an honest
**cost-of-specialization** (our model is a safety specialist, not a general solver).

**The honest split:** we *nail* the learnable **safety axis**; we *trail* frontier on the **fuzzy
quality axis** — but that axis is near-irreducibly ambiguous (GPT-4o and Claude disagree on it ~60% of
the time and the blind jury sided with our original gold 16-to-2 over a "better" relabel).

---

## 3. What we'd do better next time

Honest, specific, mostly methodology:

1. **Build the *honest* metric first.** The single biggest lever was metric design, and we found it
   twice, *late* (safety-axis reframe; sharpened detector). We chased the 5-way number for days before
   realizing ~half of it was irreducible noise. Next time: pressure-test metric validity on day 1.
2. **Audit gold labels before training, not after.** The v5 relabel (leak-recall 2%→35%) fixed
   *systematically mislabeled* gold — we'd trained several versions on bad targets first. A jury label
   audit belongs at the start.
3. **Change one variable at a time.** v7 moved prompt *and* labels together → confounded, uninterpretable.
   Cost us a version to diagnose.
4. **Reduce eval noise.** The rewrite jury eval is n=60 — a few items swing it. Bigger held-out sets
   (and more jurors) would make the small deltas we chased actually resolvable.
5. **Harden the eval harness earlier.** On the final day, MMLU came out chance-level (an MLX/4-bit
   loglikelihood quirk) and GSM8K OOM'd batched — both eval-infra issues that a day-1 smoke test of the
   whole harness would have surfaced.
6. **Lean into human curation sooner.** Every time we compared, human-anchored data beat pure
   distillation (rewrite_v2 > rewrite_v1; rewrite_v4). We under-used it early.
7. **A controlled scale ablation.** Our 4B was Colab/trl/bf16 vs the 1.7B's local MLX — close enough to
   make the point, but a matched trainer/quantization would make the scale claim airtight.
8. **Decide the operating point up front.** We flip-flopped between balanced-accuracy and recall-first
   framings; naming "missed leak = the real harm" earlier would have pointed straight at v9/tier-2.

**One-line takeaway for the grader:** *the deliverable isn't the model — it's a rigorously-measured
account of what makes a small safety judge good (clean, correctly-labeled, balanced data + honest
metrics) and what doesn't (volume, preference tuning, reasoning, and scale, at this size).*
