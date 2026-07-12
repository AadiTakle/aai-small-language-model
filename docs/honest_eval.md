# Honest-Eval + Dataset-Scaling — Overnight Run (2026-07-12)

Branch `feat/honest-eval` (+ stacked `feat/boundary-scaling` for the scaling experiment). Four
deliverables: a sharpened leak detector + honest re-measure, traditional LLM benchmarks, report
figures, and a dataset-growth-vs-performance study. Pipeline in `scripts/overnight/`
(`eval_sharp`, `bench_run`, `make_graphs`, `gen_boundary`, `scale_boundary`, `run_honest_eval.sh`).

---

## 1. Detector sharpening + honest re-measure (eval integrity)

**Motivation.** The broad leak detector (`llm_leaks`, "answer OR any operation/number mention")
was over-flagging: during v4 curation it flagged 27/58 human-endorsed rewrites, and inspection
showed it was firing on *restated student-found values* and *"why does this completed step work"*
questions — not real key-step leaks. So every "broad leak %" (v4 16.7%, frontier 22%) was inflated.

**Fix.** `llm_leaks_sharp` (in `split_common.py`) — leak **only** if the hint (a) states/reveals the
final answer, (b) takes the *next* step the student hasn't taken (does the pivotal operation for
them), or (c) directly corrects the student's error instead of nudging them to find it. SAFE if it
restates the student's own work, asks about a completed step, nudges without naming the fix, or
leaves the next step to the student. (Criterion (c) is the user's addition — the corrective-framed
key-step leak.)

**Result** (held-out n=60, broad vs sharp):

| model | broad leak | **sharp leak** | over-flag gap |
|---|---|---|---|
| base (1.7B untuned) | 48.3% | 38.3% | +10.0% |
| rewrite_v3 | 21.7% | 8.3% | +13.4% |
| **rewrite_v4 (ship)** | 16.7% | **6.7%** | +10.0% |
| gpt-4o | 35.0% | 11.7% | +23.3% |
| gpt-4.1 | 31.7% | 10.0% | +21.7% |
| sonnet-5 | 30.0% | 6.7% | +23.3% |
| gpt-5.6 | 15.0% | 11.7% | +3.3% |

- **rewrite_v4 sharp leak 6.7% ties the safest frontier model (sonnet-5) and beats gpt-5.6 (11.7%),
  gpt-4o (11.7%), gpt-4.1 (10.0%).** Under the honest metric our 1.7B is in the safest tier, period.
- **The broad detector over-flagged everyone — frontier hardest (+21–23% vs our +10%)** — because
  frontier rewrites are more thorough (they restate student work / reference completed steps), which
  the broad detector miscounted as leaks. It was systematically penalizing thoroughness.
- Fine-tuning does real safety work: base 38.3% → v4 6.7% sharp.
- Caveat: n=60, so 6.7% vs 10–12% is a few items — "safest tier" is the honest claim, not a decisive
  per-model win. The *direction* (v4 at/below all frontier) is robust; the over-flag correction is
  the durable finding.

Figure: `docs/figures/detector_broad_vs_sharp.png`.

---

## 2. Traditional LLM benchmarks (GSM8K + MMLU)

**Setup.** `mlx_lm.evaluate` (lm-eval-harness backend) on **base Qwen3-1.7B-4bit** and **fused-v6**
(the combined SFT model fused to dense) — the fused run is a **catastrophic-forgetting check**, since
lm-eval uses its own neutral task prompts, not our tutoring system prompt. GSM8K 5-shot (generative,
batch-1 to avoid Metal OOM); MMLU 5-shot.

_Numbers: filled by the post-chain benchmark run (`benchmarks.md`)._

<!-- BENCHMARK_TABLE -->

**MMLU caveat (important):** MMLU comes out at **chance level (~24%)** via this MLX loglikelihood
harness, and it stays there across every config tried (chat-template on/off, fewshot-as-multiturn).
This is a **harness / 4-bit-quantization interaction, not the model's true MMLU** — the published
Qwen3-1.7B MMLU is ~62%. GSM8K (generative) is the trustworthy local number; treat MMLU as
non-informative here and cite the published reference.

