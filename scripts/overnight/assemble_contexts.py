"""Assemble REWRITE contexts (Task 2): flagged (non-adequate) tutor messages that need a good hint.

Robust core = in-repo curated + REAL tutoring data (MRBench + MathDial are HuggingFace datasets,
already ingested here). Best-effort augment = a slice of GSM8K (HF) for extra problem diversity;
those arrive without a flawed candidate, so they're tagged needs_synth=True and the teacher
synthesizes a realistic flawed candidate + verdict before writing the rewrite (in gen_rewrites).

Frozen-eval content is excluded. A capped, held-out eval slice (real contexts only) is reserved
for the rewrite eval — models generate rewrites on it at eval time; it never sees a target.

Usage:
  python scripts/overnight/assemble_contexts.py --eval-n 60 --gsm8k 80
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402

IN_REPO = ["data/raw/v9b.jsonl", "data/raw/real_mrbench.jsonl", "data/raw/real_mathdial.jsonl"]
ADEQUATE = "adequate"


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _context(row, source):
    return {
        "id": row.get("id"),
        "source": row.get("source") or source,
        "problem": row.get("problem", ""),
        "correct_solution": row.get("correct_solution", ""),
        "final_answer": row.get("final_answer", ""),
        "key_step": row.get("key_step", ""),
        "conversation_history": row.get("conversation_history") or [],
        "candidate_message": row.get("candidate_message", ""),
        "verdict": row.get("verdict"),
        "reason": row.get("reasoning", ""),
        "needs_synth": False,
    }


def _load_gsm8k(n, seed):
    """Best-effort HF pull: GSM8K problems (MIT). Returns needs_synth contexts, or [] on failure."""
    try:
        from datasets import load_dataset
        ds = load_dataset("gsm8k", "main", split="test")
        idx = list(range(len(ds)))
        random.Random(seed).shuffle(idx)
        out = []
        for i in idx[:n]:
            ex = ds[i]
            ans = ex["answer"]
            fa = ans.split("####")[-1].strip() if "####" in ans else ""
            out.append({
                "id": f"gsm8k-{i}", "source": "hf:gsm8k",
                "problem": ex["question"], "correct_solution": ans,
                "final_answer": fa, "key_step": "", "conversation_history": [],
                "candidate_message": "", "verdict": None, "reason": "", "needs_synth": True,
            })
        print(f"[contexts] HF GSM8K: added {len(out)} needs_synth contexts", file=sys.stderr)
        return out
    except Exception as e:  # noqa: BLE001
        print(f"[contexts] HF GSM8K augment SKIPPED ({type(e).__name__}: {str(e)[:120]})", file=sys.stderr)
        return []


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--holdout", default="eval/gold/frozen_eval.jsonl")
    ap.add_argument("--out-train", default="data/raw/rewrite_contexts_train.jsonl")
    ap.add_argument("--out-eval", default="data/raw/rewrite_contexts_eval.jsonl")
    ap.add_argument("--eval-n", type=int, default=60, help="capped held-out eval contexts (real only)")
    ap.add_argument("--gsm8k", type=int, default=80, help="best-effort HF GSM8K contexts (0 = skip)")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    frozen_txt = set()
    if os.path.exists(a.holdout):
        frozen_txt = {_norm(r.get("candidate_message")) for r in read_jsonl(a.holdout)}

    seen, core = set(), []
    for path in IN_REPO:
        if not os.path.exists(path):
            continue
        src = Path(path).stem
        for r in read_jsonl(path):
            if r.get("verdict") == ADEQUATE or not r.get("candidate_message"):
                continue  # rewrite task = non-adequate candidates only
            key = (_norm(r.get("candidate_message")), _norm(r.get("problem")))
            if key in seen or _norm(r.get("candidate_message")) in frozen_txt:
                continue
            seen.add(key)
            core.append(_context(r, src))

    rng = random.Random(a.seed)
    rng.shuffle(core)
    eval_n = min(a.eval_n, len(core) // 4)
    eval_ctx = core[:eval_n]
    train_ctx = core[eval_n:]

    gsm = _load_gsm8k(a.gsm8k, a.seed) if a.gsm8k else []
    train_ctx = train_ctx + gsm
    rng.shuffle(train_ctx)

    write_jsonl(a.out_train, train_ctx)
    write_jsonl(a.out_eval, eval_ctx)

    def dist(rows, key):
        return dict(sorted(Counter(r.get(key) for r in rows).items(), key=lambda x: -x[1]))

    print(f"[contexts] core flagged (in-repo, deduped, frozen-excluded): {len(core)}")
    print(f"[contexts] TRAIN={len(train_ctx)} (incl {len(gsm)} gsm8k needs_synth)  EVAL={len(eval_ctx)}")
    print(f"[contexts] train verdict dist: {dist(train_ctx, 'verdict')}")
    print(f"[contexts] train source dist:  {dist(train_ctx, 'source')}")
    print(f"[contexts] eval  verdict dist: {dist(eval_ctx, 'verdict')}")
    print(f"[contexts] -> {a.out_train} / {a.out_eval}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
