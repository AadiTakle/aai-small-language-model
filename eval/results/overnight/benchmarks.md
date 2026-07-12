# Traditional LLM benchmarks (MLX, non-thinking, chat-template applied)
_GSM8K: 5-shot, n=30 (Metal-OOM cap on mlx_lm.evaluate's all-at-once generative batching), exact-match._
_Qwen3-1.7B published refs (approx, non-thinking): GSM8K ~75%, MMLU ~62%_

| model | GSM8K (strict) | GSM8K (flexible) | MMLU (mean acc) |
|---|---|---|---|
| base (Qwen3-1.7B-4bit) | 10.0% | 46.7% | ~24% (harness artifact) |
| fused-v6 (SFT, forgetting check) | 0.0% | 6.7% | ~24% (harness artifact) |

_GSM8K flexible-extract is the meaningful metric (strict penalizes the non-`#### N` format). fused-v6's
drop (46.7% → 6.7% flexible) is the catastrophic-forgetting / cost-of-specialization signal: the SFT
model, prompted neutrally, no longer behaves like a general solver. MMLU is chance-level via this MLX
loglikelihood harness across all configs tried (chat-template on/off, fewshot-as-multiturn) — a
harness / 4-bit-quantization interaction, NOT the true MMLU (~62% published)._
