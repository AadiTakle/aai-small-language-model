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
import time
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
FEED_PATH = REPO / "data" / "raw" / "rewrite_feed.jsonl"          # curation queue (built by build_feed.py)
HUMAN_REWRITES = REPO / "data" / "raw" / "human_rewrites.jsonl"   # curated gold rewrites (append-only)
BOUNDARY_PATH = REPO / "data" / "raw" / "boundary_pairs.jsonl"    # leaky/safe minimal pairs (gen_boundary.py)
HUMAN_BOUNDARY = REPO / "data" / "raw" / "human_boundary.jsonl"   # curated pair decisions (append-only)
THINK_RE = re.compile(r"<think>.*?</think>", re.S)

# Corrective-framed leaks are the judge's known failure mode: a leak dressed as feedback
# ("not quite — you should…") reads adequate. Surface those first in the boundary feed.
CORRECTIVE_CUES = ("not quite", "you're close", "you are close", "actually", "remember",
                   "should be", "the mistake", "you made", "incorrect", "wrong",
                   "instead of", "you forgot")

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


def _gate_chat(model, sysmsg, usermsg, temp=0.0, tries=2):
    """One gateway chat call. Tries with `temperature`, then without (Claude / gpt-5.5 deprecate it) and
    remembers temp-rejecting models; plus a light retry, since the gateway occasionally 400s a valid
    model ('invalid model ID') on a transient blip and the SDK won't retry a 400. Raises the REAL error
    only after all rounds fail — callers surface that instead of a silent placeholder."""
    client = _client()
    msgs = [{"role": "system", "content": sysmsg}, {"role": "user", "content": usermsg}]
    last = "no response"
    for attempt in range(max(1, tries)):
        for kw in ([{}] if model in _no_temp else [{"temperature": temp}, {}]):
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
        if attempt + 1 < tries:
            time.sleep(1.0)  # transient gateway hiccup — one more round before giving up
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
    p = CONTRIB_PATH
    return {"ok": True, "path": str(p.relative_to(REPO) if p.is_relative_to(REPO) else p)}


# --------------------------------------------------------------------------- #
# Rewrite-curation feed: serve fuzziest-first items from rewrite_feed.jsonl,
# skipping ones already reviewed into human_rewrites.jsonl.
# --------------------------------------------------------------------------- #
def _reviewed_ids():
    if not HUMAN_REWRITES.exists():
        return set()
    ids = set()
    for line in open(HUMAN_REWRITES):
        line = line.strip()
        if line:
            try:
                ids.add(json.loads(line).get("id"))
            except Exception:  # noqa: BLE001
                pass
    return ids


def curate_next(count=1):
    """Next unreviewed feed item(s), fuzziest-first (the feed file is pre-sorted)."""
    if not FEED_PATH.exists():
        return {"ready": False, "items": [], "total": 0, "reviewed": 0, "remaining": 0, "has_slm": False}
    feed = [json.loads(l) for l in open(FEED_PATH) if l.strip()]
    done = _reviewed_ids()
    remaining = [r for r in feed if r.get("id") not in done]
    return {"ready": True, "items": remaining[:max(1, count)], "total": len(feed),
            "reviewed": len(feed) - len(remaining), "remaining": len(remaining),
            "has_slm": any(r.get("slm_rewrite") for r in feed[:20])}


def curate_submit(rec):
    HUMAN_REWRITES.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec)
    rec["mode"] = "rewrite_curation"
    rec["ts"] = time.time()
    with open(HUMAN_REWRITES, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"ok": True, "reviewed": len(_reviewed_ids())}


# --------------------------------------------------------------------------- #
# Boundary-pair curation feed: serve leaky/safe minimal pairs from
# boundary_pairs.jsonl side by side, corrective-framed leaks first, skipping
# ones already reviewed into human_boundary.jsonl.
# --------------------------------------------------------------------------- #
def _boundary_reviewed_ids():
    if not HUMAN_BOUNDARY.exists():
        return set()
    ids = set()
    for line in open(HUMAN_BOUNDARY):
        line = line.strip()
        if line:
            try:
                ids.add(json.loads(line).get("id"))
            except Exception:  # noqa: BLE001
                pass
    return ids


def _has_corrective_cue(text):
    t = (text or "").lower()
    return any(c in t for c in CORRECTIVE_CUES)


def boundary_next(count=1):
    """Next unreviewed pair(s), corrective-framed leaks first (they're the judge's blind spot)."""
    if not BOUNDARY_PATH.exists():
        return {"ready": False, "items": [], "total": 0, "reviewed": 0, "remaining": 0}
    pairs = [json.loads(l) for l in open(BOUNDARY_PATH) if l.strip()]
    done = _boundary_reviewed_ids()
    remaining = [r for r in pairs if r.get("id") not in done]
    # stable sort: cue rows before non-cue rows, original order preserved within each group
    remaining.sort(key=lambda r: not _has_corrective_cue(r.get("leaky_candidate")))
    return {"ready": True, "items": remaining[:max(1, count)], "total": len(pairs),
            "reviewed": len(pairs) - len(remaining), "remaining": len(remaining)}


def boundary_submit(rec):
    HUMAN_BOUNDARY.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec)
    rec["mode"] = "boundary_curation"
    rec["ts"] = time.time()
    with open(HUMAN_BOUNDARY, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"ok": True, "reviewed": len(_boundary_reviewed_ids())}
