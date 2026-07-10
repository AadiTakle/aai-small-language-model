# Live Review Brief — Socratic Tutor SLM

One-line framing: **the dataset is the deliverable.** Base model is fixed (Qwen3-1.7B-4bit),
hyperparameters are fixed — every iteration this week changed *data* (labels, sources,
balancing, format), and the eval harness exists specifically to prove each change actually
helped rather than trusting intuition.

---

## 1. Sample of the training data

One real row from `data/raw/v6_consensus.jsonl` (verdict = `gives_away_key_step`):

```json
{
  "id": "exp-k2a-003",
  "band": "K-2",
  "problem": "Double 6.",
  "correct_solution": "Doubling means adding the number to itself: 6 + 6 = 12.",
  "final_answer": "12",
  "key_step": "recognize that 'double' means add the number to itself",
  "conversation_history": ["Student: I don't remember what double means."],
  "candidate_message": "Doubling a number means adding it to itself. So for double 6, what two numbers would you add together?",
  "verdict": "gives_away_key_step",
  "reasoning": "The student said they don't remember what 'double' means, so that meaning is exactly the key step; the candidate defines 'doubling means adding it to itself,' handing over the one thing being asked.",
  "rewritten_message": "You said you're not sure what 'double' means — that's the exact spot to figure out first. Think about what happens to an amount when you double it: does it get bigger or smaller, and roughly by how much? Once you decide what 'double' does to a number, try it on 6.",
  "slice": "core",
  "relabeled": "regenerated"
}
```

Each row is a candidate tutor turn to *judge and rewrite*, not a question to answer. The
model's job is the `{verdict, reasoning, rewritten_message}` triplet. This structured row is
rendered through the project's Qwen3 chat template (`socratic_tutor/prompts.py`) into a single
`text` field for actual training — that's what `data/mlx/train.jsonl` holds, one line per
example, ready for `mlx_lm lora`.

---

## 2. How the data was collected & organized

- **Sources**: real tutor-student dialogues from MRBench (Bridge novice/expert pairs + MathDial
  subset) — human/expert-annotated, not synthetic-only. Synthetic generation (via an LLM
  gateway) fills in underrepresented verdict classes where real data is thin.
- **Labeling**: multi-model **jury consensus**, not a single LLM-as-judge — the literature
  (and this project's own testing) shows a single judge correlates poorly with humans on
  fine-grained pedagogical dimensions. Cross-family agreement κ=0.69, 98% self-consistent,
  spot-checked against human judgment.
- **Quality gates**: dropped 49 artifact rows (malformed multi-turn candidates, conversations
  that end on the tutor's turn rather than the student's) — 1330 → 1281 clean rows.
- **Balancing**: deliberately moved from "downsample the majority classes" (cap-230 strategy,
  1074 rows) to **"augment the minority classes instead"** for v6+ — real added data beats
  throwing away majority-class rows.
- **Eval set kept separate and frozen** from day one, expanded over the week (103 → ~298 rows)
  and relabeled independently, specifically so training-data mistakes can't also corrupt the
  scorecard.

Full detail: `docs/dataset_size_and_sources.md`, `docs/dataset_balancing.md`.

---

## 3. How much data so far

| Set | Rows | File |
|---|---|---|
| Raw consensus-labeled pool | 1330 | `data/raw/v6_consensus.jsonl` |
| Train / valid / test split (actual v6 training run) | 915 / 114 / 115 | `data/mlx/*.jsonl` |
| Frozen held-out eval set (never trained on) | ~298 (started at 103, expanded) | `eval/gold/frozen_eval.jsonl` |
| DPO preference pairs mined | 357 | `data/dpo/bridge_mathdial_pairs.jsonl` |

Context: the project's own sizing analysis recommended ~1,000–1,500 examples — already in
range. Size is demonstrably **not** the current bottleneck: an automated pipeline that only
added more SFT rows produced zero net improvement, while *relabeling* the same rows moved leak
recall from 2%→35%. That's the strongest evidence for the "quality over volume" framing.

---

## 4. Training plan

- **Base**: `mlx-community/Qwen3-1.7B-4bit`, QLoRA via `mlx_lm lora`, fully local on Apple
  Silicon (no cloud needed for SFT).
- **Fixed hyperparameters** (project rule: iterate on data, not knobs) — rank 16, scale 20,
  dropout 0.05, lr 1e-4, batch 4, max_seq_len 2048, grad checkpointing on, ~3–5 epochs sized to
  the dataset. See `configs/lora_v1.yaml`.
- **Version lineage** (v2→v5): each version changed labels/format/artifacts, never
  hyperparameters. v5 is the latest fully-evaluated checkpoint.
- **v6** (the "augment minorities" balanced set) just finished training: 687 iterations, train
  loss 0.087, val loss 0.365 (a mild late-run uptick from 0.252→0.340→0.365 over the last three
  checkpoints — flagged as a watch-item, not yet run through the eval harness).
- **Stretch-ladder next step — DPO**: targets *rewrite safety* specifically, the one metric that
  hasn't moved for any model tried so far (see below). Full local↔Colab round trip is built:
  mine pairs → render → fuse to dense fp16 → push to HF → `colab/train_dpo.ipynb` (trl DPO,
  reference-free) → merge → push back → `mlx_lm convert` → 3-way eval. Currently paused on the
  user's own HF Hub login/push, by design.

---

## 5. How we'll evaluate whether it worked

- **Built before training**, not after — a frozen gold set the model never sees during
  training, scored by `scripts/eval_harness.py`.
- **6-criterion tiered rubric** (0/1/2 each): verdict correctness, grounded reasoning, rewrite
  safety, schema compliance, calibration robustness, consistency — mirrors the assignment's own
  Appendix A (Spec adherence / Task quality / Robustness / Consistency). Deterministic criteria
  (verdict/schema/calibration/consistency) need no grader; reasoning/rewrite-safety are graded
  by a frontier LLM judge.
- **Mandatory comparison every run**: base (untrained) vs. tuned vs. frontier references
  (GPT-4o, Claude) on the identical frozen set, with bootstrap 95% CIs — never just "did loss go
  down."

Latest full comparison (n=299): `eval/results/report/final299/summary.md`

| | base | v2 | v3 | v4 | v5 | gpt4o | claude |
|---|---|---|---|---|---|---|---|
| Verdict accuracy | 27.4% | 37.1% | 43.1% | 50.5% | **52.5%** | 51.5% | 54.2% |
| Rewrite safety (0-2) | 1.08 | 0.91 | 0.89 | 0.98 | 1.01 | 1.09 | 0.93 |

**The finding that drives the next step**: verdict accuracy climbs cleanly with each data
iteration and v5 is now statistically tied with GPT-4o and within CI-overlap of Claude. But
rewrite safety is flat at ~0.9–1.1 out of 2 for *every single contestant, including both
frontier models* — this isn't a capability or volume gap, it's evidence the failure mode needs
a preference-learning signal (DPO), not more SFT data or a bigger base model.

---

## Brainlift

`docs/brainlift-socratic-tutor.md` — "Why LLM Tutors Give Away the Answer." Full DOK structure:
Purpose (scope in/out) → Spiky POVs → Experts → Insights → Knowledge Tree. The title itself is
the thesis: the rewrite-safety plateau above is the empirical confirmation of the doc's core
spiky POV.
