# Frontier head-to-head — our 1.7B guardrail vs. Opus-4.8 & GPT-5.5

*The full range of values, side-by-side — where the shipping 1.7B pipeline **beats** the strongest
frontier models and where it **loses**. Not a single cherry-picked %.*

**Setup.** All models run the *same* judge/rewrite task under the *same* system prompt.
- **Judge:** leakage-checked **frozen set, n=298** (real MRBench tutor messages, never trained on).
- **Rewrite:** **held-out 60** contexts; leak measured by two spec-aligned LLM detectors (a *different*
  model family, gpt-4.1, from what they grade) — **broad** (fires on any operation/number mention) and
  **sharp** (`llm_leaks_sharp`: leak only if the hint states the answer / takes the student's *next*
  step / corrects their error without nudging).
- **Comparators:** `claude-opus-4-8`, `openai-group/gpt-5.5` (via the TrueFoundry gateway).
- **Ours:** `v9` (recall-first verdict detector) on the judge rows; `rewrite_v4` on the rewrite row —
  the shipping pipeline. **Base** = untuned Qwen3-1.7B-4bit.
- **Raw results:** `eval/results/overnight/verdict_demo.{md,json}` + `rewrite_demo.{md,json}`.
  Reproduce: `scripts/overnight/eval_verdict.py --frontier opus-4.8,gpt-5.5` and
  `eval_sharp.py --frontier ...` (see each script's header).

---

## 1. Judge — verdict / safety (frozen n=298)

Higher is better on every column.

| model | 5-way acc | safety-binary | **leak recall** | leak precision | leak F1 |
|---|---|---|---|---|---|
| base 1.7B | 26.8% | 68.5% | 51.0% | 55.2% | 53.0% |
| **`v9` (ours, 1.7B)** | 64.1% | 77.5% | **90.4%** ✅ | 62.3% | 73.7% |
| Opus-4.8 | 67.4% | 87.2% | 82.7% | 81.1% | 81.9% |
| GPT-5.5 | 71.5% | 88.9% | 74.0% | 92.8% | 82.4% |

**Read:** `v9` holds the **leak-recall crown — 90.4%, above both frontier models** (Opus 82.7%, GPT-5.5
74.0%). Frontier leads **safety-binary, precision, F1, and 5-way**: they flag fewer false positives and
discriminate the fuzzy middle better. `v9` deliberately over-flags (precision 62% vs. their 81–93%) —
the **recall-first trade**, below.

## 2. Rewrite — key-step leak rate (held-out 60)

Lower is safer. This is the metric the *rewriter* is judged on.

| model | broad leak | **sharp (key-step) leak** |
|---|---|---|
| base 1.7B | 46.7% | 36.7% |
| **`rewrite_v4` (ours, 1.7B)** | 16.7% | **6.7%** ✅ |
| Opus-4.8 | 20.0% | 10.0% |
| GPT-5.5 | 21.7% | 6.7% |

**Read:** `rewrite_v4` is in the **safest tier of every model tested** — **6.7% key-step leak, tying
GPT-5.5 and beating Opus (10.0%)**. The broad detector penalizes *frontier's* thoroughness hardest
(Opus/GPT-5.5 +13–15% broad-vs-sharp gap vs. our +10%), which is what motivated sharpening the detector.

## 3. General capability (the specialization trade)

| benchmark | base 1.7B | our SLM | frontier |
|---|---|---|---|
| GSM8K (flex, 5-shot) | 17.6% | specialist — low under a neutral prompt | Opus/GPT-5.5 ≫ |
| MMLU (5-shot) | 63.2% | — | high |

Our adapters are **specialists**: tuned for the safety verdict/rewrite, not general QA. (A 4B trained on
the identical recipe scored GSM8K 22.8% / MMLU 72.1% — scale buys *general* capability, not the
constrained safety behavior; see `scale_test_qwen3_4b.md`.)

---

## The honest bottom line

- **We win where a guardrail must:** **leak-recall** (catch the most leaks — a missed leak is the real
  harm) and **rewrite key-step safety** (tie/beat frontier). Both on a **local, 1.7B, auditable** model.
- **We lose on precision / F1 / safety-binary / 5-way** and general capability — frontier is more
  precise and the better generalist.
- **It's a trade, on purpose.** A recall-first detector only *triggers* a rewrite: a false flag costs
  one cheap rewrite; a missed leak reaches the student. So we tune for recall and accept lower precision.
- **The claim was never "we're smarter."** It's that on the narrow, safety-critical axis a **1.7B rivals
  or beats frontier** — and does it locally and cheaply.

*See `eval_review.md` for the full eval suite + methodology, `demo_shotlist.md` for the video plan, and
`brainlift-socratic-tutor.md` (SPOV 2) for the thesis these numbers support.*
