# Leak-recall Tier-1: self-consistency threshold sweep (v6, no retraining)

`scripts/eval_self_consistency.py` — sample k=5 @ temp 0.7 from v6 on the frozen set (n=298), predict
LEAK when ≥m of 5 samples say leak (m=1 = OR = max recall … m=5 = unanimous = max precision). Draws
v6's leak precision/recall curve with NO retraining. Sanity: greedy reproduces stored v6 exactly.

## Result — frozen set n=298
| setting | leak P | leak R | leak F1 | safety-binary | 5-way |
|---|---|---|---|---|---|
| **greedy (v6 today)** | 84.9% | 59.6% | 70.1% | 82.2% | 61.7% |
| `vote≥1/5` (OR, max recall) | 60.8% | **76.0%** | 67.5% | 74.5% | 56.7% |
| `vote≥2/5` | 72.7% | 61.5% | 66.7% | 78.5% | 58.1% |
| `vote≥3/5` | 82.6% | 54.8% | 65.9% | 80.2% | 58.4% |
| `vote≥4/5` | 84.3% | 41.3% | 55.5% | 76.8% | 55.0% |
| `vote≥5/5` | 90.0% | 26.0% | 40.3% | 73.2% | 52.3% |

## Read
1. **Recall is movable without retraining**: OR lifts leak recall 59.6% → **76.0%** (+16.4). Not a hard
   capacity wall — sampling recovers a real chunk of the missed leaks.
2. **But it's a trade, not a free win**: that recall costs precision 84.9% → 60.8% (−24), safety-binary
   82.2% → 74.5% (−8); leak F1 *slips* 70.1 → 67.5. Greedy is the F1-optimal point on the curve.
3. **Mixed signal — partly threshold, partly systematic**: pure noise → recall up / precision flat;
   pure systematic → recall flat. We saw recall-up AND precision-down → v6's sample-level uncertainty
   is real but **miscalibrated** (fires spurious leak-votes on some safe items). The boundary is
   genuinely fuzzy, not just mis-thresholded.

## What it buys now (zero training)
A **tunable safety knob**: greedy = balanced (85P/60R); `vote≥1/5` = recall-max safety mode (61P/76R).
For a tutor-safety guard where a *missed* leak is the expensive error, the recall mode is a legitimate
shippable operating point — chosen by the false-alarm-vs-missed-leak cost ratio. (For context, the
retrained v7 sits at 73P/72R — a middle point — but requires shipping v7 with its other regressions;
self-consistency gives v6 the knob with no retrain.)

## What it means for next steps
Self-consistency **slides along the current frontier; it doesn't move it.** The steep precision cost of
chasing recall shows the real lever is sharpening the discrimination so the whole curve lifts (higher
precision at a given recall). → **Tier 2 (minimal-pair contrastive augmentation)** is warranted: teach
the corrective-framed-leak boundary so v6 separates leak from safe more cleanly.

## Recommendation
- Offer the self-consistency OR mode as an optional high-recall safety setting (free, now).
- Proceed to **Tier 2** to actually improve the precision/recall frontier.

Artifacts: `scripts/eval_self_consistency.py`, `eval/results/v6_self_consistency.md`/`.json`.
Branch `feat/leak-recall-threshold`.
