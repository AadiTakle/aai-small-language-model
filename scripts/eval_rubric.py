"""Tiered (0-2) rubric eval: scores base vs tuned on the 5 behavior-spec criteria
+ consistency, with an independent OpenAI judge on the two judgment criteria, and
rolls the result up into the Appendix A 4-dimension table.

Usage (export OPENAI_API_KEY first to enable the judge; falls back to heuristic if unset):
    python scripts/eval_rubric.py --test eval/gold/all_test.jsonl --adapter-path adapters/v2 \
        --out eval/results/v2_rubric --consistency-k 3
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from socratic_tutor import config, judge  # noqa: E402
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.rubric import (  # noqa: E402
    appendix_a_rollup,
    calibration_tiers,
    consistency_tier,
    grounded_tier,
    mean,
    safety_tier,
    schema_tier,
    verdict_tier,
)
from socratic_tutor.runner import Runner  # noqa: E402
from socratic_tutor.schema import parse_model_json  # noqa: E402

CRIT_LABELS = {
    "verdict": "Verdict correctness",
    "grounded": "Grounded reasoning",
    "rewrite_safety": "Rewrite safety",
    "schema": "Schema compliance",
    "calibration": "Calibration robustness",
    "consistency": "Consistency",
}
DIM_LABELS = {
    "spec_adherence": "Spec adherence",
    "task_quality": "Task quality",
    "robustness": "Robustness",
    "consistency": "Consistency",
}


def _input(row: dict) -> dict:
    return {
        "problem": row.get("problem", ""),
        "correct_solution": row.get("correct_solution", ""),
        "conversation_history": row.get("conversation_history") or [],
        "candidate_message": row.get("candidate_message", ""),
    }


def score_model(runner: Runner, gold: list[dict], use_judge: bool, k: int, temp: float):
    per_item, adv = [], []
    for row in gold:
        raw = runner.generate(_input(row), temp=0.0)
        out = parse_model_json(raw)
        pred = (out or {}).get("verdict")
        item = {
            "id": row.get("id"),
            "gold": row.get("gold_verdict"),
            "pred": pred,
            "verdict": verdict_tier(row.get("gold_verdict"), pred),
            "schema": schema_tier(raw, out),
            "grounded": grounded_tier(row, out, use_judge),
            "rewrite_safety": safety_tier(row, out, use_judge),
            "consistency": None,
        }
        if k > 0:
            verds = [(parse_model_json(runner.generate(_input(row), temp=temp)) or {}).get("verdict")
                     for _ in range(k)]
            item["consistency"] = consistency_tier(verds)
        per_item.append(item)
        if row.get("slice") == "calibration_adversarial":
            adv.append({"id": row.get("id"), "gold": row.get("gold_verdict"), "pred": pred})

    calib = calibration_tiers(adv)
    means = {
        "verdict": mean([i["verdict"] for i in per_item]),
        "grounded": mean([i["grounded"] for i in per_item]),
        "rewrite_safety": mean([i["rewrite_safety"] for i in per_item]),
        "schema": mean([i["schema"] for i in per_item]),
        "calibration": mean(calib) if calib else None,
        "consistency": mean([i["consistency"] for i in per_item]) if k > 0 else None,
    }
    counts = {
        "n": len(per_item),
        "rewrite_safety_n": sum(1 for i in per_item if i["rewrite_safety"] is not None),
        "calibration_items": len(adv),
        "calibration_pairs": len(calib),
    }
    return {"means": means, "counts": counts, "per_item": per_item}


def _fmt(x):
    return f"{x:.2f}" if isinstance(x, (int, float)) else "n/a"


def build_markdown(base: dict, tuned: dict | None, meta: dict) -> str:
    L = ["# Tiered rubric eval — Socratic Tutor Judge/Rewriter", ""]
    L.append(f"_Judge: **{meta['judge']}**. Scale 0-2 (mean tier per criterion). "
             f"n={base['counts']['n']} gold items._")
    L.append("")
    cols = ("base", "tuned", "Δ") if tuned else ("base",)
    L.append("## Per-criterion (0-2 mean)")
    L.append("Criterion | " + " | ".join(cols))
    L.append("---|" + "|".join("---" for _ in cols))
    for c in ["verdict", "grounded", "rewrite_safety", "schema", "calibration", "consistency"]:
        b = base["means"][c]
        if tuned:
            t = tuned["means"][c]
            d = (round(t - b, 2) if isinstance(b, (int, float)) and isinstance(t, (int, float)) else None)
            L.append(f"{CRIT_LABELS[c]} | {_fmt(b)} | {_fmt(t)} | {('+' if (d or 0) >= 0 else '') + _fmt(d) if d is not None else 'n/a'}")
        else:
            L.append(f"{CRIT_LABELS[c]} | {_fmt(b)}")

    L.append("")
    L.append("## Appendix A rollup (0-2 mean per dimension)")
    rb, rt = appendix_a_rollup(base["means"]), (appendix_a_rollup(tuned["means"]) if tuned else None)
    L.append("Dimension | " + " | ".join(cols))
    L.append("---|" + "|".join("---" for _ in cols))
    for d in ["spec_adherence", "task_quality", "robustness", "consistency"]:
        b = rb[d]
        if tuned:
            t = rt[d]
            delta = (round(t - b, 2) if isinstance(b, (int, float)) and isinstance(t, (int, float)) else None)
            L.append(f"{DIM_LABELS[d]} | {_fmt(b)} | {_fmt(t)} | {('+' if (delta or 0) >= 0 else '') + _fmt(delta) if delta is not None else 'n/a'}")
        else:
            L.append(f"{DIM_LABELS[d]} | {_fmt(b)}")

    # error-analysis (auto)
    L.append("")
    L.append("## Error analysis")
    target = tuned or base
    who = "tuned" if tuned else "base"
    weak = []
    for c in ["verdict", "grounded", "rewrite_safety", "schema", "calibration", "consistency"]:
        m = target["means"][c]
        if isinstance(m, (int, float)) and m < 2.0:
            zeros = sum(1 for i in target["per_item"] if i.get(c) == 0)
            ones = sum(1 for i in target["per_item"] if i.get(c) == 1)
            weak.append(f"**{CRIT_LABELS[c]}** {m:.2f} ({zeros}×tier0, {ones}×tier1)")
    L.append(f"The {who} model's remaining weak cells: " + ("; ".join(weak) if weak else "none — all criteria at 2.00.") + ".")
    L.append(f"Denominators — rewrite-safety scored over {target['counts']['rewrite_safety_n']} "
             f"non-adequate items; calibration over {target['counts']['calibration_items']} "
             f"adversarial items in {target['counts']['calibration_pairs']} pair-group(s).")
    if target["counts"]["calibration_items"] < 8:
        L.append("_Caveat: the adversarial slice is thin and its matched pairs are split across "
                 "train/test, so most are scored as singletons. A frozen, paired adversarial holdout "
                 "(kept intact by `build_dataset`) would make calibration robustness a stronger signal._")
    if meta["judge"].startswith("heuristic"):
        L.append("_Caveat: OPENAI_API_KEY was not set, so grounded-reasoning and rewrite-safety used the "
                 "deterministic heuristic (tiers 0/2 only, no tier-1 resolution). Re-run with the key for judged tiers._")
    return "\n".join(L) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--test", required=True)
    p.add_argument("--model", default=config.MODEL)
    p.add_argument("--adapter-path", default=None, help="tuned adapter; omit for base-only")
    p.add_argument("--out", required=True, help="output path stem (writes .md + .json)")
    p.add_argument("--consistency-k", type=int, default=3, help="samples per item for consistency (0 to skip)")
    p.add_argument("--consistency-temp", type=float, default=0.7)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--no-judge", action="store_true", help="force heuristic even if key is set")
    args = p.parse_args()

    gold = read_jsonl(args.test)
    if args.limit:
        gold = gold[: args.limit]
    if not gold:
        print(f"ERROR: no gold rows in {args.test}", file=sys.stderr)
        return 2

    use_judge = (not args.no_judge) and judge.judge_available()
    judge_label = f"OpenAI {judge.MODEL}" if use_judge else "heuristic (no OPENAI_API_KEY)"
    meta = {"judge": judge_label, "test": args.test, "k": args.consistency_k}
    print(f"[rubric] judge={judge_label}; k={args.consistency_k}; n={len(gold)}", file=sys.stderr)

    print("[rubric] scoring base ...", file=sys.stderr)
    base_runner = Runner(args.model, adapter_path=None)
    base = score_model(base_runner, gold, use_judge, args.consistency_k, args.consistency_temp)

    tuned = None
    if args.adapter_path:
        print("[rubric] scoring tuned ...", file=sys.stderr)
        tuned_runner = Runner(args.model, adapter_path=args.adapter_path)
        tuned = score_model(tuned_runner, gold, use_judge, args.consistency_k, args.consistency_temp)

    out_stem = Path(args.out)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, "base": base, "tuned": tuned}
    with open(out_stem.with_suffix(".json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    md = build_markdown(base, tuned, meta)
    with open(out_stem.with_suffix(".md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
