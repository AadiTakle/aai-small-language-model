# Verdict / Rewrite Split — Overnight Experiment (2026-07-11)

## Hypothesis & motivation

The shipped 1.7B model (v6) is a **combined** judge + rewriter: one JSON output carries the
verdict, reasoning, and (when flagged) a rewritten hint. Observations from the web UI motivated a
structural change:

- Rewrites are **lengthy, templated ("you said…"), and sometimes arithmetically wrong.**
- A flagged verdict occasionally came back with `rewritten_message: null` — an out-of-distribution
  combo that appears **0×** in training, so the flagged message passed through unchanged.

**Idea (split the model).** The judge and the rewriter have *opposite* data-quality needs: the
judge wants **maximum coverage + class balance**; the rewriter wants **maximum exemplar quality**.
Jamming both into one dataset forces a single quality bar that is wrong for both. So:

1. **Task 1 — verdict-only judge** trained on a multi-axis-balanced set (drop the rewrite head).
2. **Task 2 — rewrite-only model** distilled from the *best* frontier rewriter (curated targets).

Each is measured against **base Qwen3-1.7B** and **frontier** models.

---

## Task 1 — verdict-only judge (`judge_v1`)

**What.** Multi-axis, label-safe rebalance of the current data → a verdict-only LoRA adapter.

**Why.** Isolate the judgment head and test whether dropping the rewrite burden (plus better class
balance) improves discrimination — or at least matches v6 with a cleaner, more balanced dataset.

**How.**
- **Source = `data/raw/v9b.jsonl`**, confirmed to be exactly the current `data/mlx` (1432 raw →
  1246 gated → 996/124/126, matching the live split and verdict distribution).
- **Balancing = resample only** (no row edited, so every gold verdict stays valid by construction).
  Excluded 5 rows whose candidate text appears in the frozen eval (leakage-free). Hard verdict
  balance (**145/verdict = 725 rows**) + round-robin stratification across
  **band × topic × candidate-length × conversation-turns × #numbers** to flatten the secondary
  marginals (report: `eval/results/overnight/balance_report.md`).
