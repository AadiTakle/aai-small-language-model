"""Central config: model id, paths, generation defaults."""

from pathlib import Path

# Base model (Qwen3 dense instruct, 4-bit MLX). Swappable to 0.6B / 4B later.
MODEL = "mlx-community/Qwen3-1.7B-4bit"

# Qwen3 defaults to a <think> reasoning trace. For a strict-JSON judge/rewriter we
# want clean single-object output, so thinking is disabled at both train-render and
# inference. Revisit only if verdict accuracy is poor (see plan).
ENABLE_THINKING = False

# Output token budget for a judge+rewrite response (verdict + reasoning + rewrite).
MAX_TOKENS = 512

# --- paths (repo-relative) ---
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
MLX_DIR = DATA_DIR / "mlx"
EVAL_DIR = ROOT / "eval"
GOLD_DIR = EVAL_DIR / "gold"
RESULTS_DIR = EVAL_DIR / "results"
ADAPTERS_DIR = ROOT / "adapters"
