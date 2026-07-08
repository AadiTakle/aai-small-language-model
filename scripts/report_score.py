"""Score ONE contestant on a gold set, emitting per-item 0-2 tiers for the 5 rubric
criteria + consistency (for later bootstrap-CI aggregation in compile_report.py).

Contestants: base / v2 / v3 / v4 (Qwen via MLX, thinking-off) or gpt4o (OpenAI, our
judge task). Grounding + rewrite-safety graded by the gpt-4.1 judge (socratic_tutor.judge);
deterministic criteria (verdict/schema/calibration/consistency) need no grader.

Usage:
  python scripts/report_score.py --contestant v4  --test eval/gold/frozen_eval.jsonl --out eval/results/report/v4_items.json
  python scripts/report_score.py --contestant gpt4o --test eval/gold/frozen_eval.jsonl --out eval/results/report/gpt4o_items.json
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from socratic_tutor import config, judge  # noqa: E402
from socratic_tutor.io_utils import read_jsonl  # noqa: E402
from socratic_tutor.prompts import SYSTEM_PROMPT, build_user_prompt  # noqa: E402
from socratic_tutor.rubric import (  # noqa: E402
    calibration_tiers, consistency_tier, grounded_tier, safety_tier, schema_tier, verdict_tier,
)
from socratic_tutor.schema import parse_model_json  # noqa: E402

ADAPTERS = {"v2": "adapters/v2", "v3": "adapters/v3", "v4": "adapters/v4"}


def mlx_gen(adapter):
    from socratic_tutor.runner import Runner
    r = Runner(config.MODEL, adapter_path=adapter)
    return lambda inp, temp: r.generate(inp, temp=temp)


def openai_gen(model):
    from openai import OpenAI
    client = OpenAI()

    def gen(inp, temp):
        delays = [2, 5, 10, 20, 40, 60]
        waited = 0.0
        for i in range(len(delays) + 1):
            try:
                r = client.chat.completions.create(
                    model=model, temperature=temp,
                    messages=[{"role": "system", "content": SYSTEM_PROMPT},
                              {"role": "user", "content": build_user_prompt(inp)}])
                return r.choices[0].message.content or ""
            except Exception:
                if i >= len(delays) or waited >= 180:
                    return ""
                time.sleep(delays[i]); waited += delays[i]
    return gen


def _input(row):
    return {k: row.get(k) for k in ("problem", "correct_solution", "conversation_history", "candidate_message")}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contestant", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--consistency-k", type=int, default=3)
    ap.add_argument("--consistency-temp", type=float, default=0.7)
    ap.add_argument("--no-judge", action="store_true")
    a = ap.parse_args()

    c = a.contestant
    if c == "base":
        gen = mlx_gen(None)
    elif c in ADAPTERS:
        gen = mlx_gen(ADAPTERS[c])
    elif c == "gpt4o":
        gen = openai_gen(os.environ.get("REPORT_CONTESTANT_MODEL", "gpt-4o"))
    else:
        print(f"unknown contestant {c}", file=sys.stderr); return 2

    use_judge = (not a.no_judge) and judge.judge_available()
    gold = read_jsonl(a.test)
    per_item, adv = [], []
    n = len(gold)
    for idx, row in enumerate(gold, 1):
        raw = gen(_input(row), 0.0)
        out = parse_model_json(raw)
        pred = (out or {}).get("verdict")
        item = {
            "id": row.get("id"), "gold": row.get("gold_verdict"), "pred": pred,
            "verdict": verdict_tier(row.get("gold_verdict"), pred),
            "schema": schema_tier(raw, out),
            "grounded": grounded_tier(row, out, use_judge),
            "rewrite_safety": safety_tier(row, out, use_judge),
            "consistency": None,
        }
        if a.consistency_k > 0:
            verds = [(parse_model_json(gen(_input(row), a.consistency_temp)) or {}).get("verdict")
                     for _ in range(a.consistency_k)]
            item["consistency"] = consistency_tier(verds)
        per_item.append(item)
        if row.get("slice") == "calibration_adversarial":
            adv.append({"id": row.get("id"), "gold": row.get("gold_verdict"), "pred": pred})
        if idx % 10 == 0 or idx == n:
            print(f"[score:{c}] {idx}/{n}", file=sys.stderr, flush=True)

    payload = {
        "contestant": c, "n": n, "grader": ("gpt-4.1" if use_judge else "heuristic"),
        "consistency_k": a.consistency_k, "per_item": per_item,
        "calib_tiers": calibration_tiers(adv), "calib_n": len(adv),
    }
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"[score:{c}] wrote {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
