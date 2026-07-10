"""Grounded-reasoning annotation for real-dataset rows (OpenAI gpt-4.1).

The verdict and rewrite come from the source dataset's HUMAN labels; only the
free-text `reasoning` is model-written here, grounded in the real item. Reads
OPENAI_API_KEY; returns None if unavailable so callers can fall back to a template.
"""

import json
import os
import time

MODEL = os.environ.get("OPENAI_JUDGE_MODEL", "gpt-4.1")


def available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _client():
    from openai import OpenAI

    return OpenAI()


def write_reasoning(problem: str, history: list[str], candidate: str, verdict: str,
                    max_wait: float = 120.0):
    if not available():
        return None
    system = (
        "You write ONE-sentence grounded justifications for a math-tutoring verdict. "
        "Cite a SPECIFIC detail from the candidate message (or problem) — never a generic label. "
        'Output ONLY JSON: {"reasoning": "<one sentence>"}.'
    )
    hist = "\n".join(history) if history else "(none)"
    user = (
        f"PROBLEM: {problem}\n\nCONVERSATION SO FAR:\n{hist}\n\n"
        f"CANDIDATE TUTOR MESSAGE: {candidate}\n\n"
        f"VERDICT (human-labeled, given): {verdict}\n"
        "Write the one-sentence reasoning that cites a specific detail justifying this verdict."
    )
    delays = [2, 5, 10, 20, 40]
    waited = 0.0
    for i in range(len(delays) + 1):
        try:
            r = _client().chat.completions.create(
                model=MODEL, temperature=0,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
            )
            return json.loads(r.choices[0].message.content)["reasoning"]
        except Exception:
            if i >= len(delays) or waited >= max_wait:
                return None
            time.sleep(delays[i])
            waited += delays[i]
    return None
