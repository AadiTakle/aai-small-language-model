#!/usr/bin/env python3
"""Probe: does enabling Qwen3 <think> reasoning improve VERDICT accuracy?

Same model, same (decision-tree) SYSTEM_PROMPT, thinking ON vs OFF, on a frozen-set slice —
isolates the reasoning effect. Default runs on BASE (no fine-tune confound: our adapters were
all trained thinking-off, so inference-time thinking on them is off-distribution; base was
never trained either way). Reports overall verdict accuracy, schema rate, and accuracy AMONG
parseable outputs (controls for base's JSON-formatting noise).

Usage:
  python scripts/probe_thinking.py --limit 150            # base
  python scripts/probe_thinking.py --adapter adapters/v6  # (confounded) tuned probe
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl  # noqa: E402
from socratic_tutor.prompts import SYSTEM_PROMPT, build_user_prompt  # noqa: E402
from socratic_tutor.schema import VERDICTS, parse_model_json  # noqa: E402

THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def _input(row):
    return {k: row.get(k) for k in ("problem", "correct_solution", "conversation_history", "candidate_message")}


def _render(tok, inp, thinking):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(inp)}]
    try:
        return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True,
                                       enable_thinking=thinking)
    except TypeError:
        return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adapter", default=None, help="None = base model")
    ap.add_argument("--limit", type=int, default=150)
    a = ap.parse_args()

    from mlx_lm import generate, load
    from mlx_lm.sample_utils import make_sampler

    gold = read_jsonl(str(config.GOLD_DIR / "frozen_eval.jsonl"))[:a.limit]
    model, tok = load(config.MODEL, adapter_path=a.adapter)
    sampler = make_sampler(temp=0.0)

    def one(row, thinking, mt):
        prompt = _render(tok, _input(row), thinking)
        raw = generate(model, tok, prompt=prompt, max_tokens=mt, sampler=sampler, verbose=False)
        return (parse_model_json(THINK_RE.sub("", raw)) or {}).get("verdict")

    def evalpass(thinking, mt, label):
        corr = parse_ok = 0
        for i, row in enumerate(gold, 1):
            pred = one(row, thinking, mt)
            if pred in VERDICTS:
                parse_ok += 1
            if pred == row.get("gold_verdict"):
                corr += 1
            if i % 25 == 0 or i == len(gold):
                print(f"  [{label}] {i}/{len(gold)}", file=sys.stderr, flush=True)
        n = len(gold)
        return {"acc": corr / n, "schema": parse_ok / n,
                "acc_parseable": (corr / parse_ok if parse_ok else 0.0)}

    off = evalpass(False, 512, "nothink")
    on = evalpass(True, 1024, "think")

    print(f"\n[probe] model={config.MODEL}  adapter={a.adapter}  n={len(gold)}")
    print(f"[probe] {'':14} | verdict acc | schema | acc(parseable)")
    print(f"[probe] thinking OFF   | {off['acc']:.1%}       | {off['schema']:.1%}  | {off['acc_parseable']:.1%}")
    print(f"[probe] thinking ON    | {on['acc']:.1%}       | {on['schema']:.1%}  | {on['acc_parseable']:.1%}")
    print(f"[probe] delta (on-off) | {on['acc']-off['acc']:+.1%}       | "
          f"{on['schema']-off['schema']:+.1%}  | {on['acc_parseable']-off['acc_parseable']:+.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
