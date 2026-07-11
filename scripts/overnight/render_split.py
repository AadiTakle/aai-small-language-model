"""Render a structured set to MLX text-format train/valid for one split-task.

  --task verdict : rows need {problem, correct_solution, conversation_history, candidate_message,
                   verdict, reasoning}. Target = {"verdict","reasoning"} under VERDICT_SYSTEM.
  --task rewrite : rows need the above + a target rewrite (field 'target_rewrite' or
                   'rewritten_message') + verdict + a flag reason. Target = plain hint under
                   REWRITE_SYSTEM.

Eval is the held-out FROZEN set (verdict) / held-out contexts (rewrite), NOT a split of this data,
so we only emit train + valid (90/10).

Usage:
  python scripts/overnight/render_split.py --task verdict --src data/raw/verdict_balanced.jsonl \
      --out-dir data/mlx_verdict
  python scripts/overnight/render_split.py --task rewrite --src data/raw/rewrite_train.jsonl \
      --out-dir data/mlx_rewrite
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from overnight.split_common import input_dict, render_rewrite_text, render_verdict_text  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", required=True, choices=["verdict", "rewrite"])
    ap.add_argument("--src", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--valid", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    rows = read_jsonl(a.src)
    print(f"[render:{a.task}] {len(rows)} rows from {a.src}; loading tokenizer {config.MODEL} ...",
          file=sys.stderr)
    from mlx_lm import load
    _, tok = load(config.MODEL)

    lines, skipped = [], 0
    for r in rows:
        inp = input_dict(r)
        if a.task == "verdict":
            lines.append({"text": render_verdict_text(tok, inp, r)})
        else:
            hint = r.get("target_rewrite") or r.get("rewritten_message")
            if not (isinstance(hint, str) and hint.strip()):
                skipped += 1
                continue
            reason = r.get("reason") or r.get("reasoning") or ""
            lines.append({"text": render_rewrite_text(tok, inp, r.get("verdict", ""), reason, hint.strip())})

    rng = random.Random(a.seed)
    rng.shuffle(lines)
    nv = max(1, int(len(lines) * a.valid))
    valid_lines, train_lines = lines[:nv], lines[nv:]

    out = Path(a.out_dir)
    write_jsonl(out / "train.jsonl", train_lines)
    write_jsonl(out / "valid.jsonl", valid_lines)
    print(f"[render:{a.task}] wrote {len(train_lines)} train / {len(valid_lines)} valid -> {out}"
          + (f" (skipped {skipped} missing-target)" if skipped else ""), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
