# Socratic Tutor Adequacy Judge & Rewriter

One-week SFT (QLoRA) project: fine-tune a small open base model to judge whether a tutor's message adequately scaffolds a math student (vs. leaking the answer or key step) and, if not, rewrite it into a calibrated Socratic hint. See [`docs/behavior_spec.md`](docs/behavior_spec.md) for the falsifiable behavior spec this project is built around.

## Where is the model?

**The model weights are not stored in this repo.** They live in the standard Hugging Face cache on disk:

```
~/.cache/huggingface/hub/models--mlx-community--Qwen3-1.7B-4bit/
```

`scripts/infer.py` only references the model by its Hugging Face repo name (`mlx-community/Qwen3-1.7B-4bit`). The first time it runs, `mlx_lm.load()` downloads the weights (~900MB, 4-bit quantized) into that cache directory; every run after that loads from the local cache with no network call. This is standard `huggingface_hub` behavior shared across any tool on the machine — it's not project-specific and is intentionally excluded from git (model weights don't belong in version control; the dataset and code are the actual deliverables).

If you're grading this and want to reproduce inference from scratch: set up the environment below and run `scripts/infer.py` — it will fetch the model automatically.

## Environment setup (local, Apple Silicon Mac)

This runs inference locally via [MLX](https://github.com/ml-explore/mlx) (Apple's array framework) — no CUDA/GPU cloud needed for inference. Fine-tuning (QLoRA) will need a CUDA GPU (cloud) since the project's suggested stack (Unsloth) doesn't run on Apple Silicon; MLX's native LoRA support is a possible all-local alternative, to be decided later.

```bash
python3.14 -m venv .venv       # any Python 3.11+ works; 3.14 via Homebrew used here
source .venv/bin/activate
pip install -r requirements.txt
```

**Known gotcha**: `mlx-lm`'s declared dependency is `transformers>=5.0.0`, but that version currently breaks `mlx-lm`'s tokenizer registration on import. `requirements.txt` pins `transformers==4.57.6`, which works. If you `pip install mlx-lm` fresh without the pin, expect an `AttributeError` on import.

## Running inference

```bash
python scripts/infer.py "your prompt here"
```

Loads the base model (`mlx-community/Qwen3-1.7B-4bit`) and generates a response. Note: Qwen3 defaults to a `<think>...</think>` reasoning trace before its answer — budget `max_tokens` accordingly, or it can burn its whole budget thinking without ever emitting a final answer.

## Repo layout

- `docs/behavior_spec.md` — the locked, falsifiable behavior spec (data-gen rubric + eval criterion in one).
- `docs/project_spec.md` — the original assignment/rubric.
- `docs/brainlift-socratic-tutor.md` — behavior thesis (learning-science grounding + empirical evidence on why LLM tutors leak answers).
- `docs/tutor_gap_probe_*.md` — empirical validation of the litmus test ("a well-prompted base model can't already do this reliably"): 5 conditions tested (naive prompt, engineered prompt, Self-Refine, independent Judge+Rewrite, surgical patch), none reliably hold the behavior under pressure.
- `scripts/infer.py` — minimal local inference entry point.
- `requirements.txt` — pinned working dependencies for the MLX inference environment.

## Status

- [x] Behavior spec locked
- [x] Behavior researched (brainlift + 5-condition empirical gap probe)
- [x] Local inference environment working, base model runs and responds
- [ ] Eval harness
- [ ] Data-gen pipeline
- [ ] v1 dataset + base-vs-tuned numbers
- [ ] Fine-tuning run
