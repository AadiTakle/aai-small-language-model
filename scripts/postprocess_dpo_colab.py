#!/usr/bin/env python3
"""Postprocess the Colab DPO output: convert back to MLX, run a 3-way eval.

Two independent steps:
  --convert   shell out to `mlx_lm convert` to turn the pushed HF Hub DPO checkpoint
              (dense fp16, from colab/train_dpo.ipynb's final push_to_hub) into a
              standalone quantized MLX model directory -- the well-trodden HF->MLX
              direction, lowest-risk step in the whole DPO plan.
  --eval3     run base / SFT-only (adapters/v6) / SFT+DPO (the converted merged model)
              through scripts/eval_harness.py's own evaluate()/mlx_runner()/
              comparison_markdown() -- reuses that scoring logic as-is (no
              eval_harness.py changes), just assembled into a 3-tag table instead of
              the 2-tag base-vs-tuned table its own main() produces.

Usage:
  python scripts/postprocess_dpo_colab.py --convert --hf-repo <user>/socratic-tutor-dpo-v1-fp16
  python scripts/postprocess_dpo_colab.py --eval3
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl  # noqa: E402
import eval_harness  # noqa: E402

MLX_PATH = "data/dpo/mlx_dpo_v1_4bit"
OUT_PREFIX = str(config.RESULTS_DIR / "dpo_v1_3way")


def convert(hf_repo: str) -> int:
    cmd = [
        sys.executable, "-m", "mlx_lm", "convert",
        "--hf-path", hf_repo,
        "-q", "--dtype", "float16",
        "--mlx-path", MLX_PATH,
    ]
    print(f"[convert] running: {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"[convert] mlx_lm convert failed with exit code {result.returncode}", file=sys.stderr)
        return result.returncode
    print(f"[convert] wrote {MLX_PATH}", file=sys.stderr)
    return 0


def eval3(gold_file: str | None = None, include_base: bool = True) -> int:
    gold_path = Path(gold_file) if gold_file else (config.GOLD_DIR / "test.jsonl")
    gold = read_jsonl(str(gold_path))
    if not gold:
        print(f"[eval3] ERROR: no gold rows in {gold_path}", file=sys.stderr)
        return 2

    results = {}
    if include_base:
        print(f"[eval3] base ({config.MODEL}) ...", file=sys.stderr)
        results["base"] = eval_harness.evaluate(
            gold, eval_harness.mlx_runner(config.MODEL, None, config.MAX_TOKENS))

    sft_adapter = str(config.ADAPTERS_DIR / "v6")
    print(f"[eval3] sft_v6 ({config.MODEL} + {sft_adapter}) ...", file=sys.stderr)
    results["sft_v6"] = eval_harness.evaluate(
        gold, eval_harness.mlx_runner(config.MODEL, sft_adapter, config.MAX_TOKENS))

    print(f"[eval3] dpo_v1 ({MLX_PATH}) ...", file=sys.stderr)
    results["dpo_v1"] = eval_harness.evaluate(
        gold, eval_harness.mlx_runner(MLX_PATH, None, config.MAX_TOKENS))

    md = eval_harness.comparison_markdown(results)
    suffix = f"_{gold_path.stem}" if gold_file else ""
    out_prefix = Path(OUT_PREFIX + suffix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    out_prefix.with_suffix(".md").write_text(md, encoding="utf-8")
    out_prefix.with_suffix(".json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    print(md)
    print(f"[eval3] wrote {out_prefix.with_suffix('.md')} and {out_prefix.with_suffix('.json')}",
          file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--convert", action="store_true",
                     help="Convert the pushed HF DPO checkpoint back to quantized MLX.")
    ap.add_argument("--hf-repo", default=None,
                     help="Source HF Hub repo id for --convert, e.g. "
                          "<user>/socratic-tutor-dpo-v1-fp16.")
    ap.add_argument("--eval3", action="store_true",
                     help="Run base / sft_v6 / dpo_v1 through eval_harness, emit a 3-way table.")
    ap.add_argument("--gold", default=None,
                     help="Gold jsonl for --eval3 (default: eval/gold/test.jsonl). "
                          "Pass eval/gold/frozen_eval.jsonl for the full frozen-set comparison.")
    ap.add_argument("--no-base", action="store_true",
                     help="Skip the slow base model; eval sft_v6 + dpo_v1 only.")
    a = ap.parse_args()
    if a.convert:
        if not a.hf_repo:
            ap.error("--convert requires --hf-repo")
        return convert(a.hf_repo)
    if a.eval3:
        return eval3(a.gold, include_base=not a.no_base)
    ap.error("pass --convert or --eval3")


if __name__ == "__main__":
    raise SystemExit(main())
