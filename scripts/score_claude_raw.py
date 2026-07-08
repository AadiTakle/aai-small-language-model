"""Score the Claude-contestant raw judgments (from the claude-judge-contestant workflow)
into the same per-item tier schema as the other contestants. Grounded/rewrite-safety are
graded by the gpt-4.1 judge (cross-family: Claude contestant graded by OpenAI → no self-bias).
Consistency is n/a for Claude (subagents aren't temperature-controlled here).

Usage: python scripts/score_claude_raw.py <workflow_output.json>
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from socratic_tutor import judge  # noqa: E402
from socratic_tutor.io_utils import read_jsonl  # noqa: E402
from socratic_tutor.rubric import (  # noqa: E402
    calibration_tiers, grounded_tier, safety_tier, schema_tier, verdict_tier,
)
from socratic_tutor.schema import parse_model_json  # noqa: E402


def main():
    wf_out = sys.argv[1]
    blob = json.load(open(wf_out))
    res = (blob.get("result", {}) or {}).get("results") or blob.get("results") or []
    raw_by_i = {r["i"]: r["raw"] for r in res if isinstance(r, dict) and "i" in r}
    print(f"[claude-score] loaded {len(raw_by_i)} raw judgments", file=sys.stderr)

    gold = read_jsonl("eval/gold/frozen_eval.jsonl")
    use_judge = judge.judge_available()
    per_item, adv = [], []
    for idx, row in enumerate(gold, 1):
        raw = raw_by_i.get(idx, "")
        out = parse_model_json(raw)
        pred = (out or {}).get("verdict")
        per_item.append({
            "id": row["id"], "gold": row.get("gold_verdict"), "pred": pred,
            "verdict": verdict_tier(row.get("gold_verdict"), pred),
            "schema": schema_tier(raw, out),
            "grounded": grounded_tier(row, out, use_judge),
            "rewrite_safety": safety_tier(row, out, use_judge),
            "consistency": None,
        })
        if row.get("slice") == "calibration_adversarial":
            adv.append({"id": row["id"], "gold": row.get("gold_verdict"), "pred": pred})
        if idx % 10 == 0 or idx == len(gold):
            print(f"[claude-score] {idx}/{len(gold)}", file=sys.stderr, flush=True)

    payload = {"contestant": "claude", "n": len(gold), "grader": ("gpt-4.1" if use_judge else "heuristic"),
               "consistency_k": 0, "per_item": per_item,
               "calib_tiers": calibration_tiers(adv), "calib_n": len(adv)}
    json.dump(payload, open("eval/results/report/claude_items.json", "w"), indent=2)
    matched = sum(1 for i in per_item if i["pred"] is not None)
    print(f"[claude-score] wrote claude_items.json ({matched}/{len(gold)} parseable)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