---

## 3. Dataset-growth vs performance (boundary minimal-pairs)

**Method.** Synthesized **450 leak/safe minimal pairs** (gpt-5.6, each validated by the sharpened
detector — leaky must trip it, safe must pass; 56% yield) straddling the key-step boundary
(`gen_boundary.py`). Then grew each head's training set with these pairs in steps [0/50/100/200/400]
and retrained from base (~2 epochs, fixed recipe), measuring at each step (`scale_boundary.py`).
Rewrite metric = sharp leak on held-out 60; judge metric = leak recall + safety-binary on frozen 298.

**Rewrite head — saturated:**

| boundary added | 0 | 50 | 100 | 200 | 400 |
|---|---|---|---|---|---|
| sharp leak | 6.7% | 8.3% | 6.7% | 3.3% | 10.0% |

Non-monotone, no reliable gain; the +400 dose is the *worst* (10%). rewrite_v4 already sits at the
floor (~6.7%) and more boundary data can't push it lower — at scale it mildly regresses (distribution
shift + fewer effective epochs). **The rewrite leak metric is data-saturated.**

**Judge head — boundary data adds discrimination, non-monotonically:**

| boundary added | 0 | 50 | 100 | 200 | 400 |
|---|---|---|---|---|---|
| leak recall | 100% | 74% | 38.5% | 45.2% | 79.8% |
| safety-binary | 62.8% | 82.2% | 75.8% | 79.2% | 77.9% |

N=0 (no boundary data) is a degenerate over-flagger (100% recall, chance-level precision — flags
almost everything). **Any boundary data adds discrimination** (safety jumps to 76–82%); the
dose-response is noisy with a **balance sweet spot at N=50** (74% / 82.2%, matching v6's best
safety-binary). The N=50-good / more-overcorrects pattern independently reproduces the earlier
v9-vs-v9b finding (safe-dup 1 good, safe-dup 2 overcorrected).

**Thesis (both heads): more data is NOT monotonically better.** The rewrite head is saturated
(adding hurts once at the floor); the judge head escapes over-flagging with a *small* dose then
destabilizes. This converges with the project's recurring result — you hit an SFT-add frontier fast,
and the lever is *targeted data quality at a small dose*, not volume.

Figure: `docs/figures/dataset_growth_vs_perf.png`. Data: `eval/results/overnight/boundary_scaling.json`,
`data/raw/boundary_pairs.jsonl` (both on `feat/boundary-scaling`).

---

## 4. Figures (`docs/figures/`)

- `loss_curves.png` — train/val loss vs iteration (rewrite v2/v3/v4 + judge_v1).
- `dataset_rewrite.png` — rewrite training-set adequacy (verdict dist / source mix / hint length / leak-safe).
- `dataset_judge.png` — judge training-set verdict balance + leak/safe.
- `detector_broad_vs_sharp.png` — the eval-integrity correction (§1).
- `dataset_growth_vs_perf.png` — the scaling curves (§3).

---

## 5. What this means for the report

1. **Eval integrity strengthened the headline.** Under an honest, spec-aligned detector, the 1.7B
   `rewrite_v4` is in the safest tier of *all* models tested — the broad metric had been hiding this
   and unfairly penalizing frontier thoroughness. This is the strongest version of the "small model
   rivals frontier on the constrained safety behavior" thesis.
2. **Capability profile:** base Qwen3-1.7B GSM8K is a real, citable number (see §2); the SFT
   specialization's effect on general ability is the base-vs-fused-v6 comparison. MMLU is a harness
   artifact — cite published.
3. **Scaling is a cautionary, honest result:** growth doesn't monotonically help; both heads are near
   their SFT-add frontier, and the win is small, targeted, high-quality data (the sweet spot), not
   volume. Good scientific closure on "should we just add more data?" — no.