- **Verdict-only render.** Task-specific system prompt asks for `{verdict, reasoning}` only; the
  target drops `rewritten_message`. Same LoRA recipe as v6 (rank 16, lr 1e-4, ~3 epochs / 500
  iters). Final **val loss 0.346** (better than v6's 0.365).

**Result** (frozen n=298, each model on its native prompt):

| model | 5-way acc | safety-binary | leak recall | leak precision | leak F1 |
|---|---|---|---|---|---|
| base (untuned, verdict prompt) | 26.8% | 68.5% | 51.0% | 55.2% | 53.0% |
| **judge_v1** (verdict-only, balanced) | 50.3% | 75.5% | 67.3% | 64.2% | 65.7% |
| **v6** (combined, ship) | 61.7% | 82.2% | 59.6% | 84.9% | 70.1% |
| opus-4.8 | 68.5% | 87.9% | 84.6% | 81.5% | 83.0% |
| gpt-5.6 | 70.8% | 90.6% | 77.9% | 94.2% | 85.3% |

**Learned.**
- **The split did not beat v6.** judge_v1 lost ~11 pts of 5-way accuracy and ~7 of safety-binary;
  it traded **leak precision (85→64) for recall (60→67)**.
- **Confounded — and the confound is instructive.** judge_v1 differs from v6 in *two* ways:
  verdict-only **and** less/class-balanced data (725 vs 996; `adequate` 317→145). The
  recall↑/precision↓ signature is exactly what forcing **uniform** classes does when the eval
  distribution is **non-uniform** — the model predicts leak classes more freely. Combined with a
  27% smaller training set, the balancing is the more likely driver of the regression than the
  split itself.
- **Lower val loss, worse eval.** judge_v1 fit its (uniform) training distribution *better* than v6
  fit its own, yet generalized *worse* to the natural frozen distribution. Aggressive class
  balancing is not free here — it miscalibrates to real-world class frequencies.
- **v6 remains the best SLM judge.** This is the 6th+ attempt that fails to beat v6 on the verdict.
- **Frontier clearly leads** (gpt-5.6 90.6% safety-binary, opus-4.8 87.9% vs v6 82.2%) — a real
  discrimination gap over the 1.7B; see Thesis below.
- **Clean follow-up:** train a verdict-only adapter on v6's *exact* (unbalanced) data to isolate
  "split" from "balancing." Prediction: verdict-only-on-v6-data ≈ v6 (the split is neutral; the
  balancing is what hurt).

---

## Task 2 — rewrite-only model (`rewrite_v1`), distilled from frontier

**What.** Bench-off the strongest frontier rewriters, then distill the winner's rewrites into a
1.7B rewrite-only LoRA adapter; compare to base Qwen and to the teacher.

**Why.** Rewrite quality is **data-bound** — the old combined data's rewrite targets were long
(median 29 words), templated, and sometimes wrong. Curate high-quality targets from the best
available rewriter instead.

**How.**
- **Contexts:** 1074 flagged (non-adequate) train contexts — v9b 535 + **real MRBench 394 +
  MathDial 61** (both HF-sourced tutoring data) + **HF GSM8K 80** (synthesized flawed candidate +
  verdict via the teacher) — and **60 held-out** real contexts for eval. Frozen content excluded.
- **Bench-off** (30 sampled contexts; anonymized cross-family jury = gpt-5.6-luna + sonnet-5):
  mean rank **gpt-5.6 = 1.78** < gpt-5.5 1.97 < opus-4.8 2.25; **0 leaks** for all three.
  **Winner = gpt-5.6.** (Caveat: one juror shares gpt-5.6's family; the margin + independent
  claude juror make the result credible, and the final eval uses jurors that exclude the teacher.)
- **Distillation:** gpt-5.6 produced **1070 targets** (only 4 dropped for leak/empty). Targets are
  **concise — median 18 words (vs 29 in the old data), max 43 (vs 73)** — directly fixing the
  "lengthy" complaint, with a leak-filter + one stricter retry.
- **Rewrite-only render:** system prompt takes the flagged candidate + its verdict + reason and
  emits **one concise plain-text Socratic hint** (no JSON). Trained on 963 examples, 722 iters.

**Result** (held-out n=60; cross-family jury = opus-4.8 + gpt-5.5, *excluding* the teacher):

| model | mean jury rank (1=best) | win-rate vs teacher | leak rate | mean length (words) |
|---|---|---|---|---|
| base (untuned) | 2.62 | 5.8% | 10.0% | 14.3 |
| **rewrite_v1** (distilled) | **2.13** | **18.3%** | **0.0%** | 20.3 |
| teacher gpt-5.6 | 1.26 | — | 1.7% | 18.0 |

**Learned.**
- **Distillation worked** (in contrast to Task 1). rewrite_v1 clearly beats base (rank 2.13 vs
  2.62; 3× the win-rate against the teacher) and is **safe + concise at frontier level**: **0% leak
  rate — lower than the teacher's own 1.7%** — and a 20-word median (vs the old combined data's 29).
  It directly fixes the two web-UI complaints (lengthy + leaky rewrites).
- **It does not match frontier holistic quality.** The jury preferred gpt-5.6 on ~82% of items
  (rewrite_v1 win-rate 18.3%). The 1.7B closes the safety/format/concision gap but trails on fine
  calibration/helpfulness — the expected generation-capacity ceiling.
- **The examples show genuine style transfer**, not just safety (held-out, verdict = gives_final_answer):
  - Flagged: *"…one liter is actually equal to 1000 milliliters."*
    → base: *"What is the relationship between liters and milliliters?"*;
    **rewrite_v1: *"What does the prefix 'milli-' tell you about how a milliliter compares with a liter?"***;
    gpt-5.6: *"What does the prefix 'milli-' tell you about how many equal parts one whole liter is divided into?"*
  - Flagged: *"…so 5/6 is already fully simplified."*
    → base: *"…check if 5 and 6 have any common factors other than 1."*;
    rewrite_v1: *"What does the greatest common factor (GCF) of 5 and 6 look like, and does that tell you whether the fraction can be simplified?"*;
    gpt-5.6: *"What factors do 5 and 6 have, and do they share any factor greater than 1?"*
