#!/usr/bin/env python3
"""Launch the Socratic Tutor Explorer.  ->  http://127.0.0.1:8000

    python webui/run.py            # from the repo root, inside the project venv
    python webui/run.py --port 8010

Needs: fastapi + uvicorn (pip install fastapi uvicorn). Reuses the project's socratic_tutor package
and the local adapters/ dir, and reads the gateway creds (OPENAI_BASE_URL / OPENAI_API_KEY /
OPENAI_JUDGE_MODEL) from the environment — same as the evals. If those aren't already exported,
they're loaded from webui/.env (preferred) or a repo-root .env — copy webui/.env.example to get
started. An already-exported shell always wins (setdefault), so this never overrides the eval env.
"""

import argparse
import os
import sys
from pathlib import Path

WEBUI = Path(__file__).resolve().parent
sys.path.insert(0, str(WEBUI))


def _load_env_files():
    """Zero-dependency .env loader (no python-dotenv needed). Reads KEY=VALUE lines from
    webui/.env then the repo-root .env, WITHOUT overriding anything already in the environment —
    so a shell that already has the gateway env (the eval shell) is untouched. Supports an
    `export ` prefix, # comments, blank lines, and single/double-quoted values."""
    for path in (WEBUI / ".env", WEBUI.parent / ".env"):
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip()
            if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
                val = val[1:-1]
            os.environ.setdefault(key, val)  # shell/eval env always wins


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    _load_env_files()
    import uvicorn
    base = os.environ.get("OPENAI_BASE_URL", "")
    print(f"\n  Socratic Tutor Explorer  ->  http://{a.host}:{a.port}", file=sys.stderr)
    if base and "openai.com" not in base:
        print(f"  gateway: {base}\n", file=sys.stderr)
    else:
        print("  ⚠  OPENAI_BASE_URL is NOT the gateway — tutor + frontier-judge calls will 400 with\n"
              "     'invalid model ID'. Copy webui/.env.example to webui/.env and fill it in, or launch\n"
              "     from the shell your evals use. (Local SLMs like v6 still work without it.)\n", file=sys.stderr)
    uvicorn.run("server:app", host=a.host, port=a.port, reload=False)
