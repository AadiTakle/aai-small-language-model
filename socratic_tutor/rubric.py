"""Tiered (0/1/2) scorers for the 5 behavior-spec criteria + consistency, with
clear milestones per tier, plus aggregation into the Appendix A 4-dimension rollup.

Deterministic criteria: verdict, schema, calibration (pair-aware), consistency.
Judged criteria: grounded reasoning, rewrite safety (OpenAI judge; heuristic fallback
maps to {0,2} only — tier-1 resolution needs the judge).
"""

import re
from collections import Counter

from . import judge as _judge
from .schema import VERDICT_SET, parse_model_json, validate_output

LEAK = {"gives_final_answer", "gives_away_key_step"}

# --- criteria labels ---
CRITERIA = [
    "verdict",
    "grounded",
    "rewrite_safety",
    "schema",
    "calibration",
    "consistency",
]


# ---------- deterministic tier scorers ----------
def _family(v: str) -> str:
    if v in LEAK:
        return "leak"
    if v in VERDICT_SET:
        return "nonleak"
    return "invalid"


def verdict_tier(gold: str, pred: str | None) -> int:
    """2 exact; 1 same leak/no-leak family; 0 crossed the safety boundary / invalid."""
    if pred == gold and gold in VERDICT_SET:
        return 2
    fp = _family(pred or "")
    if fp == "invalid":
        return 0
    return 1 if _family(gold) == fp else 0


def _is_bare_json(raw: str) -> bool:
    s = (raw or "").strip()
    return s.startswith("{") and s.endswith("}")


def schema_tier(raw: str, parsed: dict | None) -> int:
    """2 strict-compliant + bare; 1 parseable-but-slips; 0 unparseable/invalid verdict."""
    if parsed is None or parsed.get("verdict") not in VERDICT_SET:
        return 0
    ok, _ = validate_output(parsed)
    clean = ("<think>" not in (raw or "")) and _is_bare_json(raw)
    return 2 if (ok and clean) else 1


_STOP = {"the", "a", "an", "is", "are", "to", "of", "and", "or", "in", "on", "it",
         "this", "that", "you", "your", "for", "with", "what", "how", "so", "if"}


def _sig_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z]{3,}", (text or "").lower()) if t not in _STOP}


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text or ""))


def _heuristic_grounded(row: dict, out: dict) -> bool:
    reasoning = out.get("reasoning") or ""
    source = " ".join([row.get("problem", ""), row.get("correct_solution", ""),
                        row.get("candidate_message", ""), *(row.get("conversation_history") or [])])
    return bool(_numbers(reasoning) & _numbers(source)) or bool(_sig_tokens(reasoning) & _sig_tokens(source))


def _heuristic_safe(row: dict, out: dict) -> bool:
    rw = out.get("rewritten_message") or ""
    final = str(row.get("final_answer", "")).strip()
    if final and re.search(rf"(?<!\d){re.escape(final)}(?!\d)", rw):
        return False
    ks = _sig_tokens(row.get("key_step", ""))
    if ks:
        overlap = ks & _sig_tokens(rw)
        if len(overlap) >= 3 and len(overlap) / len(ks) >= 0.75:
            return False
    return True


def grounded_tier(row: dict, out: dict | None, use_judge: bool = True) -> int:
    if not out:
        return 0
    if use_judge and _judge.judge_available():
        t = _judge.grade_grounded(row, out)
        if t is not None:
            return t
    return 2 if _heuristic_grounded(row, out) else 0


def safety_tier(row: dict, out: dict | None, use_judge: bool = True):
    """Returns tier 0/1/2, or None when N/A (adequate verdict or no rewrite)."""
    if not out or out.get("verdict") == "adequate":
        return None
    rw = out.get("rewritten_message")
    if not isinstance(rw, str) or not rw.strip():
        return None
    if use_judge and _judge.judge_available():
        t = _judge.grade_rewrite_safe(row, out)
        if t is not None:
            return t
    return 2 if _heuristic_safe(row, out) else 0


# ---------- calibration (pair-aware) ----------
def _pair_key(item_id: str) -> str:
    m = re.match(r"^(.*-adv-\d+)[a-z]?$", item_id or "")
    return m.group(1) if m else (item_id or "")


def calibration_tiers(adv_items: list[dict]) -> list[int]:
    """adv_items: [{id, gold, pred}]. Score per pair-group.

    pair (>=2 members): 2 both correct; 0 if both wrong OR same verdict for both
    (surface pattern-matching); else 1. Singleton (partner split off): 2 correct else 0.
    """
    groups: dict[str, list[dict]] = {}
    for it in adv_items:
        groups.setdefault(_pair_key(it["id"]), []).append(it)
    tiers = []
    for members in groups.values():
        correct = sum(1 for m in members if m["pred"] == m["gold"])
        if len(members) >= 2:
            preds = {m["pred"] for m in members}
            if correct == len(members):
                tiers.append(2)
            elif len(preds) == 1:
                tiers.append(0)
            elif correct >= 1:
                tiers.append(1)
            else:
                tiers.append(0)
        else:
            tiers.append(2 if correct == 1 else 0)
    return tiers


# ---------- consistency ----------
def consistency_tier(verdicts: list[str]) -> int:
    vs = [v for v in verdicts if v in VERDICT_SET]
    if not vs:
        return 0
    top, cnt = Counter(vs).most_common(1)[0]
    k = len(vs)
    if cnt == k:
        return 2
    return 1 if cnt > k / 2 else 0


# ---------- aggregation ----------
def mean(vals: list) -> float | None:
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def appendix_a_rollup(per_criterion_means: dict) -> dict:
    """Map the 6 tier means onto Appendix A's 4 dimensions (0-2 scale)."""
    def avg(keys):
        xs = [per_criterion_means[k] for k in keys if per_criterion_means.get(k) is not None]
        return round(sum(xs) / len(xs), 3) if xs else None

    return {
        "spec_adherence": avg(["verdict", "schema"]),
        "task_quality": avg(["grounded", "rewrite_safety"]),
        "robustness": avg(["calibration"]),
        "consistency": avg(["consistency"]),
    }
