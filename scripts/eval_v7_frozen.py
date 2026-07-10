#!/usr/bin/env python3
"""Eval v7 (decision-tree relabel) on the frozen set; table it against the stored
sft_v6 / dpo_v1 numbers using the SAME deterministic + heuristic scorer.

FAIRNESS NOTE: v7 is scored with the CURRENT SYSTEM_PROMPT (the decision-tree prompt it
was trained on). The stored sft_v6 / dpo_v1 numbers were computed with the PRIOR prompt
(their training prompt). So every model is scored with the prompt it was trained on --
fair per-model -- but the prompt text differs across columns; read the v7 delta with that
in mind (it bundles the relabel AND the prompt change; attribution is a follow-up).
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
PRIOR = str(config.RESULTS_DIR / "dpo_v1_3way_frozen_eval.json")
OUT = str(config.RESULTS_DIR / "v7_frozen")


def main() -> int:
    gold = read_jsonl(FROZEN)
    if not gold:
        print(f"[v7-eval] ERROR: no gold rows in {FROZEN}", file=sys.stderr)
        return 2
    adapter = str(config.ADAPTERS_DIR / "v7")
    print(f"[v7-eval] {len(gold)} frozen rows; running v7 ({config.MODEL} + {adapter}) ...", file=sys.stderr)
    v7 = eval_harness.evaluate(gold, eval_harness.mlx_runner(config.MODEL, adapter, config.MAX_TOKENS))

    prior = json.load(open(PRIOR)) if os.path.exists(PRIOR) else {}
    results = {}
    for tag in ("sft_v6", "dpo_v1"):  # stored, prior-prompt columns for context
        if tag in prior:
            results[tag] = prior[tag]
    results["v7"] = v7

    md = eval_harness.comparison_markdown(results)
    Path(OUT + ".md").write_text(md, encoding="utf-8")
    Path(OUT + ".json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(md)
    print(f"[v7-eval] wrote {OUT}.md / {OUT}.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
