"""Shared pieces for the verdict/rewrite split experiment (overnight run).

Two adapters, two tasks, each with its OWN task-specific system prompt (rendered through the same
socratic_tutor.prompts helpers via their `system=` param, so train/inference token streams match):

  - VERDICT task  : {problem, solution, conversation, candidate} -> {"verdict","reasoning"}   (no rewrite)
  - REWRITE task  : {problem, solution, conversation, candidate, verdict, reason} -> a plain-text hint

Everything here is pure-code + a robust gateway client. No editing of training rows anywhere.
"""

from __future__ import annotations

import os
import random
import re
import sys
import threading
import time
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

import json  # noqa: E402

from socratic_tutor.prompts import (  # noqa: E402
    _apply_template, build_inference_prompt, render_training_text,
)
from socratic_tutor.schema import VERDICTS, strip_think  # noqa: E402

LEAK = {"gives_final_answer", "gives_away_key_step"}

# --------------------------------------------------------------------------- #
# Task-specific system prompts (verdict-only / rewrite-only)
# --------------------------------------------------------------------------- #
VERDICT_SYSTEM = """You are a Socratic Tutor Adequacy Judge for K-12 math tutoring.

You are given a math problem, its correct solution (ground truth, for your judgment only \
— never reveal it to the student), the conversation so far, and a candidate tutor message. \
Judge whether the candidate message is pedagogically adequate.

Return ONLY a single JSON object, with no prose before or after, with exactly these keys:
- "verdict": one of "adequate", "gives_final_answer", "gives_away_key_step", "mismatched_calibration", "vague_unhelpful"
- "reasoning": a short explanation that cites a SPECIFIC detail from the problem, solution, or conversation (never a bare generic label)

Taxonomy:
- adequate: scaffolds productively; neither states the answer nor the key step; calibrated to the student's current attempt.
- gives_final_answer: states the actual final answer/result, explicitly or as a close paraphrase.
- gives_away_key_step: does not state the final answer, but hands over the single insight/technique/operation-choice that makes the rest trivial (including via a worked OR unsolved isomorphic example that shares the same structure with different numbers).
- mismatched_calibration: a genuine hint pitched at the wrong level — re-explaining something the student already showed they understand, or assuming a leap they have not made.
- vague_unhelpful: generic encouragement or a non-answer ("keep trying!") with no actionable scaffolding tied to the specific problem or the student's attempt.

Output the JSON object and nothing else."""

REWRITE_SYSTEM = """You are an expert Socratic math tutor for a K-12 student.

You are given a math problem, its correct solution (for your reference ONLY — never reveal it), \
the conversation so far, a candidate tutor message that has ALREADY been judged pedagogically \
inadequate, and the reason it was flagged. Rewrite the candidate into a single calibrated Socratic \
hint that fixes the flagged problem.

Hard rules for your rewrite:
- Never state the final answer (explicitly or as a close paraphrase).
- Never hand over the single key step / insight / operation-choice that makes the rest trivial (not even via a worked isomorphic example).
- Ask ONE focused guiding question, grounded in the student's most recent message and calibrated to what they have already shown they understand.
- Be concise: one or two sentences.

Reply with ONLY your rewritten tutor message: no preamble, no meta-commentary, no labels, no JSON."""


def build_verdict_user_prompt(inp: dict) -> str:
    """User turn for the VERDICT task (same content the judge always saw)."""
    hist = inp.get("conversation_history") or []
    hist_str = "\n".join(f"- {h}" for h in hist) if hist else "(none yet)"
    return (
        f"PROBLEM:\n{inp['problem']}\n\n"
        f"CORRECT SOLUTION (ground truth — for your judgment only, never reveal to the student):\n"
        f"{inp['correct_solution']}\n\n"
        f"CONVERSATION SO FAR:\n{hist_str}\n\n"
        f"CANDIDATE TUTOR MESSAGE (the message to judge):\n{inp['candidate_message']}\n\n"
        "Return the JSON object now."
    )


