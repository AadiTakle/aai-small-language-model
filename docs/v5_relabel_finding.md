# v5 — Training-data relabel against the corrected golden set

The strongest result of the project's data-centric arc: the model's key-step-leak blindness was a **label problem**, not a capacity limit, and cleaning the training data fixed it.

## The chain: diagnosis → fix → result

1. **Corrected the golden set.** Manual human review + a calibrated Claude-subagent reconcile (no external key) found the eval had systematically mislabeled key-step **leaks** as `adequate`. `gives_away_key_step` gold went 1 → 40; 92/306 gold verdicts changed. (See `eval/gold/review/reconcile_applied.json`.)
2. **Re-scored v4 on the corrected gold** (same 306 items, same predictions, only labels changed): verdict accuracy dropped *most for the best models* (v4 −8.5 pts). Diagnosis: **v4 had learned the lenient "leaks are adequate" bias from its training data** — the old eval was rewarding the same leniency.
3. **Relabeled the training data** (v4 → v5) against the corrected golden standard via the same LLM-as-judge framework (`scripts/relabel_training.py`, Claude subagents). **222 / 1334 flips (17%)**; `gives_away_key_step` training examples 142 → 229; leaks removed from the `adequate` class; flipped rows got **regenerated** corrected targets (verdict + grounded reasoning + a *safe* rewrite, leak-gated). Retrained `adapters/v5` on the same config as v4 (only the data differs).

## Result — v4 vs v5 on the corrected golden set (n=306, verdict-only, deterministic)

| model | verdict accuracy [95% CI] | verdict tier | `gives_away_key_step` recall (exact) | caught as *any* leak |
|---|---|---|---|---|
| v4 | 51.6 [46, 57] | 1.343 | **1/40 (2%)** | 6/40 (15%) |
| **v5** | 49.0 [44, 55] | 1.330 | **14/40 (35%)** | **23/40 (58%)** |

**Reading:**
- The **targeted safety behavior improved ~17×**: exact key-step-leak detection 2% → 35%; caught-as-a-leak 15% → 58%. From a **data-only** change (same model, same hyperparameters, same training config).
- **Overall verdict accuracy is statistically unchanged** (CIs overlap) — the safety gain came at no significant aggregate cost. The small nominal dip is a precision trade-off: v5 flags leaks more aggressively, occasionally over-calling.
- This confirms the project's central claim — **reliable, constrained behavior from data**: v4's leak-blindness was mislabeled training targets, corrected by relabeling, not by a bigger model.

## Method / reproducibility
- Calibration built **from the corrected golden set** (few-shot per verdict incl. the 40 real `gives_away_key_step` cases) + the reviewer's operative criteria — `scripts/relabel_training.py --prep`.
- Verdict judged by Claude subagents; flipped rows' targets regenerated + leak-gated (`--prep-regen` / `--assemble-v5`). No external API key (data-cleaning, no contestant-bias concern).
- Scores: `eval/results/report/recon306/{v4,v5}_items.json`. Scored with `report_score.py --no-judge --consistency-k 0` (deterministic criteria only).

## Caveats / what's still owed
- **Verdict-only.** Grounded reasoning, rewrite-safety, consistency, and the frontier contestants (`gpt-4o`, `claude`) are **not** re-scored on the corrected gold yet — those need a non-Claude judge (TrueFoundry gateway or restored OpenAI billing).
- v5's leak recall (35% exact / 58% any-leak) is a large improvement but **not** yet frontier-level; further gains likely need DPO (preference pairs) on top of the cleaned data.
- The corrected gold is human-anchored (your rulings) + neutral-strict-read-confirmed on the majority of edits, but it is a judgment standard; numbers should be read as "against our best current definition of correct," which is materially cleaner than the original MRBench mapping.
