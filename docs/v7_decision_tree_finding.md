# v7 decision-tree relabel — finding (negative, with a real confound)

## What v7 is
An attempt to lift verdict accuracy by attacking the quality axis (adequate /
mismatched_calibration / vague_unhelpful), where `docs/rubric_evaluation.md` located nearly
all remaining error (mismatched recall ~14%). Two changes vs v6:
1. **Prompt**: an explicit ordered decision procedure + confirmation rule added to `SYSTEM_PROMPT`.
2. **Labels**: a conservative gpt-5.5 relabel of the 814 quality-axis rows of `v6_consensus`
   (`scripts/relabel_v7.py`) — flip a verdict only when a guided pass AND an independent verify
   pass agree (CONFIRMED). **91 flips** applied (14 →adequate, 77 →non-adequate regenerated +
   leak-gated; 8 dropped). Notably 15 `adequate → gives_away_key_step` (leaks that were mislabeled
   adequate). Safety-axis verdicts left untouched. Training config identical to v6 (687 iters).

Training: val loss **0.287** (v6: 0.365), train loss 0.078 — fits/generalizes better on its own
(relabeled) valid split.

## Result — frozen set (n=298), deterministic verdict + heuristic rewrite-safety
| Metric | sft_v6 | dpo_v1 | v7 |
|---|---|---|---|
| Verdict accuracy | 61.7% | 54.4% | **56.4%** |
| Rewrite safety (heuristic) | 89.6% | 86.1% | **90.5%** |
| Grounded (heuristic) | 99.0% | 99.3% | 97.3% |
| Schema compliance | 99.7% | 99.3% | 97.3% |
| Calibration | 100% | 100% | 100% |

**v7 does not beat v6**: verdict accuracy −5.3, rewrite-safety +0.9 (~2 items, noise-level),
schema −2.4, grounded −1.7. `sft_v6` remains the ship model. (v7 still beats v4/v5/GPT-4o/Claude
on verdict accuracy — it's the 2nd-best model — but the goal was to beat v6, and it didn't.)

## Why it likely regressed
1. **Gold was NOT relabeled to the decision tree — a real confound.** The frozen gold's labels
   predate the explicit tree. A v7 trained to the sharper rule will *principledly disagree* with the
   old gold on genuinely-ambiguous quality-axis items and get scored wrong for it. So −5.3 partly
   measures divergence-from-un-updated-gold, not necessarily worse pedagogy. This is a limitation of
   tonight's test, not proof the tree is bad.
2. **Schema −2.4 is real degradation.** The tree prompt is ~150 tokens longer, pushing a handful of
   training sequences over `max_seq_length=2048`; those got truncated (target JSON cut), plausibly
   teaching occasional malformed output. ~2.4 of the 5.3 verdict drop is just unparseable outputs.
3. Prompt differs across columns (v7 new prompt vs v6 old prompt — each scored with its own training
   prompt, fair per-model, but not isolated).

## Recommendation
- **`sft_v6` stays the ship model.** v7 is not an improvement by the fixed yardstick.
- This is NOT a clean rejection of the decision tree — it's inconclusive because the gold wasn't
  updated and a few v7 rows were truncated. To settle it:
  1. Relabel the **frozen gold** to the same decision tree (consensus), then re-eval all models on
     the updated gold — the only fair test of a criteria change.
  2. Fix the truncation: bump `max_seq_length` to ~2304 for the tree prompt (or trim the prompt), so
     no target JSON is cut.
  3. Isolate prompt-vs-relabel: train a v7b with the new labels but the OLD prompt.
- The **relabel data itself is sound and reusable** (91 conservative CONFIRMED flips, 15 real leaks
  caught) — `data/raw/v7.jsonl` is a cleaner pool even though v7-as-trained didn't win.

Artifacts: `data/raw/v7.jsonl`, `eval/results/v7_relabel_report.md`, `eval/results/v7_frozen.md`,
`adapters/v7` (gitignored). Branch `feat/v7-decision-tree`.