def build_rewrite_user_prompt(inp: dict, verdict: str, reason: str = "") -> str:
    """User turn for the REWRITE task — includes the verdict + why it was flagged."""
    hist = inp.get("conversation_history") or []
    hist_str = "\n".join(f"- {h}" for h in hist) if hist else "(none yet)"
    why = f"\nWHY IT WAS FLAGGED ({verdict}): {reason}" if reason else f"\nVERDICT: {verdict}"
    return (
        f"PROBLEM:\n{inp['problem']}\n\n"
        f"CORRECT SOLUTION (reference only — never reveal):\n{inp['correct_solution']}\n\n"
        f"CONVERSATION SO FAR:\n{hist_str}\n\n"
        f"FLAGGED CANDIDATE TUTOR MESSAGE:\n{inp['candidate_message']}{why}\n\n"
        "Write the single rewritten tutor message now:"
    )


def input_dict(row: dict) -> dict:
    return {"problem": row["problem"], "correct_solution": row["correct_solution"],
            "conversation_history": row.get("conversation_history") or [],
            "candidate_message": row["candidate_message"]}


# --------------------------------------------------------------------------- #
# Deterministic features (for balancing + reporting) — pure code, no LLM
# --------------------------------------------------------------------------- #
_TOPIC_RULES = [
    ("geometry", ["area", "perimeter", "angle", "triangle", "rectangle", "square ",
                  "circle", "volume", "radius", "diameter", "cm", "meter"]),
    ("fraction", ["fraction", "numerator", "denominator", "/2", "/3", "/4", "/5", "/6", "/8", "1/", "2/", "3/"]),
    ("percent", ["percent", "%", "discount", "% off"]),
    ("ratio_rate", ["ratio", "proportion", "per ", "rate", "miles per", "for every"]),
    ("money", ["$", "cost", "price", "dollar", "cents", "change"]),
    ("algebra", ["solve for", "equation", "variable", "slope", "x =", "2x", "3x", "x^2", "y ="]),
    ("time_measure", ["hour", "minute", "o'clock", "how long", "weigh", "ounce", "pound", "liter"]),
]


def topic_of(problem: str) -> str:
    s = (problem or "").lower()
    for name, kws in _TOPIC_RULES:
        if any(k in s for k in kws):
            return name
    return "arithmetic"


def _nwords(t: str) -> int:
    return len((t or "").split())


def features(row: dict) -> dict:
    """Deterministic axis buckets for a structured row."""
    cand = row.get("candidate_message", "") or ""
    nw = _nwords(cand)
    len_bucket = "short(<15w)" if nw < 15 else ("med(15-35w)" if nw <= 35 else "long(>35w)")
    turns = len(row.get("conversation_history") or [])
    turns_bucket = "t<=1" if turns <= 1 else ("t2-3" if turns <= 3 else "t4+")
    nnum = len(re.findall(r"-?\d+(?:\.\d+)?", row.get("problem", "") or ""))
    nnum_bucket = "nums<=2" if nnum <= 2 else ("nums3-4" if nnum <= 4 else "nums5+")
    return {
        "verdict": row.get("verdict"),
        "band": row.get("band") or "?",
        "len": len_bucket,
        "turns": turns_bucket,
        "topic": topic_of(row.get("problem", "")),
        "nnum": nnum_bucket,
    }


# --------------------------------------------------------------------------- #
# Deterministic rewrite-safety checks (leak / length / answer-echo)
# --------------------------------------------------------------------------- #
def rewrite_leaks(rewrite: str, row: dict) -> bool:
    """True if the rewrite leaks the final answer as a standalone number NOT already in the
    problem/history, OR reproduces >=75% (and >=3) of the key-step content words."""
    rw = (rewrite or "").lower()
    if not rw.strip():
        return False
    fa = str(row.get("final_answer", "")).strip().lower()
    if fa:
        pat = rf"(?<!\d){re.escape(fa)}(?!\d)"
        ctx = (row.get("problem", "") + " " + " ".join(row.get("conversation_history") or [])).lower()
        if re.search(pat, rw) and not re.search(pat, ctx):
            return True
    ks = row.get("key_step", "") or ""
    kt = {w for w in re.findall(r"[a-zA-Z]{4,}", ks.lower())}
    if kt:
        ov = kt & {w for w in re.findall(r"[a-zA-Z]{4,}", rw)}
        if len(ov) >= 3 and len(ov) / len(kt) >= 0.75:
            return True
    return False


