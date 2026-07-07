#!/usr/bin/env python3
"""Eval harness for the Socratic Tutor Adequacy Judge & Rewriter.

Scores a model-under-test against a labeled gold set on the 5 criteria from
docs/behavior_spec.md, and can produce a base-vs-tuned comparison table.

Runs fully unattended without an API key: criteria 1/4/5 are deterministic and
criteria 2/3 use deterministic heuristics by default. A stronger LLM-judge can
be injected later via `set_judge()` (kept out of the default path so the harness
never blocks on network/keys).

Usage:
    # smoke the harness against the base model alone (no training needed):
    python scripts/eval_harness.py --test eval/gold/test.jsonl --tag base

    # base-vs-tuned comparison in one shot:
    python scripts/eval_harness.py --test eval/gold/test.jsonl \
        --adapter-path adapters/smoke --out eval/results/smoke

    # offline harness self-test using pre-recorded outputs (no MLX load):
    python scripts/eval_harness.py --test eval/gold/test.jsonl \
        --fixture-in some_outputs.jsonl --tag fixture
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Make the repo root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from socratic_tutor import config
from socratic_tutor.io_utils import read_jsonl, write_jsonl
from socratic_tutor.prompts import build_inference_prompt
from socratic_tutor.schema import VERDICTS, parse_model_json, validate_output

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "so", "to", "of", "in",
    "on", "for", "with", "your", "you", "that", "this", "is", "are", "was",
    "were", "be", "it", "as", "at", "by", "from", "how", "what", "why", "which",
    "do", "does", "did", "can", "could", "would", "should", "have", "has",
    "student", "message", "answer", "problem", "solution", "hint", "tutor",
}

# Injectable LLM judge; None => deterministic heuristics only (default).
_JUDGE = None


def set_judge(judge_fn) -> None:
    """Install an optional judge: judge_fn(kind, payload) -> bool.

    kind in {"grounded", "rewrite_safe"}. Left unset for unattended runs.
    """
    global _JUDGE
    _JUDGE = judge_fn


# --------------------------------------------------------------------------- #
# Text helpers for the deterministic heuristics
# --------------------------------------------------------------------------- #
def _numbers(text: str) -> set[str]:
    return set(re.findall(r"-?\d+(?:\.\d+)?", text or ""))


def _sig_tokens(text: str) -> set[str]:
    toks = re.findall(r"[a-zA-Z]{4,}", (text or "").lower())
    return {t for t in toks if t not in _STOPWORDS}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


# --------------------------------------------------------------------------- #
# Criterion 2: grounded reasoning (heuristic)
# --------------------------------------------------------------------------- #
def reasoning_is_grounded(row: dict, out: dict) -> bool:
    reasoning = out.get("reasoning") or ""
    if not reasoning.strip():
        return False
    source = " ".join(
        [row.get("problem", ""), row.get("correct_solution", ""),
         row.get("candidate_message", ""), *(row.get("conversation_history") or [])]
    )
    if _numbers(reasoning) & _numbers(source):
        return True
    if _sig_tokens(reasoning) & _sig_tokens(source):
        return True
    if _JUDGE is not None:
        try:
            return bool(_JUDGE("grounded", {"row": row, "out": out}))
        except Exception:
            return False
    return False


# --------------------------------------------------------------------------- #
# Criterion 3: rewrite safety (heuristic) — only meaningful for non-adequate
# --------------------------------------------------------------------------- #
def rewrite_is_safe(row: dict, out: dict) -> bool | None:
    """True/False for non-adequate verdicts; None when N/A (adequate/no rewrite)."""
    if out.get("verdict") == "adequate":
        return None
    rewrite = out.get("rewritten_message")
    if not isinstance(rewrite, str) or not rewrite.strip():
        return None
    rw = _normalize(rewrite)

    final = _normalize(str(row.get("final_answer", "")))
    if final and re.search(rf"(?<!\d){re.escape(final)}(?!\d)", rw):
        return False  # leaks the literal final answer

    # If the rewrite reproduces nearly ALL key-step keywords, treat as leaking the
    # step. Kept conservative (>=3 tokens AND >=75% of them): good Socratic hints
    # naturally reuse domain nouns ("perimeter", "sides"), which is not a leak.
    key_step = row.get("key_step", "")
    ks_tokens = _sig_tokens(key_step)
    if ks_tokens:
        overlap = ks_tokens & _sig_tokens(rewrite)
        if len(overlap) >= 3 and len(overlap) / len(ks_tokens) >= 0.75:
            return False

    if _JUDGE is not None:
        try:
            return bool(_JUDGE("rewrite_safe", {"row": row, "out": out}))
        except Exception:
            return True  # judge error shouldn't fail-closed a heuristic pass
    return True


# --------------------------------------------------------------------------- #
# Model runners
# --------------------------------------------------------------------------- #
def _make_greedy_sampler():
    try:
        from mlx_lm.sample_utils import make_sampler
        return make_sampler(temp=0.0)
    except Exception:
        return None


def mlx_runner(model_id: str, adapter_path: str | None, max_tokens: int):
    """Return a fn(prompt)->text backed by a loaded MLX model."""
    from mlx_lm import generate, load

    model, tokenizer = load(model_id, adapter_path=adapter_path)
    sampler = _make_greedy_sampler()

    def run(inp: dict) -> str:
        prompt = build_inference_prompt(tokenizer, inp)
        kwargs = {"max_tokens": max_tokens, "verbose": False}
        if sampler is not None:
            kwargs["sampler"] = sampler
        try:
            return generate(model, tokenizer, prompt=prompt, **kwargs)
        except TypeError:
            kwargs.pop("sampler", None)
            return generate(model, tokenizer, prompt=prompt, **kwargs)

    return run


def fixture_runner(fixture_path: str):
    """Replay pre-recorded outputs keyed by row id (offline harness self-test)."""
    recorded = {r["id"]: r.get("raw_output", "") for r in read_jsonl(fixture_path)}

    def run(inp: dict) -> str:
        return recorded.get(inp.get("id"), "")

    return run


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def evaluate(gold_rows: list[dict], run_fn, record_raw: list | None = None) -> dict:
    n = len(gold_rows)
    verdict_correct = 0
    schema_ok = 0
    grounded_ok = 0
    safe_total = 0
    safe_ok = 0
    calib_total = 0
    calib_correct = 0
    confusion: dict[str, dict[str, int]] = {v: {u: 0 for u in VERDICTS} for v in VERDICTS}
    per_item = []

    for row in gold_rows:
        raw = run_fn(row)
        if record_raw is not None:
            record_raw.append({"id": row.get("id"), "raw_output": raw})
        out = parse_model_json(raw)
        ok_schema, _ = validate_output(out) if out is not None else (False, ["unparseable"])
        pred = (out or {}).get("verdict")
        gold = row.get("gold_verdict")

        if ok_schema:
            schema_ok += 1
        if pred == gold and gold in VERDICTS:
            verdict_correct += 1
        if gold in confusion and pred in confusion[gold]:
            confusion[gold][pred] += 1

        grounded = bool(out) and reasoning_is_grounded(row, out)
        if grounded:
            grounded_ok += 1

        safe = rewrite_is_safe(row, out) if out else None
        if safe is not None:
            safe_total += 1
            if safe:
                safe_ok += 1

        if row.get("slice") == "calibration_adversarial":
            calib_total += 1
            if pred == gold:
                calib_correct += 1

        per_item.append({
            "id": row.get("id"), "gold": gold, "pred": pred,
            "schema_ok": ok_schema, "grounded": grounded, "rewrite_safe": safe,
        })

    def pct(a, b):
        return round(100.0 * a / b, 1) if b else None

    return {
        "n": n,
        "verdict_accuracy": pct(verdict_correct, n),
        "grounded_reasoning": pct(grounded_ok, n),
        "rewrite_safety": pct(safe_ok, safe_total),
        "rewrite_safety_n": safe_total,
        "schema_compliance": pct(schema_ok, n),
        "calibration_robustness": pct(calib_correct, calib_total),
        "calibration_n": calib_total,
        "confusion": confusion,
        "per_item": per_item,
    }


CRITERIA = [
    ("verdict_accuracy", "Verdict accuracy"),
    ("grounded_reasoning", "Grounded reasoning (heuristic)"),
    ("rewrite_safety", "Rewrite safety (heuristic)"),
    ("schema_compliance", "Schema compliance"),
    ("calibration_robustness", "Calibration robustness"),
]


def comparison_markdown(results: dict[str, dict]) -> str:
    tags = list(results.keys())
    lines = ["# Eval results — Socratic Tutor Judge/Rewriter", ""]
    lines.append("Metric | " + " | ".join(tags) + (" | Δ" if len(tags) == 2 else ""))
    lines.append("|".join(["---"] * (len(tags) + 1 + (1 if len(tags) == 2 else 0))))
    for key, label in CRITERIA:
        cells = []
        for t in tags:
            v = results[t].get(key)
            cells.append("n/a" if v is None else f"{v}%")
        row = f"{label} | " + " | ".join(cells)
        if len(tags) == 2:
            a, b = results[tags[0]].get(key), results[tags[1]].get(key)
            row += f" | {round(b - a, 1):+}" if (a is not None and b is not None) else " | —"
        lines.append(row)
    lines.append("")
    lines.append(f"_n = {results[tags[0]]['n']} gold items; "
                 f"rewrite-safety over non-adequate items only; "
                 f"calibration over the adversarial slice._")
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default=config.MODEL)
    p.add_argument("--adapter-path", default=None,
                   help="If set, ALSO evaluate base+adapter and emit a base-vs-tuned table.")
    p.add_argument("--test", default=str(config.GOLD_DIR / "test.jsonl"))
    p.add_argument("--out", default=str(config.RESULTS_DIR / "eval"),
                   help="Output path prefix (writes <out>.md and <out>.json).")
    p.add_argument("--tag", default="base", help="Label when evaluating a single model.")
    p.add_argument("--max-tokens", type=int, default=config.MAX_TOKENS)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--fixture-in", default=None,
                   help="Replay outputs from this jsonl instead of loading MLX (offline self-test).")
    p.add_argument("--fixture-out", default=None,
                   help="Record raw model outputs to this jsonl for later offline scoring.")
    args = p.parse_args()

    gold = read_jsonl(args.test)
    if args.limit:
        gold = gold[: args.limit]
    if not gold:
        print(f"ERROR: no gold rows in {args.test}", file=sys.stderr)
        return 2

    results: dict[str, dict] = {}
    raw_sink: list = [] if args.fixture_out else None

    if args.fixture_in:
        run = fixture_runner(args.fixture_in)
        results[args.tag] = evaluate(gold, run, record_raw=raw_sink)
    else:
        print(f"[eval] loading base model {args.model} ...", file=sys.stderr)
        base_run = mlx_runner(args.model, None, args.max_tokens)
        results["base"] = evaluate(gold, base_run, record_raw=raw_sink)
        if args.adapter_path:
            print(f"[eval] loading tuned model + adapter {args.adapter_path} ...", file=sys.stderr)
            tuned_run = mlx_runner(args.model, args.adapter_path, args.max_tokens)
            results["tuned"] = evaluate(gold, tuned_run)
        else:
            # single-model run: relabel "base" with the requested tag
            results = {args.tag: results["base"]}

    out_prefix = Path(args.out)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    md = comparison_markdown(results)
    (out_prefix.with_suffix(".md")).write_text(md, encoding="utf-8")
    (out_prefix.with_suffix(".json")).write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    if raw_sink is not None:
        write_jsonl(args.fixture_out, raw_sink)

    print(md)
    print(f"[eval] wrote {out_prefix.with_suffix('.md')} and {out_prefix.with_suffix('.json')}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
