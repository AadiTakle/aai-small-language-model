#!/usr/bin/env python3
"""Eval v8 (thinking) on the frozen set; table it vs stored sft_v6 (+ v7) on the same scorer.

v8 uses the SAME prompt, labels, and training config as v6 — thinking is the ONLY change (targets
carry a <think> reasoning trace; inference runs with enable_thinking=True and max_tokens=1024 so
the think block + JSON both fit). So v8 vs sft_v6 isolates the thinking lever cleanly.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl  # noqa: E402
import eval_harness  # noqa: E402

FROZEN = str(config.GOLD_DIR / "frozen_eval.jsonl")
PRIOR = str(config.RESULTS_DIR / "v7_frozen.json")  # has stored sft_v6, dpo_v1, v7 (prior prompt/no-think)
OUT = str(config.RESULTS_DIR / "v8_frozen")
MAX_TOKENS = 1024  # thinking needs room for the <think> trace + the JSON


def main() -> int:
    gold = read_jsonl(FROZEN)
    if not gold:
        print(f"[v8-eval] ERROR: no gold rows in {FROZEN}", file=sys.stderr)
        return 2
    adapter = str(config.ADAPTERS_DIR / "v8")
    print(f"[v8-eval] {len(gold)} rows; running v8 ({config.MODEL} + {adapter}) thinking, "
          f"max_tokens={MAX_TOKENS} ...", file=sys.stderr)
    v8 = eval_harness.evaluate(gold, eval_harness.mlx_runner(config.MODEL, adapter, MAX_TOKENS))

    prior = json.load(open(PRIOR)) if os.path.exists(PRIOR) else {}
    results = {}
    for tag in ("sft_v6", "v7"):  # baseline + the prior attempt, for context
        if tag in prior:
            results[tag] = prior[tag]
    results["v8"] = v8

    md = eval_harness.comparison_markdown(results)
    Path(OUT + ".md").write_text(md, encoding="utf-8")
    Path(OUT + ".json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(md)
    print(f"[v8-eval] wrote {OUT}.md / {OUT}.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