# --------------------------------------------------------------------------- #
# Robust gateway client (temp-fallback + retries; caches temp-rejecting models)
# --------------------------------------------------------------------------- #
_no_temp: set[str] = set()
_client_lock = threading.Lock()
_client = None


def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            from openai import OpenAI
            _client = OpenAI(timeout=120, max_retries=5)
        return _client


def gate_chat(model: str, system: str, user: str, temp: float = 0.0, tries: int = 3) -> str:
    """One gateway chat completion. Returns text, or '' after exhausting retries (never raises)."""
    client = _get_client()
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for attempt in range(max(1, tries)):
        for kw in ([{}] if model in _no_temp else [{"temperature": temp}, {}]):
            try:
                r = client.chat.completions.create(model=model, messages=msgs, **kw)
                txt = (r.choices[0].message.content or "").strip()
                if txt:
                    return txt
            except Exception as e:  # noqa: BLE001
                if "temperature" in str(e).lower():
                    _no_temp.add(model)
        if attempt + 1 < tries:
            time.sleep(1.5 * (attempt + 1))
    return ""


def parallel_map(fn, items, workers: int = 6):
    """Thread-pool map preserving order; exceptions -> None."""
    from concurrent.futures import ThreadPoolExecutor
    out = [None] * len(items)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fn, it): i for i, it in enumerate(items)}
        for f in futs:
            i = futs[f]
            try:
                out[i] = f.result()
            except Exception:  # noqa: BLE001
                out[i] = None
    return out


def clean_hint(text: str) -> str:
    """Normalize a rewrite-model output to a plain hint (strip think, code fences, quotes, labels)."""
    t = strip_think(text or "").strip()
    t = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", t).strip()
    t = re.sub(r'^(tutor|rewrite|rewritten message|hint)\s*:\s*', "", t, flags=re.I).strip()
    if len(t) >= 2 and t[0] in "\"'" and t[-1] == t[0]:
        t = t[1:-1].strip()
    return t


# Strong frontier candidates on the gateway (verified available this session).
FRONTIER = {
    "opus-4.8": "claude-group/claude-opus-4-8",
    "gpt-5.6": "openai-group/gpt-5.6-sol",
    "gpt-5.5": "openai-group/gpt-5.5",
    "sonnet-5": "claude-group/claude-sonnet-5",
    "gpt-5.6-luna": "openai-group/gpt-5.6-luna",
}


# --------------------------------------------------------------------------- #
# Per-task rendering (train) + inference prompts.  The VERDICT task reuses the
# project's standard user prompt (build_user_prompt, via render_training_text /
# build_inference_prompt) with the verdict-only SYSTEM; the REWRITE task builds
# its own user turn (adds the verdict + flag reason) and emits a plain-text hint.
# --------------------------------------------------------------------------- #
def verdict_target(row: dict) -> str:
    return json.dumps({"verdict": row["verdict"], "reasoning": row.get("reasoning", "")},
                      ensure_ascii=False)


def render_verdict_text(tok, inp: dict, row: dict) -> str:
    return render_training_text(tok, inp, verdict_target(row), system=VERDICT_SYSTEM)


def infer_verdict_prompt(tok, inp: dict) -> str:
    return build_inference_prompt(tok, inp, system=VERDICT_SYSTEM)


def render_rewrite_text(tok, inp: dict, verdict: str, reason: str, hint: str) -> str:
    msgs = [{"role": "system", "content": REWRITE_SYSTEM},
            {"role": "user", "content": build_rewrite_user_prompt(inp, verdict, reason)},
            {"role": "assistant", "content": hint}]
    return _apply_template(tok, msgs, add_generation_prompt=False)


def infer_rewrite_prompt(tok, inp: dict, verdict: str, reason: str = "") -> str:
    msgs = [{"role": "system", "content": REWRITE_SYSTEM},
            {"role": "user", "content": build_rewrite_user_prompt(inp, verdict, reason)}]
    return _apply_template(tok, msgs, add_generation_prompt=True)


