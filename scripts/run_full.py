#!/usr/bin/env python3
"""Full-dataset run: combine v1 + expansion shards -> build+gold -> train adapters/v2 -> eval.

Globs BOTH data/raw/v1_*.jsonl and data/raw/exp_*.jsonl, dedups by id, gates + splits +
renders, trains adapters/v2 (iters computed for ~EPOCHS passes), then evaluates base vs
tuned on the held-out full gold AND the stable hand-seeded seed gold. Lets us see whether
the larger dataset improves on the v1 numbers.

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
EPOCHS = 3
ADAPTER = config.ADAPTERS_DIR / "v2"
COMBINED = config.RAW_DIR / "all.jsonl"
FULL_GOLD = config.GOLD_DIR / "all_test.jsonl"


def _run(cmd: list[str], desc: str) -> int:
    print(f"\n=== {desc} ===\n$ {' '.join(cmd)}", flush=True)
    rc = subprocess.run(cmd, cwd=str(ROOT)).returncode
    print(f"[{desc}] exit={rc}", flush=True)
    return rc


def _batch_size() -> int:
    try:
        import yaml
        return int(yaml.safe_load((ROOT / "configs/lora_v1.yaml").read_text()).get("batch_size", 4))
    except Exception:
        return 4


def main() -> int:
    shards = sorted(glob.glob(str(config.RAW_DIR / "v1_*.jsonl")) +
                    glob.glob(str(config.RAW_DIR / "exp_*.jsonl")))
    if not shards:
        print("FATAL: no v1_*/exp_* shards found.", file=sys.stderr)
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
        print(f"[combine] {Path(sh).name}: {len(rows)} rows")
    write_jsonl(COMBINED, combined)
    print(f"[combine] {len(combined)} unique rows -> {COMBINED}")

    if _run([PY, "scripts/build_dataset.py", "--raw", str(COMBINED),
             "--out-dir", str(config.MLX_DIR), "--gold-out", str(FULL_GOLD)], "build full") != 0:
        return 1

    n_train = len(read_jsonl(config.MLX_DIR / "train.jsonl"))
    batch = _batch_size()
    iters = max(150, EPOCHS * math.ceil(n_train / batch))
    print(f"[plan] n_train={n_train} batch={batch} epochs={EPOCHS} -> iters={iters}")

    train_args = ["--train", "--model", config.MODEL, "--data", str(config.MLX_DIR),
                  "--adapter-path", str(ADAPTER), "-c", "configs/lora_v1.yaml", "--iters", str(iters)]
    rc = _run([PY, "-m", "mlx_lm", "lora", *train_args], "train v2")
    if rc != 0:
        _run([PY, "-m", "mlx_lm.lora", *train_args], "train v2 (fallback)")
    trained = (ADAPTER / "adapters.safetensors").exists()

    if trained:
        _run([PY, "scripts/eval_harness.py", "--test", str(FULL_GOLD), "--adapter-path", str(ADAPTER),
              "--out", str(config.RESULTS_DIR / "v2_base_vs_tuned")], "eval (full gold)")
        _run([PY, "scripts/eval_harness.py", "--test", str(config.GOLD_DIR / "test.jsonl"),
              "--adapter-path", str(ADAPTER), "--out", str(config.RESULTS_DIR / "v2_on_seed_gold")],
             "eval (seed gold)")
    else:
        print("WARN: v2 adapter missing; base-only eval on full gold.", file=sys.stderr)
        _run([PY, "scripts/eval_harness.py", "--test", str(FULL_GOLD), "--tag", "base",
              "--out", str(config.RESULTS_DIR / "v2_base_only")], "eval (base only)")

    print(f"\n[full] done. trained={trained}. n_examples={len(combined)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
