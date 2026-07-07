#!/usr/bin/env python3
"""v1 real-dataset run: combine teacher shards -> build+gold -> QLoRA train -> full eval.

Consumes data/raw/v1_*.jsonl shards (produced by the teacher subagents), dedups by id,
gates + splits + renders to data/mlx, trains adapters/v1 with fixed hyperparameters
(iters computed for ~EPOCHS passes), then runs the full base-vs-tuned eval on BOTH the
held-out v1 gold and the stable hand-seeded seed gold.

Log-and-continue: a failed stage is reported; later stages still run where meaningful.
"""

from __future__ import annotations

import glob
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from socratic_tutor import config
from socratic_tutor.io_utils import read_jsonl, write_jsonl

PY = sys.executable
EPOCHS = 4
ADAPTER = config.ADAPTERS_DIR / "v1"
COMBINED = config.RAW_DIR / "v1.jsonl"
V1_GOLD = config.GOLD_DIR / "v1_test.jsonl"


def _run(cmd: list[str], desc: str) -> int:
    print(f"\n=== {desc} ===\n$ {' '.join(cmd)}", flush=True)
    rc = subprocess.run(cmd, cwd=str(ROOT)).returncode
    print(f"[{desc}] exit={rc}", flush=True)
    return rc


def _batch_size() -> int:
    try:
        import yaml
        cfg = yaml.safe_load((ROOT / "configs/lora_v1.yaml").read_text())
        return int(cfg.get("batch_size", 4))
    except Exception:
        return 4


def main() -> int:
    # 1) combine shards, dedup by id
    shards = sorted(glob.glob(str(config.RAW_DIR / "v1_*.jsonl")))
    if not shards:
        print("FATAL: no data/raw/v1_*.jsonl shards found.", file=sys.stderr)
        return 1
    seen, combined = set(), []
    for sh in shards:
        rows = read_jsonl(sh)
        for r in rows:
            rid = r.get("id")
            if rid in seen:
                continue
            seen.add(rid)
            combined.append(r)
        print(f"[combine] {sh}: {len(rows)} rows")
    write_jsonl(COMBINED, combined)
    print(f"[combine] {len(combined)} unique rows -> {COMBINED}")

    # 2) build + gold
    if _run([PY, "scripts/build_dataset.py", "--raw", str(COMBINED),
             "--out-dir", str(config.MLX_DIR), "--gold-out", str(V1_GOLD)], "build v1") != 0:
        print("FATAL: build failed.", file=sys.stderr)
        return 1

    n_train = len(read_jsonl(config.MLX_DIR / "train.jsonl"))
    batch = _batch_size()
    iters = max(100, EPOCHS * math.ceil(n_train / batch))
    print(f"[plan] n_train={n_train} batch={batch} epochs={EPOCHS} -> iters={iters}")

    # 3) train
    train_args = ["--train", "--model", config.MODEL, "--data", str(config.MLX_DIR),
                  "--adapter-path", str(ADAPTER), "-c", "configs/lora_v1.yaml",
                  "--iters", str(iters)]
    rc = _run([PY, "-m", "mlx_lm", "lora", *train_args], "train v1")
    if rc != 0:
        rc = _run([PY, "-m", "mlx_lm.lora", *train_args], "train v1 (fallback)")
    trained = (ADAPTER / "adapters.safetensors").exists()

    # 4) full eval on v1 gold AND the seed gold
    if trained:
        _run([PY, "scripts/eval_harness.py", "--test", str(V1_GOLD),
              "--adapter-path", str(ADAPTER), "--out", str(config.RESULTS_DIR / "v1_base_vs_tuned")],
             "eval (v1 gold)")
        _run([PY, "scripts/eval_harness.py", "--test", str(config.GOLD_DIR / "test.jsonl"),
              "--adapter-path", str(ADAPTER), "--out", str(config.RESULTS_DIR / "v1_on_seed_gold")],
             "eval (seed gold)")
    else:
        print("WARN: v1 adapter not found; running base-only eval on v1 gold.", file=sys.stderr)
        _run([PY, "scripts/eval_harness.py", "--test", str(V1_GOLD), "--tag", "base",
              "--out", str(config.RESULTS_DIR / "v1_base_only")], "eval (base only)")

    print(f"\n[v1] done. trained={trained}. n_examples={len(combined)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
