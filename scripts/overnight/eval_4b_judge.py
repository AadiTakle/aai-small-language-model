"""Eval a converted MLX Qwen3-4B judge on the frozen set — the scale-thesis comparison.

Reports leak-recall / safety-binary / leak-F1 / 5-way accuracy, directly comparable to our 1.7B `v9`
(64.1 5-way / 77.5 safety / 90.4 recall / 73.7 F1). Run AFTER Colab pushes the merged 4B and you
convert it to MLX:
  python -m mlx_lm convert --hf-path <hf-user>/socratic-judge-4b --mlx-path data/scale_4b/mlx_4b -q
  python scripts/overnight/eval_4b_judge.py --model data/scale_4b/mlx_4b
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from socratic_tutor.io_utils import read_jsonl  # noqa: E402
from socratic_tutor.schema import parse_model_json  # noqa: E402
from overnight.split_common import LEAK, infer_verdict_prompt, input_dict  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True, help="converted MLX 4B path (merged, no adapter)")
    ap.add_argument("--frozen", default="eval/gold/frozen_eval.jsonl")
    ap.add_argument("--label", default="qwen3-4b-judge")
    ap.add_argument("--out", default="eval/results/overnight/eval_4b_judge")
    a = ap.parse_args()

    from mlx_lm import generate, load
    from mlx_lm.sample_utils import make_sampler

    model, tok = load(a.model)
    sampler = make_sampler(temp=0.0)
    frozen = read_jsonl(a.frozen)
    print(f"[eval-4b] {a.label} on {len(frozen)} frozen rows ...", file=sys.stderr, flush=True)

    tp = fp = tn = fn = correct5 = 0
    for r in frozen:
        prompt = infer_verdict_prompt(tok, input_dict(r))
        raw = generate(model, tok, prompt=prompt, max_tokens=128, sampler=sampler, verbose=False)
        pred = (parse_model_json(raw) or {}).get("verdict", "")
        gold = r.get("gold_verdict") or r.get("verdict")
        correct5 += pred == gold
        gl, pl = gold in LEAK, pred in LEAK
        tp += gl and pl
        fp += (not gl) and pl
        tn += (not gl) and (not pl)
        fn += gl and (not pl)

    n = len(frozen)
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = 2 * prec * recall / (prec + recall) if (prec + recall) else 0.0
    safety = (tp + tn) / max(1, n)
    acc5 = correct5 / max(1, n)
    stats = {"label": a.label, "n": n, "acc5": round(acc5, 3), "safety_binary": round(safety, 3),
             "leak_recall": round(recall, 3), "leak_precision": round(prec, 3), "leak_f1": round(f1, 3)}

    md = ("# Scale-thesis: Qwen3-4B judge vs 1.7B v9 (frozen)\n\n"
          "| model | 5-way | safety-bin | leak R | leak P | leak F1 |\n|---|---|---|---|---|---|\n"
          f"| 1.7B v9 (ship) | 64.1 | 77.5 | 90.4 | 62.3 | 73.7 |\n"
          f"| {a.label} | {acc5:.1%} | {safety:.1%} | {recall:.1%} | {prec:.1%} | {f1:.1%} |\n")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out + ".md").write_text(md, encoding="utf-8")
    Path(a.out + ".json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(md)
    print(f"[eval-4b] wrote {a.out}.md/.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
