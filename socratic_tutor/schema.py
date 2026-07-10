"""Taxonomy, output parsing, and schema validation for the judge/rewriter.

The model must emit a single JSON object:
    {"verdict": <one of VERDICTS>, "reasoning": <str>, "rewritten_message": <str|null>}
with rewritten_message null iff verdict == "adequate".
"""

import json
import re

VERDICTS = [
    "adequate",
    "gives_final_answer",
    "gives_away_key_step",
    "mismatched_calibration",
    "vague_unhelpful",
]
VERDICT_SET = set(VERDICTS)
OUTPUT_KEYS = {"verdict", "reasoning", "rewritten_message"}


def strip_think(text: str) -> str:
    """Remove Qwen3 <think>...</think> blocks, including an unclosed trailing one."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL)  # unclosed
    return text


def _first_balanced_json(text: str):
    """Return the first balanced {...} substring, respecting string literals/escapes."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None


def parse_model_json(text: str):
    """Best-effort extract the model's JSON object. Returns dict or None.

    Never raises: a chatty/invalid output returns None and is scored as a
    schema-compliance failure by the eval harness rather than crashing it.
    """
    if not isinstance(text, str):
        return None
    candidate = _first_balanced_json(strip_think(text))
    if candidate is None:
        return None
    try:
        obj = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def validate_output(obj) -> tuple[bool, list[str]]:
    """Check an output dict against the schema. Returns (ok, errors)."""
    errors: list[str] = []
    if not isinstance(obj, dict):
        return False, ["output is not a JSON object"]

    verdict = obj.get("verdict")
    if verdict not in VERDICT_SET:
        errors.append(f"invalid or missing verdict: {verdict!r}")

    reasoning = obj.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        errors.append("reasoning missing or empty")

    has_rm = "rewritten_message" in obj
    rm = obj.get("rewritten_message")
    if not has_rm:
        errors.append("rewritten_message key missing")
    elif verdict == "adequate":
        if rm is not None:
            errors.append("rewritten_message must be null when verdict == adequate")
    else:  # non-adequate verdict
        if not isinstance(rm, str) or not rm.strip():
            errors.append("rewritten_message required (non-null) when verdict != adequate")

    extra = set(obj.keys()) - OUTPUT_KEYS
    if extra:
        errors.append(f"unexpected keys: {sorted(extra)}")

    return (len(errors) == 0), errors


def validate_input(obj) -> tuple[bool, list[str]]:
    """Check an input dict has the required fields with correct types."""
    errors: list[str] = []
    if not isinstance(obj, dict):
        return False, ["input is not a JSON object"]
    for key in ("problem", "correct_solution", "candidate_message"):
        if not isinstance(obj.get(key), str) or not obj[key].strip():
            errors.append(f"{key} missing or empty")
    hist = obj.get("conversation_history")
    if not isinstance(hist, list) or not all(isinstance(h, str) for h in hist):
        errors.append("conversation_history must be a list of strings")
    return (len(errors) == 0), errors
