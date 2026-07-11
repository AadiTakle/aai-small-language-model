"""FastAPI app for the Socratic Tutor Explorer. Serves the static frontend at / and a small JSON API.

Endpoints:
  GET  /api/models        -> {judges:[...], tutors:[...]}   (drives every dropdown + the compare suite)
  POST /api/tutor         -> a frontier LLM plays the Socratic tutor -> next candidate message
  POST /api/judge_suite   -> grade a candidate with every (or a subset of) registry judge
  POST /api/contribute    -> append a human-approved datapoint to data/raw/human_contributions.jsonl
"""

import sys
import time
from pathlib import Path

WEBUI = Path(__file__).resolve().parent
sys.path.insert(0, str(WEBUI))

from fastapi import FastAPI  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import engine  # noqa: E402

app = FastAPI(title="Socratic Tutor Explorer")


class SuiteReq(BaseModel):
    problem: str = ""
    solution: str = ""
    conversation: list[str] = []
    candidate: str = ""
    models: list[str] | None = None


class TutorReq(BaseModel):
    tutor: str
    problem: str = ""
    solution: str = ""
    conversation: list[str] = []


class ContribReq(BaseModel):
    problem: str = ""
    solution: str = ""
    final_answer: str = ""
    key_step: str = ""
    conversation: list[str] = []
    candidate_message: str = ""
    verdict: str = ""
    reasoning: str = ""
    rewritten_message: str | None = None
    source_model: str = ""
    ranked_over: list[str] = []
    slm_verdict: str = ""      # what the SLM said (Tutor Session) — provenance vs the human label
    slm_rewrite: str | None = None  # what the SLM/model proposed as a rewrite — provenance vs the human rewrite
    mode: str = ""             # "tutor_session" | "compare"


@app.get("/api/health")
def health():
    import os
    base = os.environ.get("OPENAI_BASE_URL", "")
    return {"gateway_base_url": base or None,
            "gateway_configured": bool(base) and "openai.com" not in base}


@app.get("/api/models")
def models():
    return {"judges": engine.judges(), "tutors": engine.tutors()}


@app.post("/api/tutor")
def tutor(r: TutorReq):
    return engine.tutor_turn(r.tutor, r.problem, r.solution, r.conversation)


@app.post("/api/judge_suite")
def judge_suite(r: SuiteReq):
    return {"results": engine.judge_suite(r.problem, r.solution, r.conversation, r.candidate, r.models)}


@app.post("/api/contribute")
def contribute(r: ContribReq):
    rec = r.model_dump()
    rec["conversation_history"] = rec.pop("conversation")
    rec["human_edited"] = True
    rec["source"] = "webui_human_contribution"
    rec["ts"] = time.time()
    return engine.contribute(rec)


# Static frontend at / (registered last so /api/* takes precedence).
app.mount("/", StaticFiles(directory=str(WEBUI / "frontend"), html=True), name="frontend")
