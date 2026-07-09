# Ablation — prompt-masked vs unmasked (text-format) training

**Result: a negative for masking on the measurable axis.** At matched config, masking the prompt did not improve the constrained behavior and slightly *regressed* key-step-leak recall. Keep the unmasked (text-format) recipe as the ship candidate.

## Hypothesis
Our training uses **text-format** JSONL (`{"text": full system+user+assistant}`), which `mlx_lm` trains with **no prompt masking** → loss over the whole sequence. Empirically ~90% of the loss (576 / 640 tokens) lands on the prompt (system + problem + conversation), only ~10% (~64 tokens) on the JSON target. Hypothesis: **masking the prompt** (loss on the assistant JSON only) focuses the signal and should improve the judge behavior — and, more importantly, stop the model from imitating clunky MRBench tutor turns, helping **rewrite safety**.

## Method (isolates one variable)
- **v5-masked**: `build_dataset.py --format chat` → `{"messages":[system,user,assistant]}`, trained with `configs/lora_v1_masked.yaml` (`mask_prompt: true`, everything else identical to `lora_v1.yaml`). Verified the chat render is **token-identical** to the text render (Qwen3 emits an empty `<think></think>` either way), so the ONLY difference is the loss mask.
- **v5-text**: `adapters/v5` (the shipped v5 relabel run).
- Same v5 data, same seed-0 split, same 500 iters. Scored on the corrected golden set, deterministic criteria only (`report_score.py --no-judge --consistency-k 0`).

## Result — corrected gold, n=306

| model | verdict accuracy [95% CI] | verdict tier | schema | `gives_away_key_step` recall (exact) | caught as any leak |
|---|---|---|---|---|---|
| **v5 (text / no-mask)** | 49.0 [44, 55] | **1.330** | 1.980 | **14/40 (35%)** | **23/40 (58%)** |
| v5-masked | 47.7 [42, 53] | 1.304 | 1.967 | 9/40 (22%) | 14/40 (35%) |

- Verdict accuracy and schema are within noise (CIs overlap).
- **Leak recall regressed** under masking: any-leak 58% → 35%, exact 35% → 22% — worse on the safety-critical metric.

## Interpretation
Two compounding reasons the "wasted signal" intuition didn't pan out:
1. **Full-sequence training is a mini in-domain LM objective.** Predicting the problem/conversation tokens teaches the small (1.7B) model to *represent* tutoring dialogue; that representation aids the downstream classification. Masking discards it.
2. **Undertraining at matched iters.** With `mask_prompt`, each example contributes loss on only ~64 target tokens (vs ~640), so at the same 500 iters the masked model is far less converged (masked val loss plateaued ~1.0 vs text ~0.26). A fair-er comparison would give masked more iters — but that's a hyperparameter change, outside the "iterate on data, not hyperparameters" rule, so the matched-config result stands.

## Caveat & decision
- The **primary** hypothesis — masking improves **rewrite safety** — is **LLM-judged and untested** here (blocked on a non-Claude grader; TrueFoundry gateway or OpenAI billing). This ablation only settles the deterministic axis.
- On that axis masking is a slight negative and worse on leak recall, so **do not adopt masking** for the classification behavior. Re-evaluate only if/when the judged rewrite-safety comparison shows a large masking win that outweighs the leak-recall regression.
- **Ship candidate stays v5-text (`adapters/v5`).**
