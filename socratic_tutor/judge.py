"""Independent LLM-as-judge (OpenAI) for the two judgment-heavy criteria:
grounded reasoning and rewrite safety, each scored on the 0/1/2 tier rubric.

Uses an OpenAI model (default gpt-4.1) deliberately different from the tuned model's
family (Qwen distilled from Claude) to avoid self-preference bias. Reads OPENAI_API_KEY
from the environment; when absent, judge_available() is False and callers fall back to
the deterministic heuristic. Transient API errors are retried with backoff (per the
project's rate-limit rule) before giving up on a single item.
"""

import json
import os
import time

MODEL = os.environ.get("OPENAI_JUDGE_MODEL", "gpt-4.1")

GROUNDED_RUBRIC = (
    "Score how well the judge model's REASONING is grounded in and justifies its verdict.\n"
    "2 = cites a SPECIFIC, real detail from the problem/solution/history that actually "
    "justifies the verdict (e.g. quotes the exact phrase in the candidate message that leaks the step).\n"
    "1 = references a real detail but it is generic or not the decisive one — right ballpark, weak link to the verdict.\n"
    "0 = boilerplate/generic reasoning, cites something not present, or contradicts the verdict."
)

SAFETY_RUBRIC = (
    "Score whether the REWRITTEN tutor message is a safe Socratic hint for this problem.\n"
    "2 = a student could NOT finish by copying it: it states neither the final answer nor the single key "
    "step/insight, uses no isomorphic worked example, and is grounded in the student's most recent message.\n"
    "1 = does not state the final answer but nudges close to the key step (partial leak), OR is safe but "
    "generic / not grounded in the student's specific attempt.\n"
    "0 = leaks the final answer or the key step (including via a worked or unsolved isomorphic example) — "
    "a student could finish with no further thinking."
)


def judge_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _client():
    from openai import OpenAI

    return OpenAI()


def _ask_tier(system: str, user: str, max_wait: float = 180.0):
    """Call the judge, return an int tier in {0,1,2} or None on persistent failure.

    Retries transient errors with escalating backoff up to ~max_wait seconds total,
    then returns None so one flaky call falls back to the heuristic rather than
    stalling the whole eval.
    """
    delays = [2, 5, 10, 20, 40, 60]
    waited = 0.0
    last_err = None
    for i in range(len(delays) + 1):
        try:
            client = _client()
            resp = client.chat.completions.create(
                model=MODEL,
                temperature=0,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
            )
            obj = json.loads(resp.choices[0].message.content)
            tier = int(obj["tier"])
            return tier if tier in (0, 1, 2) else None
        except Exception as e:  # noqa: BLE001 — retry any transient API/parse error
            last_err = e
            if i >= len(delays) or waited >= max_wait:
                break
            time.sleep(delays[i])
            waited += delays[i]
    print(f"[judge] giving up after retries ({last_err}); falling back to heuristic")
    return None


def _fmt_context(row: dict) -> str:
    hist = row.get("conversation_history") or []
    hist_str = "\n".join(f"- {h}" for h in hist) if hist else "(none yet)"
    return (
        f"PROBLEM:\n{row.get('problem','')}\n\n"
        f"CORRECT SOLUTION (ground truth):\n{row.get('correct_solution','')}\n\n"
        f"FINAL ANSWER: {row.get('final_answer','')}\n"
        f"KEY STEP: {row.get('key_step','')}\n\n"
        f"CONVERSATION SO FAR:\n{hist_str}\n\n"
        f"CANDIDATE TUTOR MESSAGE (the message being judged):\n{row.get('candidate_message','')}"
    )


def grade_grounded(row: dict, out: dict):
    if not judge_available():
        return None
    system = (
        "You are a strict evaluator applying a fixed 0/1/2 rubric. "
        "Return ONLY a JSON object: {\"tier\": 0|1|2, \"why\": \"<one sentence>\"}.\n\n"
        + GROUNDED_RUBRIC
    )
    user = (
        _fmt_context(row)
        + f"\n\nMODEL VERDICT: {out.get('verdict')}"
        + f"\nMODEL REASONING (score this): {out.get('reasoning')}"
    )
    return _ask_tier(system, user)


def grade_rewrite_safe(row: dict, out: dict):
    if not judge_available():
        return None
    system = (
        "You are a strict evaluator applying a fixed 0/1/2 rubric. "
        "Return ONLY a JSON object: {\"tier\": 0|1|2, \"why\": \"<one sentence>\"}.\n\n"
        + SAFETY_RUBRIC
    )
    user = (
        _fmt_context(row)
        + f"\n\nMODEL VERDICT: {out.get('verdict')}"
        + f"\nREWRITTEN MESSAGE (score this): {out.get('rewritten_message')}"
    )
    return _ask_tier(system, user)
