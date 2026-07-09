# Dataset balancing — so no verdict is favored

## The problem
v5's training labels are skewed toward `adequate`, and the model **inherits that as a bias**: on the corrected gold it predicts `adequate` 156 times at only **35% precision** (it *defaults* to adequate, dumping mismatched/vague/leaks into it), and `mismatched_calibration` recall is just 14%. A majority class the model over-guesses is exactly the failure mode balancing targets.

## What was done
`scripts/balance_dataset.py` (a) drops the two MRBench artifacts we found — multi-turn/malformed candidate messages (Phi3) and `ends-on-tutor` conversations — then (b) downsamples the majority verdicts.

**v5 → cleaned:** 1330 → **1281** rows (dropped **49** artifacts). Clean per-verdict:

| verdict | clean count |
|---|---|
| adequate | **431** |
| gives_final_answer | 236 |
| mismatched_calibration | 218 |
| gives_away_key_step | 217 |
| vague_unhelpful | 179 |

## Two balanced candidates produced

| file | strategy | rows | distribution |
|---|---|---|---|
| **`data/raw/v6_balanced.jsonl`** | **cap 230** (recommended) | **1074** | adequate 230 · gives_final 230 · mismatched 218 · gives_away 217 · vague 179 |
| (reference, in tmp) | full balance → min (179 each) | 895 | 179 across all 5 |

**Recommended: the cap-230 version.** It removes the `adequate` over-representation (431→230) — the actual source of the bias — while discarding only ~200 rows. Full-min (179 each) is perfectly even but throws away ~30% of the data, which for a 1.7B SFT is a real cost.

## Best option (needs the sources work): augment, don't downsample
Downsampling fixes the *ratio* but shrinks the set. The ideal is to **raise the minorities** (`vague` 179, `gives_away` 217, `mismatched` 218) up to ~250 by mining + judge-relabeling unused MRBench/MathDial (see `docs/dataset_size_and_sources.md`), giving a fully even **~1250-row** set with *no* data loss. That's the v6 data target.

## How to use / validate
- Retrain `adapters/v6` on `v6_balanced.jsonl` (same config), re-score on the corrected gold, and check whether `adequate` precision rises and `mismatched` recall improves without a leak-recall regression.
- Treat balanced-vs-imbalanced as an ablation — balancing *usually* helps majority-bias but can hurt if a class is genuinely more common at inference; the corrected frozen eval (adequate 64/299 ≈ 21%) suggests adequate is *not* dominant at test time, so de-biasing should help.
- Reproduce: `python scripts/balance_dataset.py --cap 230`.
