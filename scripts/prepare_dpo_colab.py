#!/usr/bin/env python3
"""Prepare the local side of the DPO/Colab round trip.

Two independent steps:
  --render  build data/dpo/dpo_pairs_rendered.jsonl: trl.DPOTrainer-ready
            {id, source_detail, verdict, prompt, chosen, rejected} rows. For each mined
            pair, renders TWO full training texts (chosen vs rejected rewrite) via the
            exact same render_training_text() used for SFT, then splits on their longest
            common prefix -- prompt = shared prefix (ends inside the `"rewritten_message":`
            key-open), chosen/rejected = the diverging suffixes. Reuses existing
            chat-template/JSON-escaping code as-is; no new rendering logic.
  --fuse    shell out to `mlx_lm fuse` to merge adapters/v6 into the dense Qwen3-1.7B base,
            dequantize to fp16, and optionally push to a private HF Hub repo -- the
            artifact Colab loads to start DPO training.

Usage:
  python scripts/prepare_dpo_colab.py --render
  python scripts/prepare_dpo_colab.py --fuse
  python scripts/prepare_dpo_colab.py --fuse --hf-repo <user>/socratic-tutor-sft-v6-fp16
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.prompts import render_training_text  # noqa: E402
from gen_lib import assistant_json  # noqa: E402

PAIRS_IN = "data/dpo/bridge_mathdial_pairs.jsonl"
RENDERED_OUT = "data/dpo/dpo_pairs_rendered.jsonl"
# Dense repo, not the local mlx-community 4bit one -- this must match whatever tokenizer
# Colab loads for training (Colab loads Qwen/Qwen3-1.7B directly, per the DPO plan).
DENSE_TOKENIZER_REPO = "Qwen/Qwen3-1.7B"


def _input_dict(row: dict) -> dict:
    return {
        "problem": row["problem"],
        "correct_solution": row["correct_solution"],
        "conversation_history": row.get("conversation_history") or [],
        "candidate_message": row["candidate_message"],
    }


def _assert_tokenizer_parity(dense_tok) -> None:
    """Fail fast if the dense HF tokenizer's chat template diverges from the local MLX one.

    If these differ, rendering with the dense tokenizer would produce a token stream the
    SFT model was never actually trained on -- a real correctness bug, not a nicety.
    """
    from mlx_lm import load
    _, mlx_tok = load(config.MODEL)
    sample_inp = {
        "problem": "If x + 2 = 5, what is x?",
        "correct_solution": "x = 3",
        "conversation_history": ["Student: I think x = 4."],
        "candidate_message": "That's not quite right, try again.",
    }
    sample_json = assistant_json(
        {"verdict": "vague_unhelpful", "reasoning": "test", "rewritten_message": "test rewrite"}
    )
    mlx_text = render_training_text(mlx_tok, sample_inp, sample_json)
    dense_text = render_training_text(dense_tok, sample_inp, sample_json)
    if mlx_text != dense_text:
        i = next((i for i, (a, b) in enumerate(zip(mlx_text, dense_text)) if a != b),
                  min(len(mlx_text), len(dense_text)))
        print(
            f"[render] FATAL: {DENSE_TOKENIZER_REPO}'s chat template output differs from "
            f"{config.MODEL}'s at char {i}:\n"
            f"  mlx:   {mlx_text[max(0, i - 40):i + 40]!r}\n"
            f"  dense: {dense_text[max(0, i - 40):i + 40]!r}\n"
            "Rendering with the dense tokenizer would not match what the SFT model was "
            "trained on -- fix the template mismatch before proceeding.",
            file=sys.stderr,
        )
        sys.exit(1)
    print("[render] tokenizer sanity check OK: dense and MLX chat templates match exactly",
          file=sys.stderr)


def render(limit: int | None) -> int:
    from transformers import AutoTokenizer
    print(f"[render] loading tokenizer {DENSE_TOKENIZER_REPO} ...", file=sys.stderr)
    tokenizer = AutoTokenizer.from_pretrained(DENSE_TOKENIZER_REPO)
    _assert_tokenizer_parity(tokenizer)

    rows = read_jsonl(PAIRS_IN)
    if limit:
        rows = rows[:limit]

    out, skipped = [], Counter()
    for row in rows:
        inp = _input_dict(row)
        chosen_json = assistant_json({
            "verdict": row["verdict"], "reasoning": row["reasoning"],
            "rewritten_message": row["chosen_rewrite"],
        })
        rejected_json = assistant_json({
            "verdict": row["verdict"], "reasoning": row["reasoning"],
            "rewritten_message": row["rejected_rewrite"],
        })
        text_chosen = render_training_text(tokenizer, inp, chosen_json)
        text_rejected = render_training_text(tokenizer, inp, rejected_json)

        prompt = os.path.commonprefix([text_chosen, text_rejected])
        chosen = text_chosen[len(prompt):]
        rejected = text_rejected[len(prompt):]

        if '"rewritten_message"' not in prompt:
            skipped["prompt_split_too_early"] += 1
            continue
        if not chosen.strip() or not rejected.strip() or chosen == rejected:
            skipped["empty_or_identical_completion"] += 1
            continue

        out.append({
            "id": row["id"],
            "source_detail": row["source_detail"],
            "verdict": row["verdict"],
            "prompt": prompt,
            "chosen": chosen,
            "rejected": rejected,
        })

    write_jsonl(RENDERED_OUT, out)
    dist = Counter(r["source_detail"] for r in out)
    vdist = Counter(r["verdict"] for r in out)
    print(f"[render] {len(out)}/{len(rows)} pairs rendered -> {RENDERED_OUT}", file=sys.stderr)
    print(f"[render] by source: {dict(dist)}", file=sys.stderr)
    print(f"[render] by verdict: {dict(vdist)}", file=sys.stderr)
    if skipped:
        print(f"[render] skipped: {dict(skipped)}", file=sys.stderr)
    return 0


def fuse(hf_repo: str | None) -> int:
    adapter_path = str(config.ADAPTERS_DIR / "v6")
    save_path = "data/dpo/fused_v6_fp16"
    cmd = [
        sys.executable, "-m", "mlx_lm", "fuse",
        "--model", config.MODEL,
        "--adapter-path", adapter_path,
        "--save-path", save_path,
        "--dequantize",
    ]
    if hf_repo:
        cmd += ["--upload-repo", hf_repo]
    print(f"[fuse] running: {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"[fuse] mlx_lm fuse failed with exit code {result.returncode}", file=sys.stderr)
        return result.returncode
    suffix = f", pushed to {hf_repo}" if hf_repo else " (local only -- no --hf-repo given)"
    print(f"[fuse] wrote {save_path}{suffix}", file=sys.stderr)
    return 0


def push_fused(hf_repo: str) -> int:
    """Upload an already-fused local checkpoint without redoing the fuse/dequantize."""
    from huggingface_hub import HfApi
    save_path = "data/dpo/fused_v6_fp16"
    api = HfApi()
    print(f"[push] creating (if needed) private repo {hf_repo} ...", file=sys.stderr)
    api.create_repo(hf_repo, private=True, exist_ok=True)
    print(f"[push] uploading {save_path} -> {hf_repo} ...", file=sys.stderr)
    api.upload_folder(folder_path=save_path, repo_id=hf_repo)
    print(f"[push] done: https://huggingface.co/{hf_repo}", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--render", action="store_true",
                     help="Render DPO pairs to prompt/chosen/rejected.")
    ap.add_argument("--fuse", action="store_true",
                     help="Fuse+dequantize adapters/v6 into a dense fp16 checkpoint.")
    ap.add_argument("--push-fused", action="store_true",
                     help="Upload the already-fused local checkpoint (skips redoing the fuse).")
    ap.add_argument("--hf-repo", default=None,
                     help="Target HF Hub repo id, e.g. <username>/socratic-tutor-sft-v6-fp16. "
                          "Required for --push-fused; optional for --fuse (upload inline).")
    ap.add_argument("--limit", type=int, default=None, help="--render: only process N rows.")
    a = ap.parse_args()
    if a.render:
        return render(a.limit)
    if a.fuse:
        return fuse(a.hf_repo)
    if a.push_fused:
        if not a.hf_repo:
            ap.error("--push-fused requires --hf-repo")
        return push_fused(a.hf_repo)
    ap.error("pass --render, --fuse, or --push-fused")


if __name__ == "__main__":
    raise SystemExit(main())
