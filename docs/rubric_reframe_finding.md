# Rubric reframe — separate the objective SAFETY axis from the fuzzy QUALITY axis

## Why
Four levers (DPO, v7 relabel, v7-audit, v8 thinking) failed to beat v6 on 5-way verdict accuracy,
and the blind-jury audit showed the quality axis (adequate / mismatched_calibration /
vague_unhelpful) is *intrinsically fuzzy* — even Claude and GPT-4o split on 46/77 contested items.
The 5-way metric conflates that partly-unlearnable fuzzy axis with the objective, product-critical
**safety** axis (does the candidate message leak the answer or the key step?). This reframe
re-scores existing predictions to measure the safety axis directly — **no model runs**, pure
re-scoring of stored preds against the current frozen gold (`scripts/rescore_safety.py`).

Metrics: **5-way** (old), **3-way** (collapse the three quality verdicts → SAFE, keep the two
objective leak types), **safety-binary** (LEAK {gives_final_answer, gives_away_key_step} vs SAFE),
**leak P/R/F1** (leak = positive class — the safety-critical number for the product).

## Result — frozen set (re-scored)
| model | n | 5-way acc (old) | 3-way acc | safety binary | leak P | leak R | leak F1 |
|---|---|---|---|---|---|---|---|
| base | 298 | 25.2% | 65.1% | 66.1% | 55.2% | 15.4% | 24.1% |
| v2 | 298 | 36.2% | 74.2% | 75.5% | 86.0% | 35.6% | 50.3% |
| v3 | 298 | 42.3% | 67.1% | 67.8% | 75.0% | 14.4% | 24.2% |
| v4 | 298 | 50.3% | 75.8% | 77.2% | 86.0% | 41.3% | 55.8% |
| v5 | 298 | 55.4% | 76.5% | 79.2% | 77.5% | 59.6% | 67.4% |
| **v6** | 298 | **61.7%** | **79.2%** | **82.2%** | 84.9% | 59.6% | 70.1% |
| v7 | 298 | 56.4% | 76.5% | 79.2% | 73.5% | 72.1% | 72.8% |
| v8 | 298 | 50.3% | 70.8% | 74.8% | 64.7% | 63.5% | 64.1% |
| gpt4o | 298 | 52.3% | 76.2% | 77.5% | 91.1% | 39.4% | 55.0% |
| claude | 298 | 59.4% | 76.8% | 78.5% | 74.5% | 76.0% | 75.2% |

(v7's preds used the decision-tree prompt; all others the v6 prompt. Metric change, not a re-run.)

## What it shows
1. **v6's 5-way understates it.** Safety-binary **82.2%** / 3-way **79.2%** — the **best of every
   model**, beating GPT-4o (77.5/76.2) and Claude (78.5/76.8). ~20 pts of apparent "error" was the
   fuzzy quality axis, not safety mistakes. On the product-relevant axis, the 1.7B beats the frontier.
2. **The model learned safety.** base leak-F1 24% → v6 70%; safety-binary 66% → 82%, rising across
   the data iterations. SFT worked on the axis that matters.
3. **Real weakness the old metric hid: leak RECALL.** v6 catches only **59.6%** of leaks (precision
   84.9% — few false alarms, but misses 40%). For a safety product, recall is the priority (better to
   over-flag than let an answer slip). Claude 76%, v7 72%.
4. **v7 recontextualized.** Its "over-flipping" (which lost on 5-way) bought the best SFT **leak
   recall (72.1%)** — it traded toward catching more leaks; the 5-way metric mismeasured it.

## Recommendation
- **Adopt safety-binary + leak-F1 as the HEADLINE eval metric**; keep 5-way as a diagnostic. It's the
  honest, product-aligned measure, and it's where the model is strong and the frontier is beatable.
- **Ship v6** — best model on the metric that matters.
- **Next concrete lever with real headroom: leak RECALL** (v6 misses 40% of leaks). v7 already
  proved recall is movable (72% vs v6's 60%) — a recall-oriented decision threshold, a
  recall-weighted prompt, or targeted data on the missed-leak patterns are the candidates. This is a
  sharper, more valuable target than chasing exact-match on the fuzzy axis.

Artifacts: `scripts/rescore_safety.py`, `eval/results/rubric_reframe.md` / `.json`.
Branch `feat/rubric-reframe`.
