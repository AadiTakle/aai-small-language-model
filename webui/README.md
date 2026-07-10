# Socratic Tutor Explorer

A small local web UI to query the tutor SLMs (v6/v9/…) and frontier LLMs, watch the
LLM-tutors-→-SLM-guards pipeline live, and contribute human-labeled datapoints. Side project — off
the project spec; isolated in this `webui/` folder, reuses the repo's `socratic_tutor` package and
the local `adapters/`.

## Launch
```bash
# from the repo root, inside the project venv:
pip install fastapi uvicorn          # one-time
python webui/run.py                  # -> http://127.0.0.1:8000   (use --port to change)
```
Requirements: the gateway env vars the evals already use (`OPENAI_BASE_URL`, `OPENAI_API_KEY`,
`ANTHROPIC_*`) for the frontier models, and the trained adapters present under `adapters/`
(they're gitignored, so they live only on the machine that trained them).

## Two tabs
- **Tutor Session** — fill in the problem setup, pick a tutor LLM + a judge SLM, then chat as the
  *student*. Each turn: the tutor LLM (prompt-engineered to be Socratic) writes a reply → the judge
  SLM grades it → the message shown to the student is the SLM's **safe rewrite** whenever the tutor
  leaks. You watch the guardrail work in real time.
- **Compare & Label** — provide the full input + a candidate message; **every model in the suite**
  (SLM versions + frontier LLMs) grades it side by side. Star a favorite, rank the rest, then edit the
  favorite's verdict/reasoning/rewrite and **add it to the dataset** as a human-approved datapoint
  (appended to `data/raw/human_contributions.jsonl` — kept separate from training data; fold it in
  deliberately later).

## Expanding the suite
Everything is driven by **`webui/models.json`** — the single expansion point. Add a new SLM version or
LLM by appending one entry:
```json
{"id": "v10", "label": "SLM v10", "kind": "mlx", "adapter": "adapters/v10", "max_tokens": 512}
{"id": "gemini", "label": "Gemini 2.5", "kind": "gateway", "model": "google-group/gemini-2.5-pro"}
```
`judges` = anything that grades a candidate (SLMs + frontier). `tutors` = frontier models that can
play the Socratic tutor in Tab 1. New entries appear automatically in the dropdowns and the compare
grid — no code change. MLX models are lazy-loaded + cached (first query per model ~10s, then fast);
a registered SLM whose adapter isn't trained yet shows "not trained yet" instead of crashing.

## Architecture
`run.py` → `server.py` (FastAPI: serves `frontend/` + a small JSON API) → `engine.py` (registry,
lazy MLX cache, gateway client, judge/tutor/contribute). The judge path reuses the exact
`socratic_tutor` prompts + `parse_model_json` the offline evals use, so the UI grades identically.
