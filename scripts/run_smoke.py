#!/usr/bin/env python3
"""50-junk end-to-end smoke: generate -> build -> train (QLoRA) -> eval base-vs-tuned.

Success criterion (per the Day 2 plan): the full loop RUNS end to end and produces a
numbers table. It does NOT need tuned>base — the data is deliberate junk; this only
proves the plumbing (data format, MLX LoRA training, adapter loading, eval).

Runs unattended: each stage logs and, where a later stage can still add value, continues
(e.g. if training fails, it still reports the base-model eval).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from socratic_tutor import config
from socratic_tutor.io_utils import write_jsonl
from gen_lib import make_junk_examples

PY = sys.executable
RAW = config.RAW_DIR / "smoke.jsonl"
ADAPTER = config.ADAPTERS_DIR / "smoke"
RESULTS = config.RESULTS_DIR / "smoke_base_vs_tuned"


def _run(cmd: list[str], desc: str) -> int:
    print(f"\n=== {desc} ===\n$ {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT))
    print(f"[{desc}] exit={proc.returncode}", flush=True)
    return proc.returncode


def _train_cmd(base: list[str]) -> int:
    """mlx_lm lora, tolerant of the two module-invocation spellings."""
    rc = _run([PY, "-m", "mlx_lm", "lora", *base], "train (mlx_lm lora)")
    if rc != 0:
        rc = _run([PY, "-m", "mlx_lm.lora", *base], "train (mlx_lm.lora fallback)")
    return rc


def main() -> int:
    # 1) generate 50 junk examples
    rows = make_junk_examples(50)
    write_jsonl(RAW, rows)
    print(f"[gen] wrote {len(rows)} junk examples -> {RAW}")

    # 2) build MLX dataset
    if _run([PY, "scripts/build_dataset.py", "--raw", str(RAW), "--out-dir", str(config.MLX_DIR)],
            "build dataset") != 0:
        print("FATAL: build failed; cannot train.", file=sys.stderr)
        return 1

    # 3) train QLoRA adapter
    train_args = [
        "--train", "--model", config.MODEL,
        "--data", str(config.MLX_DIR), "--adapter-path", str(ADAPTER),
        "-c", "configs/lora_smoke.yaml",
    ]
    trained = _train_cmd(train_args) == 0 and (ADAPTER / "adapters.safetensors").exists()

    # 4) eval — base vs tuned if the adapter trained, else base-only
    eval_args = [PY, "scripts/eval_harness.py", "--test", str(config.GOLD_DIR / "test.jsonl"),
                 "--out", str(RESULTS)]
    if trained:
        eval_args += ["--adapter-path", str(ADAPTER)]
    else:
        print("WARN: adapter not found; running BASE-ONLY eval.", file=sys.stderr)
        eval_args += ["--tag", "base"]
    rc = _run(eval_args, "eval")

    print(f"\n[smoke] done. trained={trained}. results -> {RESULTS}.md/.json")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
