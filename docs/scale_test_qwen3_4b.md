# Qwen3-4B scale test — falsifying (or refining) the "data, not scale" thesis

> *Superseded framing: the frontier safety-binary comparisons below predate the Opus-4.8/GPT-5.5 suite.
> Current, consistent numbers are in [`eval_review.md`](eval_review.md) §2 — the durable frontier win is
> **leak-recall** (v9 90.4% > Opus 82.7% / GPT-5.5 74.0%); frontier leads safety-binary/precision. The
> scale conclusion here (scale ≠ the lever) is unaffected and stands.*

## Purpose + honest framing
Re-run the same data-centric recipe on a **4B** base instead of 1.7B and see whether scale materially
changes the result. Thesis prediction: **little/no difference on the metrics that matter** → confirms
"≈80% of the outcome is the data, not the model size." **This is a falsification test, not a
confirmation exercise** — write down the predictions below *before* looking, report whatever happens,
and if 4B materially helps, update the thesis + Brainlift (SPOV 1/2). "Even better if negative" is the
hoped-for result, but the value is in running it honestly.

## Pre-registered predictions (commit to these first)
- **safety-binary:** ~flat (±2–3 pts). v6-1.7B already beats GPT-4o/Claude here → data-bound/near-
  ceiling; scale shouldn't add much.
- **5-way accuracy:** ~flat. Dominated by the fuzzy quality axis (intrinsic ambiguity) → scale can't
  fix what frontier models can't agree on either.
- **leak recall:** THE one to watch — it's capacity-bound. 4B *might* improve it.
  - Flat too → thesis **strongly confirmed** (even the capacity-bound metric is data-coverage-bound).
  - Jumps a lot → thesis **refined, not refuted**: "data gets you the ceiling *for a given size*;
    scale raises that ceiling only on the discrimination-hard sub-metric." Update SPOV 2's scope.
  - Everything jumps → thesis **challenged**; reevaluate.
- **v8 thinking at 4B:** does CoT stop hurting? If v8-4B no longer regresses, that supports "reasoning
  needs scale" (Brainlift Insight 7's caveat). If it still hurts, small-model-CoT-fails generalizes
  past 1.7B.

## Setup (once)
1. Base exists as a pre-quantized drop-in: `mlx-community/Qwen3-4B-4bit` (downloads on first load).
2. Branch: `git checkout -b feat/scale-test-4b`
3. Point the project at 4B — edit `socratic_tutor/config.py`: `MODEL = "mlx-community/Qwen3-4B-4bit"`.
   The Qwen3 tokenizer is **shared across sizes**, so the data renders identically — only the model
   changes. This one global switch is read by build/train/eval alike.
4. Memory/time: 4B QLoRA ≈ 11–13 GB peak (fits a 24 GB Mac), ~2–3× the 1.7B wall-clock per version
   (≈1.5–2.5 hr each). Run **sequentially** (each build overwrites `data/mlx`), ideally in the
   background one at a time. Keep the Mac awake (`caffeinate`).

## Per-version recipe (build → train → eval)

### v6-4B — the core thesis test  (ENABLE_THINKING = False, the default)
```
python scripts/build_dataset.py --raw data/raw/v6_consensus.jsonl --out-dir data/mlx
python -m mlx_lm lora --train --model mlx-community/Qwen3-4B-4bit --data data/mlx \
    --adapter-path adapters/v6-4b -c configs/lora_v1.yaml --iters 687
python scripts/eval_adapter.py --adapter adapters/v6-4b --tag v6-4b
```
This is the headline comparison: **v6-4B vs v6-1.7B on the safety axis.**

### v9(b)-4B — does scale move the leak-recall frontier?  (ENABLE_THINKING = False)
```
python scripts/build_dataset.py --raw data/raw/v9b.jsonl --out-dir data/mlx   # use v9.jsonl if v9b didn't land
python -m mlx_lm lora --train --model mlx-community/Qwen3-4B-4bit --data data/mlx \
    --adapter-path adapters/v9-4b -c configs/lora_v1.yaml --iters 687
python scripts/eval_adapter.py --adapter adapters/v9-4b --tag v9-4b
```

