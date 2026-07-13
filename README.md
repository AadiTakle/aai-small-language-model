# Socratic Tutor Adequacy Judge & Rewriter (Qwen3-1.7B)

A local, fine-tuned **safety guardrail for AI math tutors**. It judges whether a tutor's message
leaks the answer or the pivotal key step and — if flagged — rewrites it into a calibrated Socratic
hint. Built in one week via QLoRA SFT on `mlx-community/Qwen3-1.7B-4bit` (MLX, Apple Silicon).

**Behavior spec (the gate, falsifiable):** *a tutor message is adequate iff it neither states the
final answer nor hands over the single key step/insight that trivializes the problem; it scaffolds
with a question or calibrated hint instead.* See [`docs/behavior_spec.md`](docs/behavior_spec.md).

**Thesis:** for a small safety-critical judge, the lever is **the data and the honest metric, not
scale** — a fixed 1.7B went from 2% → 90% leak-recall on labels alone, and a 2.4×-scale 4B trained
identically did **not** beat it.

---

## Shipped artifacts (Hugging Face)

| artifact | what it is | link |
|---|---|---|
| **Judge `v9`** | recall-first verdict **detector** (fused 1.7B) | [atakle/socratic-tutor-judge-v9-1.7b](https://huggingface.co/atakle/socratic-tutor-judge-v9-1.7b) |
| **Rewriter `rewrite_v4`** | safe Socratic **rewriter** (fused 1.7B) | [atakle/socratic-tutor-rewriter-v4-1.7b](https://huggingface.co/atakle/socratic-tutor-rewriter-v4-1.7b) |
| **Dataset** | the real deliverable — 6 files, 3,157 rows + card | [atakle/socratic-tutor-data](https://huggingface.co/datasets/atakle/socratic-tutor-data) |
| **4B scale probe** | Qwen3-4B judge, identical recipe (falsification test) | [atakle/socratic-judge-4b](https://huggingface.co/atakle/socratic-judge-4b) |

**Ship pipeline:** `v9` judges a tutor message → **if flagged as a leak**, `rewrite_v4` rewrites it
into an operation-free guiding question. Two 1.7B QLoRA adapters, run locally.

---

## Headline results (the heuristics)

Measured base vs. tuned vs. **the strongest frontier (Opus-4.8 + GPT-5.5)**. Full table + provenance:
[`docs/frontier_comparison.md`](docs/frontier_comparison.md).

| metric | base 1.7B | **ours** | Opus-4.8 | GPT-5.5 |
|---|---|---|---|---|
| Judge — **leak recall** (ship metric ↑) | 51.0% | **90.4%** ✅ | 82.7% | 74.0% |
| Judge — safety-binary | 68.5% | 77.5% | 87.2% | 88.9% |
| Judge — leak precision | 55.2% | 62.3% | 81.1% | 92.8% |
| Judge — 5-way acc | 26.8% | 64.1% | 67.4% | 71.5% |
| Rewrite — key-step leak (↓ safer) | 36.7% | **6.7%** ✅ | 10.0% | 6.7% |

**The honest read:** we **win where a guardrail must** — leak-**recall** (catch the most leaks) and
**rewrite key-step safety** (tie/beat frontier) — on a local 1.7B. We **lose** on precision / F1 /
safety-binary / 5-way: frontier is more precise and the better generalist. That's the **recall-first
trade, on purpose** — a false flag just spends a rewrite; a missed leak reaches the student.
**Scale isn't the lever:** the 4B gains only noise on the safety behavior while winning on general
benchmarks (GSM8K/MMLU) — safety is a *data* property.

---

## Run the demo (web UI)

```bash
.venv/bin/python webui/run.py --port 8010      # then open http://127.0.0.1:8010
```
In the **Compare** tab pick **"Ship pipeline (v9 → rewrite_v4)"**, paste a leaky tutor message, and
watch `v9` flag it and `rewrite_v4` fix it. Base / `v6` / frontier judges are available side-by-side.
For a snappy recording, run with no eval jobs competing for the GPU.

## Run inference / evals from the CLI

```bash
# base-model sanity check
.venv/bin/python scripts/infer.py "your prompt here"

# judge eval (frozen set) — base vs tuned vs frontier
.venv/bin/python scripts/overnight/eval_verdict.py --models base,v9 --frontier opus-4.8,gpt-5.5

# rewrite leak re-measure (broad vs sharp detector), held-out 60
.venv/bin/python scripts/overnight/eval_sharp.py --frontier opus-4.8,gpt-5.5
```

The tuned models are QLoRA adapters in `adapters/` (gitignored, regenerable) over
`mlx-community/Qwen3-1.7B-4bit`; the HF repos above host the **fused** standalone versions.

---

## The eval suite + criteria (the "heuristics")

Full detail + methodology in [`docs/eval_review.md`](docs/eval_review.md); every rubric spelled out in
its §5. In short:

- **Objective safety axis** (the headline): `LEAK = {gives_final_answer, gives_away_key_step}` vs.
  `SAFE`. We report **leak precision / recall / F1** and **safety-binary** separately from the fuzzy
  5-way quality axis (which even GPT-4o and Claude split ~60% of the time).
- **Four leak detectors**, evolved over the project: deterministic → broad (`llm_leaks`) → crisp →
  **sharp (`llm_leaks_sharp`)**, the honest one: *does the hint take the student's **next** step, or
  leave it for them?* The measurement detector is a **different model family** (gpt-4.1) from what it
  grades, and was itself validated (caught over-flagging, then sharpened).
- **Frozen eval set** (n≈300): real MRBench tutor messages, leakage-checked, never trained on.
- **Cross-family jury** for anything subjective — anonymized, position-debiased, teacher excluded
  (we learned the hard way: same-model self-agreement rubber-stamps its own bias).
- **Adversarial stress test** (cave-rate over escalating "just tell me" turns) + **traditional
  benchmarks** (GSM8K / MMLU, forgetting check) + **dataset-scaling** and **4B scale** curves.

---

## Environment setup (local, Apple Silicon Mac)

Inference and 1.7B QLoRA training both run **locally via [MLX](https://github.com/ml-explore/mlx)** —
no cloud GPU needed. (Only the 4B scale probe used Colab/CUDA.)

```bash
python3.14 -m venv .venv       # any Python 3.11+ works
source .venv/bin/activate
pip install -r requirements.txt
```

**Known gotcha:** `mlx-lm` declares `transformers>=5.0.0`, but that breaks its tokenizer registration
on import. `requirements.txt` pins `transformers==4.57.6`, which works. Also note the `mlx_lm` CLIs are
console scripts (`.venv/bin/mlx_lm.lora`, `mlx_lm.fuse`, `mlx_lm.evaluate`) or `python -m mlx_lm
<subcommand>` — **not** `python -m mlx_lm.evaluate` (no `__main__` guard). Qwen3 emits a
`<think>…</think>` trace by default; the judge/rewriter prompts disable it.

## Repo layout

- **[`SUBMISSION.md`](SUBMISSION.md)** — start here: the 5 deliverables → status + all links.
- `docs/behavior_spec.md` — the locked, falsifiable behavior spec.
- `docs/eval_review.md` — eval suite + results + retrospective + exact criteria (§5).
- `docs/frontier_comparison.md` — full head-to-head vs Opus-4.8 & GPT-5.5 (win/lose range).
- `docs/model_devlog.md` — per-version dev-log (v1 → ship): goal / change / metric / decision.
- `docs/brainlift-socratic-tutor.md` — the two-part thesis (learning-science + SLM-training), sourced.
- `docs/project_report.md` — full experiment log; `docs/demo_shotlist.md` — the 3–5 min video plan.
- `socratic_tutor/` — library: `config.py`, `prompts.py`, `rubric.py`, `io_utils.py`.
- `scripts/` — `infer.py`, `eval_harness.py`, and `scripts/overnight/` (the eval + data-gen +
  scaling pipeline: `eval_verdict`, `eval_rewrite`, `eval_sharp`, `stress_ship`, `bench_run`,
  `scale_boundary`, `eval_4b_judge`, `split_common`).
- `webui/` — the inference demo (`run.py`, `engine.py`, `models.json`).
- `data/` — training/eval data + `data/hf/` (published bundles); `adapters/` — trained adapters
  (gitignored, regenerable; ship: `v9`, `rewrite_v4`).

## Status

- [x] Behavior spec locked; behavior researched (brainlift + 5-condition gap probe)
- [x] Eval harness (frozen set, safety axis, 4 detectors, cross-family jury, stress test, benchmarks)
- [x] Data-gen pipeline + published dataset (3,157 rows)
- [x] Fine-tuning: v1 → **v9 judge** + **rewrite_v4 rewriter** shipped; DPO/CoT/relabel/scale ablations
- [x] Models + demo published to HF; results measured base vs tuned vs frontier
- [ ] Demo video (record from `docs/demo_shotlist.md`)
