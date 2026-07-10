# v8 thinking — finding (clear negative: thinking HURTS a 1.7B here)

## What v8 is
The cleanest experiment of the four: **thinking is the ONLY variable vs v6.** Same v6 labels,
same v6 prompt (the v7 decision tree reverted), same training config + 687 iters. The only change:
each SFT target carries a `<think>` reasoning trace (1,144 concise traces distilled from gpt-5.5,
rationalized to the v6 verdict), and inference runs `enable_thinking=True` (max_tokens 1024 for
think + JSON). Both cheap probes (base, v6) were confirmed uninformative — only a *trained*
thinking model could answer whether reasoning helps.

## Result — frozen set (n=298), same scorer
| Metric | sft_v6 | v7 | v8 (thinking) |
|---|---|---|---|
| **Verdict accuracy** | **61.7%** | 56.4% | **50.3%** |
| Grounded (heuristic) | 99.0% | 97.3% | 99.3% |
| Rewrite safety (heuristic) | 89.6% | 90.5% | **85.7%** |
| Schema compliance | 99.7% | 97.3% | 99.3% |
| Calibration robustness | 100% | 100% | 0% (0/2) |

**Thinking made it worse: verdict −11.4, rewrite-safety −3.9 vs v6.** Schema/grounded are fine
(99.3%) — v8 emits valid JSON, it's just *confidently wrong more often*. (Calibration "0%" is only
2 adversarial probes, both flipped — directionally consistent but n=2, not the headline.)

## Why — the classic small-model chain-of-thought failure
A 1.7B model made to generate a reasoning trace before answering **reasons unreliably and talks
itself out of the correct verdict.** CoT helps large models but frequently *hurts* small ones:
their intermediate reasoning is low-quality, and conditioning the verdict on that shaky trace
compounds errors instead of correcting them. v6 maps input→verdict directly; v8 inserts a fallible
reasoning step in between. This matches the base probe (base was ~chance — it couldn't reason
usefully) and the fact that the failures cluster on the trickiest (adversarial) items.

## Conclusion
- **`sft_v6` stays the ship model** — now the **4th** lever that fails to beat it (DPO v1,
  v7-relabel, v7-audit confirmation, v8-thinking). v6 (data-centric SFT on 1.7B, 61.7% verdict,
  beating GPT-4o and Claude) is a genuinely strong, hard-to-beat baseline.
- **Thinking is not dead — but it needs scale.** The evidence now points one way: a 1.7B can't turn
  reasoning into better verdicts. The thinking lever, if pursued, requires a bigger model (Qwen3
  **4B / 8B**), where the reasoning trace is actually reliable. That is the well-justified next bet
  (and the two-stage judge→rewrite split still applies there).
- **Or reframe what we measure.** Four negatives at 1.7B strongly suggest we're at the model's
  ceiling for exact-match on a 5-way, partly-fuzzy axis. The structural move from
  `rubric_evaluation.md` (headline the objective **binary safety** score; collapse / stop chasing
  the mismatched↔vague distinction) remains the cheaper alternative.

Artifacts: `data/raw/v8_traces.jsonl`, `eval/results/v8_frozen.md`, `adapters/v8` (gitignored),
`scripts/gen_think_traces.py`, `scripts/eval_v8_frozen.py`. Branch `feat/v8-thinking`.