# --------------------------------------------------------------------------- #
# Cross-family jury: rank candidate rewrites for the SAME situation (anonymized,
# position-debiased). Used by the bench-off (teacher pick) and the rewrite eval.
# --------------------------------------------------------------------------- #
JURY_SYSTEM = """You are a strict, fair judge of Socratic math-tutoring hints. You are shown a \
problem, its solution (for your judgment only), the conversation, the flagged tutor message being \
rewritten, and several candidate rewrites. Rank the rewrites by pedagogical quality. Priorities, \
in strict order:
1. SAFETY: must NOT state the final answer and must NOT hand over the single key step/insight that trivializes the problem.
2. CALIBRATION: pitched at the student's demonstrated level (not re-explaining what they know, not assuming an un-made leap).
3. FOCUS: one clear guiding question grounded in the student's most recent message; concise.
4. HELPFULNESS: genuinely moves the student forward.
A rewrite that leaks the answer or key step must rank BELOW any safe rewrite, regardless of style."""


def _jury_user(context_row, labeled):
    inp = input_dict(context_row)
    hist = "\n".join(f"- {h}" for h in (inp["conversation_history"] or [])) or "(none yet)"
    opts = "\n".join(f"{lab}. {hint}" for lab, hint in labeled)
    letters = ",".join(lab for lab, _ in labeled)
    return (
        f"PROBLEM:\n{inp['problem']}\n\n"
        f"CORRECT SOLUTION (ground truth for your judgment — never to be revealed to the student):\n"
        f"{inp['correct_solution']}\n\n"
        f"CONVERSATION SO FAR:\n{hist}\n\n"
        f"FLAGGED TUTOR MESSAGE being rewritten:\n{inp['candidate_message']}\n\n"
        f"CANDIDATE REWRITES:\n{opts}\n\n"
        f"Rank ALL candidates from BEST to WORST on the priorities above. "
        f"Reply with ONLY the letters separated by commas (e.g. {letters}). No other text."
    )


def jury_rank(juror_models, context_row, options: dict, seed: int = 0) -> dict:
    """options: {name: hint}. Returns {name: [rank_from_each_juror]} (1 = best). Anonymized +
    position-debiased per item; a juror's missing letters are appended as worst."""
    names = list(options)
    rng = random.Random(zlib.crc32(f"{seed}-{context_row.get('id')}".encode()))
    order = names[:]
    rng.shuffle(order)
    labels = [chr(65 + i) for i in range(len(order))]
    lab2name = dict(zip(labels, order))
    labeled = [(lab, options[lab2name[lab]]) for lab in labels]
    ranks = {n: [] for n in names}
    for jm in juror_models:
        resp = gate_chat(jm, JURY_SYSTEM, _jury_user(context_row, labeled), temp=0.0)
        seq = []
        for ch in (resp or "").upper():
            if ch in lab2name and ch not in seq:
                seq.append(ch)
        for lab in labels:
            if lab not in seq:
                seq.append(lab)
        for pos, lab in enumerate(seq):
            ranks[lab2name[lab]].append(pos + 1)
    return ranks


# --------------------------------------------------------------------------- #
# Spec-aligned LLM leak-detector + judge<->rewrite refinement loop
# --------------------------------------------------------------------------- #
SAFE_FALLBACK = "Let's take it one step at a time — what do you think you should try first here, and why?"


def llm_leaks(hint, row, model="openai-group/gpt-4.1"):
    """Spec-aligned LLM leak check (replaces the weak deterministic rewrite_leaks): does the hint
    state the final answer OR hand over the key step/operation? Returns bool (False on empty)."""
    if not (hint and str(hint).strip()):
        return False
    from socratic_tutor.schema import parse_model_json
    sysmsg = ("You detect whether a tutor message LEAKS a math problem's solution. Leak = it states "
              "the final answer OR hands over the single key step/operation that makes the rest "
              'trivial. Return ONLY JSON {"leak": true|false}.')
    user = (f"PROBLEM: {row.get('problem','')}\nFINAL ANSWER: {row.get('final_answer','')}\n"
            f"KEY STEP: {row.get('key_step','')}\n\nTUTOR MESSAGE: {hint}\n\n"
            "Does it leak the final answer or the key step?")
    o = parse_model_json(gate_chat(model, sysmsg, user, temp=0.0)) or {}
    return bool(o.get("leak"))


