"""Model registry + judge/tutor services for the Socratic Tutor Explorer.

Reuses the project's `socratic_tutor` package (prompts + schema) and the same MLX + gateway runners
the eval harness uses — so the UI grades a candidate identically to the offline evals. MLX models are
lazy-loaded and cached; gateway (frontier) calls go through the OpenAI-compatible TrueFoundry client.
Everything is driven by webui/models.json, which is the single expansion point for new SLMs/LLMs.
"""

import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parent
REPO = WEBUI_DIR.parent
sys.path.insert(0, str(REPO))

from socratic_tutor import config  # noqa: E402
from socratic_tutor.prompts import SYSTEM_PROMPT, build_user_prompt, build_inference_prompt  # noqa: E402
from socratic_tutor.schema import parse_model_json  # noqa: E402

REGISTRY = json.load(open(WEBUI_DIR / "models.json"))
CONTRIB_PATH = REPO / "data" / "raw" / "human_contributions.jsonl"
THINK_RE = re.compile(r"<think>.*?</think>", re.S)

_mlx_cache = {}
_mlx_lock = threading.RLock()  # reentrant: _mlx_generate holds it and calls _get_mlx which also locks
_no_temp = set()  # gateway models that reject the `temperature` param (Claude, gpt-5.5) — learned on 1st 400

TUTOR_SYS = (
    "You are an expert Socratic math tutor for a K-12 student. Guide the student toward the answer "
    "WITHOUT revealing it. Hard rules: never state the final answer, and never hand over the single "
    "pivotal step / insight / operation-choice that makes the rest trivial (not even via a worked "
    "isomorphic example). Ask ONE focused guiding question at a time, build on the student's most "
    "recent message, and calibrate to what they've already shown they understand. You are given the "
    "problem and its correct solution FOR YOUR REFERENCE ONLY — never reveal the solution. Reply with "
    "ONLY your next tutor message: no preamble, no meta-commentary, no labels."
)


def judges():
    return REGISTRY["judges"]


def tutors():
    return REGISTRY["tutors"]


def _input(problem, solution, conversation, candidate):
    return {"problem": problem, "correct_solution": solution,
            "conversation_history": conversation or [], "candidate_message": candidate}


def _client():
    from openai import OpenAI
    return OpenAI(timeout=90, max_retries=4)


def _gate_chat(model, sysmsg, usermsg, temp=0.0):
    """One gateway chat call. Tries with `temperature`, then without (Claude / gpt-5.5 deprecate it);
    remembers temp-rejecting models so we don't waste a 400 next time. Raises with the REAL error if
    it can't get non-empty text — callers surface that instead of a silent placeholder."""
    client = _client()
    msgs = [{"role": "system", "content": sysmsg}, {"role": "user", "content": usermsg}]
    attempts = [{}] if model in _no_temp else [{"temperature": temp}, {}]
    last = "no response"
    for kw in attempts:
        try:
            r = client.chat.completions.create(model=model, messages=msgs, **kw)
            txt = (r.choices[0].message.content or "").strip()
            if txt:
                return txt
            last = "gateway returned empty content"
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {str(e)[:200]}"
            if "temperature" in str(e).lower():
                _no_temp.add(model)  # deprecated/rejected — skip it next time
    raise RuntimeError(last)


def _get_mlx(adapter):
    key = adapter or "__base__"
    with _mlx_lock:
        if key not in _mlx_cache:
            from mlx_lm import load
            _mlx_cache[key] = load(config.MODEL, adapter_path=adapter)
        return _mlx_cache[key]


def _mlx_generate(adapter, inp, max_tokens):
    from mlx_lm import generate
    from mlx_lm.sample_utils import make_sampler
    model, tok = _get_mlx(adapter)
    prompt = build_inference_prompt(tok, inp)
    with _mlx_lock:  # serialize GPU use across requests
        return generate(model, tok, prompt=prompt, max_tokens=max_tokens,
                        sampler=make_sampler(temp=0.0), verbose=False)


def _judge_entry(entry, inp):
    """Grade one candidate with one model -> {model, label, verdict, reasoning, rewritten_message, error}."""
    try:
        if entry["kind"] == "mlx":
            adapter = entry.get("adapter")
            if adapter and not (REPO / adapter).exists():
                return {"model": entry["id"], "label": entry.get("label", entry["id"]),
                        "error": "adapter not found (this SLM version isn't trained yet)"}
            raw = _mlx_generate(adapter, inp, entry.get("max_tokens", 512))
        else:
            raw = _gate_chat(entry["model"], SYSTEM_PROMPT, build_user_prompt(inp))
        o = parse_model_json(THINK_RE.sub("", raw)) or {}
        return {"model": entry["id"], "label": entry.get("label", entry["id"]),
                "verdict": o.get("verdict"), "reasoning": o.get("reasoning", ""),
                "rewritten_message": o.get("rewritten_message")}
    except Exception as e:  # noqa: BLE001
        return {"model": entry["id"], "label": entry.get("label", entry["id"]),
                "error": f"{type(e).__name__}: {e}"}


def judge_suite(problem, solution, conversation, candidate, model_ids=None):
    """Grade the candidate with every registry judge (or a subset). Gateway in parallel, MLX serialized."""
    inp = _input(problem, solution, conversation, candidate)
    entries = [j for j in REGISTRY["judges"] if (model_ids is None or j["id"] in model_ids)]
    results = {}
    gw = [e for e in entries if e["kind"] == "gateway"]
    mlx = [e for e in entries if e["kind"] == "mlx"]
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(_judge_entry, e, inp): e["id"] for e in gw}
        for e in mlx:  # serialized — shared single GPU
            results[e["id"]] = _judge_entry(e, inp)
        for f in futs:
            results[futs[f]] = f.result()
    return [results[e["id"]] for e in entries]  # preserve registry order


def judge_one(model_id, problem, solution, conversation, candidate):
    entry = next((j for j in REGISTRY["judges"] if j["id"] == model_id), None)
    if not entry:
        return {"model": model_id, "error": "unknown model"}
    return _judge_entry(entry, _input(problem, solution, conversation, candidate))


def tutor_turn(tutor_id, problem, solution, conversation):
    """A frontier model plays the Socratic tutor -> its next message (the candidate to be judged)."""
    entry = next((t for t in REGISTRY["tutors"] if t["id"] == tutor_id), None)
    if not entry:
        return {"error": "unknown tutor"}
    convo = "\n".join(conversation) if conversation else "(none yet)"
    user = (f"PROBLEM:\n{problem}\n\nCORRECT SOLUTION (reference only — never reveal):\n{solution}\n\n"
            f"CONVERSATION SO FAR:\n{convo}\n\nYour next tutor message:")
    try:
        return {"candidate_message": _gate_chat(entry["model"], TUTOR_SYS, user, temp=0.7)}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def contribute(record):
    CONTRIB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONTRIB_PATH, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"ok": True, "path": str(CONTRIB_PATH.relative_to(REPO))}