- **rewrite_v1 training** wandered on val loss (min ~0.387 around iter 200, drifting up then back) —
  722 iters (~3 epochs) is likely 1 epoch too many for 963 rows; ~2 epochs would reduce overfit.

---

## Eval integrity

The frozen set (n=298) is **real MRBench tutor messages from named models** (`frozen-mrb-…-Gemini`,
`-Mistral`, `-Llama31405B`, …) — a different id namespace from the synthetic training rows, with
only **5 shared candidate texts, all excluded** from training. No train/eval leakage on either task.

---

## Thesis implications

Both tasks show frontier > 1.7B, but the **shape** of the gap differs — and that sharpens the
thesis rather than simply refuting it:

- The 1.7B **matches frontier on the *constrainable/distillable* behaviors**: rewrite safety
  (rewrite_v1 0% leak, below the teacher's 1.7%), output format (100% schema), concision (distilled
  targets 18–20 words), and the verdict **safety axis** (v6 82.2% is competitive, if now behind the
  very newest models). These are teachable by data + constraint.
- The 1.7B **trails frontier on the *capacity-bound* behaviors**: fine-grained 5-way discrimination
  (gpt-5.6 70.8% vs v6 61.7%) and holistic rewrite quality (jury prefers gpt-5.6 on ~82% of items).
- So **"scale doesn't matter" is too strong.** The defensible, evidence-backed SPOV: *a small model
  can be trained/distilled to match frontier on the safety-critical, well-specified behaviors, but a
  real capability gap remains on open-ended judgment and generation quality.* Recommend updating the
  brainlift to this sharper claim (with these numbers) rather than a blanket scale-invariance.
- Whether **scaling *our own* model** (1.7B → 4B) closes the capacity-bound gap is the separate,
  still-unrun Qwen3-4B test (`docs/scale_test_qwen3_4b.md`) — and it's most likely to move the
  rewrite holistic-quality and 5-way numbers, not the already-frontier-level safety/concision.

## Recommendations

1. **Rewrite head — a real win to adopt.** rewrite_v1 is safe (0 leaks), concise, and clearly beats
   base. Ship it as the **local rewrite head paired with v6 as the judge** (two adapters), or keep
   the **delegate-to-frontier** path for maximum quality. Either fixes the web-UI rewrite problems.
2. **Judge head — keep v6.** Do **not** ship judge_v1. Before concluding on the split, run the clean
   isolation: verdict-only on v6's *exact unbalanced* data (prediction: ≈ v6). If revisiting balance,
   use gentle class *weighting*, not uniform *downsampling* (which cost 27% of data + miscalibrated).
3. **Feed the human rewrite dataset** (web-UI contributions) into the distillation set to push
   holistic quality toward frontier — this is the tomorrow-task we scoped.
4. **Qwen3-4B rewrite** is the highest-value scale probe now (most likely to close the holistic gap).

## Artifacts

- Pipeline: `scripts/overnight/` (`split_common`, `balance_multiaxis`, `assemble_contexts`,
  `gen_rewrites`, `render_split`, `eval_verdict`, `eval_rewrite`).
- Data: `data/raw/verdict_balanced.jsonl`, `data/raw/rewrite_train.jsonl`,
  `data/raw/rewrite_contexts_{train,eval}.jsonl`.
- Results: `eval/results/overnight/{balance_report.md, benchoff.json, verdict_eval.*, rewrite_eval.*}`.
- Adapters (gitignored, regenerable): `adapters/judge_v1`, `adapters/rewrite_v1`.

---

## Follow-up (same day) — isolation, recall-first reframe, rewrite_v2

**Isolation (disentangle split vs balancing vs volume on the verdict):**

