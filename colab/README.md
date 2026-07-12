# Colab: Qwen3-4B judge — the scale-thesis run

Trains a **bigger (4B) version of our judge** on the *identical* recipe + data as our 1.7B `v9`
(90.4% leak-recall), so we can test: **does scale beat the tuned small model on the constrained
safety behavior?** Also runs clean GSM8K/MMLU on 4B-base / 4B-tuned / 1.7B-base (A100 → no Metal OOM,
full sample) to backfill the dev-log's traditional benchmarks.

## Steps (~1.5–2h on A100, well within 90 units)

1. **Runtime → Change runtime type → A100 GPU.**
2. **Upload** `data/colab_4b/train.jsonl` and `data/colab_4b/valid.jsonl` to `/content/` (Files pane).
3. **HF token:** click the 🔑 (Secrets) in the sidebar, add `HF_TOKEN` (a write token). Or you'll be prompted.
4. **Edit** the `HF_REPO` line in `train_4b_judge.py` to `<your-hf-username>/socratic-judge-4b`.
5. Upload `colab/train_4b_judge.py`, then in a cell: `!python train_4b_judge.py`
   (or paste the file into one cell and run).

## What comes back

- A merged 4B judge pushed to `HF_REPO`. **Send me the repo name** — I convert it to MLX and eval on
  our frozen set (leak-recall/safety/5-way) vs the 1.7B `v9`.
- `/content/bench/*` — GSM8K + MMLU for 4B-base, 4B-tuned, 1.7B-base (paste the printed numbers to me).

If a cell errors (trl/peft API drift is the usual culprit), paste the traceback — I'll patch the script
immediately. The one likely swap: older `trl` wants `max_seq_length=`/`tokenizer=` instead of
`max_length=`/`processing_class=` (noted inline).
