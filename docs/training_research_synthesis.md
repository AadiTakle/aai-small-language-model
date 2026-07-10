# Training-methods research — 6-agent fleet synthesis (2026-07-10)

Six parallel research agents, each on one training-method family, grounded in our state (Qwen3-1.7B
judge/rewriter; v6 the ship model at the 1.7B ceiling; **leak recall ~60% the open problem**; four
prior negatives: DPO, v7-relabel, v8-thinking, v7-audit). Full reports in the session transcript.

## Verdict by angle
1. **Preference optimization (KTO / ORPO / SimPO; RLAIF/GRPO).** Diagnosed *why* our DPO failed: the
   pairs varied only the **rewrite**, never the verdict/leak-flag — so it trained the wrong thing and
   let the verdict drift. Fix = attach the preference to the **verdict** (KTO on `{prompt, verdict-
   completion, desirable/undesirable}`, undesirable = v6's own missed leaks). Now **MLX-native**
   (`mlx-tune`: KTO/ORPO/GRPO) — no Colab. Risk: reusing the rewrite pairs repeats the mistake; SLM-
   capacity caution (EASE). A preference method can't manufacture discrimination the model lacks.
2. **Distillation from frontier judges (black-box).** v6 is already SFT-on-teacher-labels, so more of
   the same plateaus. Best = **DART (distill→audit→repair)**: audit v6's outputs with a **2-of-3
   teacher jury** (never a single teacher — the v7 over-flip trap), find corrective-framed misses,
   severity-weighted SFT on them. Plain SFT, local, reuses `gap_loop.py`. DSS shows rationale can be a
   *train-time* signal without an inference trace (unlike v8). Modest expected gain.
3. **Recall-oriented / cost-sensitive.** Class counts aren't very skewed → discrimination, not raw
   imbalance. **Cheapest + genuinely untried: self-consistency OR-toward-leak** (sample k=5; if ANY
   says leak → leak; recall ≥ single-sample by construction), pure eval-side, no retraining. Plus a
   **logprob-threshold** readout (P(first verdict token); the two leak labels share token-id 70,
   distinct from non-leak) → a tunable operating point with NO new head. `mlx_lm.tuner.train()` exposes
   a custom-loss hook if true weighting is wanted. Risk: OR won't help if misses are *systematic* (not
   sampling noise) — which is itself the diagnostic.
4. **Small-model reasoning alternatives.** **DEAD END, decisively.** Four independent negatives (our
   v8 + MACA + failed CODI reproductions + 2025-26 "thinking backfires" / weak-judge-sway papers naming
   our exact mechanism at *bigger* scale). Only cheap close-out: the same self-consistency N=5 (= #3).
   Do NOT spend the week on latent-CoT / PRM.
5. **Advanced data-centric (augmentation).** Measured the gap: training has **no matched minimal-pair**
   (same wrong-answer setup with one leaky-corrective AND one safe-corrective response) — that
   contrastive pair doesn't exist in the data. Fix = **minimal-pair contrastive synthesis** (generate
   both sides; jury + round-trip validated) — the *one un-falsified data hypothesis*. On-thesis,
   reuses `gap_loop.py`/`gen_lib.py`. Grow the eval slice first (only ~13 corrective leaks in frozen; 0
   in the probe) or the effect isn't measurable. Risk: surface-phrasing overfit → 1:1 safe counterparts
   + a safe-corrective canary.
6. **Architecture / scale.** Strongest structural evidence: a **discriminative encoder classifier**
   (DeBERTa-v3 / ModernBERT) exposes real logits → a **free tunable precision/recall threshold** (what
   v7 hacked via prompt). Ettin: 400M encoder > 1B decoder on classification; AEGIS: 67M classifier ≥
   7B generative guard. BUT `mlx-embeddings` is inference-only → needs PyTorch+MPS+`transformers.Trainer`
   (2nd stack, but ~1 afternoon; `transformers` already installed). **Scale to 4B/8B** is MLX-native +
   cheap but off-thesis and attacks the fuzzy quality-axis more than leak recall. Uni-SafeBench:
   unifying gen+classification hurts safety → favors a split. A bare classifier loses the grounded
   `reasoning` citation → it's a component *alongside*, not instead of, the generator.

## Convergent themes
- **Leak recall is likely a THRESHOLD / decision-boundary problem as much as a capacity one.** v6 has
  high leak *precision* (85%) and sits at one point on the PR curve; v7 already reached 72% recall. A
  classifier, or a logprob / self-consistency threshold, turns "one point" into "a curve you choose."
- **The cheapest first move — self-consistency OR-toward-leak — was independently the #1 pick of TWO
  agents (3, 4).** It's a free lottery ticket AND the diagnostic for threshold-vs-systematic.
- **"Train on the errors, with a JURY."** KTO-on-verdict (1), DART audit-repair (2), and minimal-pair
  synthesis (5) all converge on targeting v6's specific missed-leak pattern — and all warn: cross-
  family jury, never a single teacher (the v7 trap).
- **Reasoning is dead at 1.7B** (4, cross-confirmed by 1).

## Recommended sequence
- **Tier 1 — this week, hours, zero retraining, also a DIAGNOSTIC:** self-consistency OR-toward-leak
  (k=5) + logprob-threshold sweep on v6 → draw v6's real precision/recall curve. Recall ~70% at OK
  precision → free shippable win + leak-recall is a threshold problem (done). If not → the miss is
  systematic → Tier 2.
- **Tier 2 — on-thesis training fix, 2-3 days:** minimal-pair contrastive augmentation → v9 (grow the
  eval slice first; jury + round-trip validate; gap-loop accept/revert with a safe-corrective canary).
- **Tier 3 — structural spike, ~1 afternoon:** DeBERTa-v3 binary leak/safe classifier via
  `transformers.Trainer`/MPS, scored with `rescore_safety.py` vs v6's 60% recall. Wins → classifier-
  judge is the structural answer; loses → not architecture, scale is the lever.
- **Reserve (only if 1-3 plateau):** KTO-on-verdict (MLX-native `mlx-tune`) or scale to Qwen3-4B.

## Don'ts
Reasoning/CoT (dead); blind relabel of clean data (v7 trap); DPO on the rewrite-only pairs (the
diagnosed failure).

## Housekeeping
**Bug (caught by the architecture agent):** `socratic_tutor/config.py` still has `ENABLE_THINKING=True`
(set for v8). v6 ships thinking-**off** — revert to `False` before any v6-based experiment (Tier 1/2)
or v6 runs in thinking mode.
