# Tier-2: minimal-pair contrastive augmentation (v9) — the frontier moved, but overshot

`scripts/run_tier2.py` — seeded 80 real v6_consensus contexts, gpt-5.5 generated matched
leaky-corrective / safe-corrective pairs, a cross-family jury (Claude + gpt-4o) kept only pairs both
judges scored leaky=leak & safe=not-leak (**19/80 passed → 38 training rows**), added to v6_consensus,
retrained v9 (687 iters, v6 config). Auto accept/revert on the frozen set with a safe-corrective canary.

## Result — frozen n=298
| metric | v6 | v9 | Δ |
|---|---|---|---|
| leak recall | 59.6% | **89.4%** | +29.8 |
| leak precision | 84.9% | 62.0% | −22.9 |
| leak F1 | 70.1% | 73.2% | +3.2 |
| safety-binary | 82.2% | 77.2% | −5.0 |
| 5-way | 61.7% | 63.8% | +2.0 |
| canary FP (safe-corrective, n=40) | 12.5% | 60.0% | +47.5 |

**Auto-verdict: REVERT (v6 stays)** — leak recall up, but safety-binary and the canary regressed.

## Read — the most encouraging leak-recall result yet, with a clear, fixable flaw
1. **The frontier MOVED (first time in the project).** Leak recall +30 (60→89), F1 +3.2, 5-way +2.0.
   At ~62% precision v9 catches **89%** of leaks vs. the self-consistency knob's 76% at the same
   precision — so *training* on the minimal pairs produced a better recall/precision tradeoff than the
   inference-time trick could. The corrective-framed-leak boundary **is teachable with targeted data**;
   self-consistency could only slide along v6's fixed curve, augmentation moved the curve.
2. **But it overshot + overfit the surface cue.** Precision −23, safety-binary −5, and the canary blew
   up: FP on *safe* corrective messages 12.5%→60%. v9 learned "corrective framing → leak" too crudely
   and now over-flags legitimate corrections — the exact surface-phrasing-overfit risk flagged upfront.
   **The canary caught it (the guard worked).** v9-as-is must not ship (it would nag students on fine
   hints).
3. **Why it overshot:** only **38 rows** made it in (jury strict at 19/80 — correctly strict), and the
   1:1 leaky:safe ratio wasn't enough counterweight — 19 leaky examples pushed recall hard, 19 safe
   couldn't hold precision on a fixed-size model.

## This is a dose/balance TUNING problem, not a dead end
For the first time a training lever moved the leak-recall frontier. Next iteration (v9b):
- **Skew the ratio toward the safe counterweight** (e.g., 1 leaky : 2–3 safe) to hold precision while
  keeping the recall gain.
- **More validated pairs** — 19 is thin; generate more seeds (or a second jury round) to net ~50–80
  clean pairs, so the signal teaches the *subtle* state-vs-elicit distinction rather than the crude cue.
- **Gentler dose** — the added rows may be over-weighted at 687 iters; try fewer, or a lower LoRA rank
  on the add.
- **Combine with the threshold knob** — v9 sits at 62P/89R; applying self-consistency `vote≥m` to v9
  should pull precision back up along its *better* frontier, potentially to a point that dominates v6
  (e.g., ~80P/80R). That's the clean win to aim for.

## Verdict
`sft_v6` stays the ship model. v9 is a promising **partial** — the first frontier movement — needing
ratio/dose tuning + a threshold to land a clean operating point. If a recall-max safety guard is the
product goal, v9 (62P/89R) is a candidate, but the canary argues against it as a default.

Artifacts: `data/tier2/`, `data/raw/v9.jsonl`, `adapters/v9` (gitignored), `eval/results/v9_tier2.md`/
`.json`. Branch `feat/leak-recall-threshold`.

## v9b (safe-dup tuning) — overcorrected to precision
160 seeds → 34 validated pairs → 102 rows at **1 leaky : 2 safe** (`--safe-dup 2`). Result: the canary
was **fixed** (FP 12.5%→12.5%; precision recovered 62%→75.7%) — but it overshot the other way: leak
recall **crashed to 51.0%** (below v6's 59.6%), F1 −9.1, and a **broad** regression (5-way −7.4). So
v9 overshot recall (canary broke); v9b overshot precision (recall below baseline) *and* the 102 added
rows hurt general accuracy. Two failure modes bracketing a narrow sweet spot we didn't hit.

**Refined conclusion:** the minimal-pair lever is a **knife-edge**, and at the row-count needed the
synthetic augmentation causes broad regression (consistent with the gap-loop "adding hurts" finding and
"augment-don't-replace"). The clean leak-recall lever is therefore **not** more training-data tuning —
it's the **inference-time threshold on v6** (self-consistency = 61P/76R, no retraining, no regression),
or the structural routes (discriminative classifier / scale — see `docs/scale_test_qwen3_4b.md`).
`sft_v6` stays ship (now the 6th experiment not to cleanly beat it).