### v8-4B — does thinking stop hurting at 4B?  (ENABLE_THINKING = True)
```
# edit config.py: ENABLE_THINKING = True
python scripts/build_dataset.py --raw data/raw/v6_consensus.jsonl --traces data/raw/v8_traces.jsonl --out-dir data/mlx
python -m mlx_lm lora --train --model mlx-community/Qwen3-4B-4bit --data data/mlx \
    --adapter-path adapters/v8-4b -c configs/lora_v1.yaml --iters 687
python scripts/eval_adapter.py --adapter adapters/v8-4b --tag v8-4b --max-tokens 1024
# revert config.py: ENABLE_THINKING = False afterward
```

### v7-4B — optional / lowest priority  (ENABLE_THINKING = False)
The v7 relabel data was over-flipped (a blind jury rejected it), so v7-4B mostly tests "bad labels at
4B." Run only for a complete v6–v9 sweep:
```
python scripts/build_dataset.py --raw data/raw/v7.jsonl --out-dir data/mlx
python -m mlx_lm lora --train --model mlx-community/Qwen3-4B-4bit --data data/mlx \
    --adapter-path adapters/v7-4b -c configs/lora_v1.yaml --iters 687
python scripts/eval_adapter.py --adapter adapters/v7-4b --tag v7-4b
```
Caveat: v7's *prompt* had the decision tree; this branch uses the v6 prompt. To reproduce v7 faithfully
you'd also restore the tree in `SYSTEM_PROMPT`. Simplest: skip v7 unless you need the full sweep.

## Fill in this table (1.7B refs from the frozen evals)
| model | leak recall | leak precision | safety-binary | 5-way |
|---|---|---|---|---|
| **v6-1.7B (ref)** | 59.6% | 84.9% | 82.2% | 61.7% |
| v6-4B | | | | |
| **v9-1.7B (ref)** | 89.4% | 62.0% | 77.2% | 63.8% |
| v9-4B | | | | |
| **v8-1.7B (ref)** | — | — | 74.8% | 50.3% |
| v8-4B | | | | |

## Interpretation (decide the rule before you look)
- v6-4B safety-binary within **±3 of 82.2%** → thesis holds (data, not scale).
- v6-4B leak recall **≈ 60%** → thesis strongly holds (the gap is data-coverage, not size).
- v6-4B leak recall **≫ 60%** → thesis **refined**: scale raises the size-ceiling on the one
  capacity-bound residual. Update Brainlift SPOV 2 scope to "labels + metric are the lever *up to the
  model's size ceiling*; scale lifts that ceiling only on discrimination-hard sub-metrics."
- v8-4B **no longer regresses** → "reasoning needs scale" becomes the headline (Insight 7 flips from
  caveat to claim).
- **Everything jumps materially** → thesis challenged; rewrite SPOV 2 and flag it in the report.

## If 4B is inconclusive
Escalate to **Qwen3-8B** (MLX can QLoRA it ~16 GB but slowly; A100/Colab is the cleaner path — same
recipe, `MODEL` = the 8B base). Only worth it if 4B shows a *trend* worth confirming — don't run 8B on
a null 4B result (that itself is the thesis-confirming answer).

## Why we expect ~no difference (the mechanism, for the writeup)
The two ceilings from `docs/project_report.md`: (A) discrimination capacity — the only place scale can
help, and only for leak recall; (B) intrinsic ambiguity of the quality axis — where even frontier
models are stuck, so scale can't help the 5-way number. On the *shipped* metric (safety-binary), v6 is
already frontier-beating at 1.7B, so there's little headroom for scale to demonstrate. A flat 4B result
isn't a failure to improve — it's the thesis, measured.