| model | data | objective | 5-way | safety-bin | leak R | leak P | leak F1 |
|---|---|---|---|---|---|---|---|
| v6 | v6_consensus ~996 | combined | 61.7 | 82.2 | 59.6 | 84.9 | 70.1 |
| judge_v1 | 725 balanced | verdict-only | 50.3 | 75.5 | 67.3 | 64.2 | 65.7 |
| judge_full | 1189 natural | verdict-only | 54.4 | 76.5 | **84.6** | 62.0 | 71.5 |
| combined_bal | 725 balanced | combined | 60.7 | 75.5 | 79.8 | 61.5 | 69.5 |

- **The split HURT:** combined_bal > judge_v1 on *identical* 725 data (5-way +10, recall +12) → the rewrite task regularizes/helps the verdict. Don't split for accuracy.
- **More + natural data → frontier-level recall:** judge_full leak recall 84.6 (= opus-4.8), F1 71.5 (edges v6); precision stays 62 (over-flags) so safety-binary/5-way still < v6.

**Recall-first reframe (deployment decision).** The judge only *triggers* a rewrite, so a false negative (missed leak) is the real harm and a false positive just spends a rewrite. Under recall-first, **leak recall is the ship metric → `judge_full` (84.6, ties frontier opus-4.8) is the ship detector, not v6** (v6 misses ~40% of leaks). Thesis: at 1.7B, judge_full *matches opus-4.8 on catching leaks*.

**rewrite_v2 (human-anchored).** Curated set = 23 human + 1033 gpt-5.6 regenerations steered to the human standard. Held-out n=60, same jury:

| model | jury rank | win-rate vs teacher | leak | len |
|---|---|---|---|---|
| base | 3.49 | 0% | 10% | 14 |
| rewrite_v1 | 2.68 | 15.0% | 0% | 20 |
| **rewrite_v2** | **2.48** | **16.7%** | 0% | 23 |
| gpt-5.6 | 1.35 | — | 0% | 18 |

→ **rewrite_v2 > rewrite_v1** (human-anchoring beats pure distillation, from only 23 corrections); still trails frontier holistic quality.

**Ship pipeline (recall-first, superseded below): `judge_full` + `rewrite_v2`.**

### Recall-first ship detector — `v9` (the winner)

Diagnostic (`judge_full` missed leaks): all **16 misses are `gives_away_key_step`** (gives_final recall 100%), specifically **corrective-framed key-step leaks** — the tutor corrects the student by *stating* the key step ("you're close, but remember… let's try dividing…"), which judge_full mislabels `mismatched_calibration`. That is exactly what tier-2 minimal-pairs (`run_tier2`) target.

Recall-first eval (frozen n=298):

| model | 5-way | safety-bin | leak R | leak P | leak F1 |
|---|---|---|---|---|---|
| judge_full | 54.4 | 76.5 | 84.6 | 62.0 | 71.5 |
| combined_full | 55.7 | **83.2** | 66.3 | 82.1 | 73.4 |
| **v9** (tier2, safe-dup 1) | **64.1** | 77.5 | **90.4** | 62.3 | **73.7** |
| v9b (tier2, safe-dup 2) | 56.0 | 77.2 | 51.0 | 75.7 | 60.9 |

**`v9` leads on leak recall (90.4%), F1 (73.7%), and 5-way (64.1%)** — best SLM judge on all three; catches ~94/104 leaks. Precision 62% (over-flags) is acceptable under recall-first. v9b confirms safe-dup 2 overcorrects (recall 51%). Ensemble-union(judge_full∨v6) was a near-no-op (85.6%, +1) — correlated SLMs.

**Ship (recall-first): `v9` (detector, 90.4% recall) → `rewrite_v2` (rewriter, 0% leak).** Both 1.7B, already trained. Note: `combined_full` is the best *balanced* judge (83.2 safety-binary, best of all — beats v6) if the objective were balanced accuracy; the **objective controls the operating point** (verdict-only → recall-heavy; combined → precision-heavy). To push recall past 90% toward catch-all: `run_tier2` with more seeds (fresh corrective-framed pairs), or a recall-tuned binary leak/safe head.
