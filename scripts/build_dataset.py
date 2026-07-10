#!/usr/bin/env python3
"""Convert raw teacher tuples -> MLX text-format JSONL (train/valid/test).

Primary format is TEXT-pre-rendered: each MLX line is
    {"text": render_training_text(system, user, assistant_json, enable_thinking=False)}
so the training and inference token streams match exactly and no <think> block
can leak on either side (chat-format auto-templating cannot force enable_thinking=False).

Optionally also emits the held-out test split in the eval-harness GOLD format.

Usage:
    python scripts/build_dataset.py --raw data/raw/smoke.jsonl --out-dir data/mlx
    python scripts/build_dataset.py --raw data/raw/v1.jsonl --out-dir data/mlx \
        --gold-out eval/gold/v1_test.jsonl
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from socratic_tutor import config
from socratic_tutor.io_utils import read_jsonl, split_rows, write_jsonl
from socratic_tutor.prompts import SYSTEM_PROMPT, build_user_prompt, render_training_text
from gen_lib import assistant_json, passes_quality_gate


def _input_dict(row: dict) -> dict:
    return {
        "problem": row["problem"],
        "correct_solution": row["correct_solution"],
        "conversation_history": row.get("conversation_history") or [],
        "candidate_message": row["candidate_message"],
    }


def _gold_row(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "problem": row["problem"],
        "correct_solution": row["correct_solution"],
        "final_answer": row.get("final_answer", ""),
        "key_step": row.get("key_step", ""),
        "conversation_history": row.get("conversation_history") or [],
        "candidate_message": row["candidate_message"],
        "gold_verdict": row["verdict"],
        "gold_reasoning": row.get("reasoning", ""),
        "gold_rewrite": row.get("rewritten_message"),
        "slice": row.get("slice", "core"),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw", required=True)
    p.add_argument("--out-dir", default=str(config.MLX_DIR))
    p.add_argument("--gold-out", default=None,
                   help="Also write the test split in eval-harness gold format here.")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--train", type=float, default=0.8)
    p.add_argument("--valid", type=float, default=0.1)
    p.add_argument("--no-gate", action="store_true", help="Skip the quality gate.")
    p.add_argument("--traces", default=None,
                   help="v8 thinking: JSON {id: trace} or jsonl {id,trace}. Wraps each assistant "
                        "target as <think>trace</think> + json for thinking-mode SFT (needs "
                        "config.ENABLE_THINKING=True). Rows without a trace fall back to their reasoning.")
    p.add_argument("--format", choices=["text", "chat"], default="text",
                   help="text = {'text': full render} (no prompt masking, default/legacy). "
                        "chat = {'messages':[system,user,assistant]} for mlx_lm ChatDataset + "
                        "mask_prompt:true (loss on the assistant JSON only). Renders token-identical; "
                        "only the loss mask differs.")
    args = p.parse_args()

    raw = read_jsonl(args.raw)
    kept, skipped = [], []
    for row in raw:
        if args.no_gate:
            kept.append(row)
            continue
        ok, errs = passes_quality_gate(row)
        (kept if ok else skipped).append((row, errs) if not ok else row)
    if skipped:
        print(f"[build] skipped {len(skipped)}/{len(raw)} rows failing the quality gate:",
              file=sys.stderr)
        for row, errs in skipped[:10]:
            print(f"    - {row.get('id')}: {errs}", file=sys.stderr)
    if not kept:
        print("ERROR: no rows passed the gate", file=sys.stderr)
        return 2

    rng = random.Random(args.seed)
    rng.shuffle(kept)
    train_rows, valid_rows, test_rows = split_rows(kept, args.train, args.valid)

    if args.format == "chat":
        # {"messages":[system,user,assistant]} — mlx_lm ChatDataset applies the chat
        # template at load; pair with `mask_prompt: true` in the lora config so loss falls
        # on the assistant JSON only. No tokenizer needed here.
        def to_lines(rows):
            return [{"messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(_input_dict(r))},
                {"role": "assistant", "content": assistant_json(r)},
            ]} for r in rows]
        print("[build] format=chat (messages) — pair with mask_prompt:true for prompt masking",
              file=sys.stderr)
    else:
        print(f"[build] format=text — loading tokenizer from {config.MODEL} for rendering ...",
              file=sys.stderr)
        from mlx_lm import load
        _, tokenizer = load(config.MODEL)

        traces = None
        if args.traces:
            import json as _json
            traces = (_json.load(open(args.traces)) if args.traces.endswith(".json")
                      else {r["id"]: r.get("trace", "") for r in read_jsonl(args.traces)})
            n_tr = sum(1 for t in traces.values() if (t or "").strip())
            print(f"[build] loaded {n_tr} think-traces from {args.traces} (thinking-mode SFT)",
                  file=sys.stderr)

        def _assistant(r):
            aj = assistant_json(r)
            if traces is not None:
                tr = (traces.get(r["id"]) or r.get("reasoning") or "").strip()
                if tr:
                    return f"<think>\n{tr}\n</think>\n\n{aj}"
            return aj

        def to_lines(rows):
            return [{"text": render_training_text(tokenizer, _input_dict(r), _assistant(r))}
                    for r in rows]

    out_dir = Path(args.out_dir)
    write_jsonl(out_dir / "train.jsonl", to_lines(train_rows))
    write_jsonl(out_dir / "valid.jsonl", to_lines(valid_rows))
    write_jsonl(out_dir / "test.jsonl", to_lines(test_rows))
    print(f"[build] wrote {len(train_rows)} train / {len(valid_rows)} valid / "
          f"{len(test_rows)} test -> {out_dir}", file=sys.stderr)

    if args.gold_out:
        write_jsonl(args.gold_out, [_gold_row(r) for r in test_rows])
        print(f"[build] wrote {len(test_rows)} gold rows -> {args.gold_out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