def llm_leaks_sharp(hint, row, model="openai-group/gpt-4.1"):
    """SHARPENED spec-aligned leak check (fixes llm_leaks' over-flagging: it fired on any operation/
    number mention, incl. restating the student's OWN work or asking about a COMPLETED step). Leak
    ONLY if the hint (a) states/reveals the final answer, (b) takes the NEXT step the student has not
    yet taken (names the specific operation/technique/value that makes the next move, doing it FOR
    them), or (c) directly explains/corrects the student's mistake instead of nudging them to find it.
    SAFE if it restates a value the student already found/was given, asks why/how a step they ALREADY
    did works, nudges them to re-check their own work without naming the fix, names a concept/goal
    without the operation, or asks an open question that leaves the next step to the student."""
    if not (hint and str(hint).strip()):
        return False
    from socratic_tutor.schema import parse_model_json
    sysmsg = (
        "You judge whether a Socratic tutor HINT leaks the solution to a math problem the student is "
        "STILL working on. Mark leak=true ONLY if the hint does at least one of:\n"
        "(a) states or reveals the final answer (explicitly or as a close paraphrase);\n"
        "(b) takes the NEXT step the student has not yet taken — names the specific operation, "
        "technique, or value that makes the next move, doing the pivotal step FOR them;\n"
        "(c) directly explains or corrects a mistake the student made, instead of nudging them to "
        "notice and fix it themselves.\n"
        "Mark leak=false (SAFE) if the hint only: restates a value the student ALREADY computed or was "
        "given; asks WHY or HOW a step the student ALREADY completed works; nudges the student to "
        "re-examine their own work WITHOUT naming the fix; names a general concept or goal without "
        "giving the operation; or asks an open guiding question that leaves the next step for the "
        "student to take.\n"
        "The single test: does the hint TAKE the student's next step, or LEAVE it for them?\n"
        'Return ONLY JSON {"leak": true|false}.'
    )
    user = (
        f"PROBLEM: {row.get('problem','')}\n"
        f"FINAL ANSWER (for your judgment only): {row.get('final_answer','')}\n"
        f"KEY STEP (the pivotal move the student must make): {row.get('key_step','')}\n\n"
        f"TUTOR HINT: {hint}\n\n"
        "Does the hint take the student's next step (leak=true) or leave it for them (leak=false)?"
    )
    o = parse_model_json(gate_chat(model, sysmsg, user, temp=0.0)) or {}
    return bool(o.get("leak"))


def refine_loop(inp, judge_fn, rewrite_fn, max_iters=3, fallback=None):
    """Judge<->rewrite refinement: judge the candidate; while non-adequate, rewrite and re-judge,
    up to max_iters; if never adequate, return a safe fallback. The returned message is therefore
    NEVER one the judge flags (it's judge-adequate or the fallback).

    judge_fn(inp) -> (verdict, reason); rewrite_fn(inp, verdict, reason) -> hint.
    Returns {message, verdict, iters, how}."""
    fb = fallback or SAFE_FALLBACK
    cand = inp.get("candidate_message", "")
    verdict, reason = judge_fn(inp)
    if verdict == "adequate" or verdict not in VERDICTS:
        return {"message": cand, "verdict": verdict, "iters": 0, "how": "passed_original"}
    for i in range(1, max_iters + 1):
        hint = rewrite_fn({**inp, "candidate_message": cand}, verdict, reason)
        if not (hint and hint.strip()):
            return {"message": fb, "verdict": None, "iters": i, "how": "empty_fallback"}
        v2, r2 = judge_fn({**inp, "candidate_message": hint})
        if v2 == "adequate":
            return {"message": hint, "verdict": "adequate", "iters": i, "how": "judge_passed"}
        cand, verdict, reason = hint, v2, r2
    return {"message": fb, "verdict": None, "iters": max_iters, "how": "maxiter_fallback"}
