#!/usr/bin/env python3
"""Launch the Socratic Tutor Explorer.  ->  http://127.0.0.1:8000

    python webui/run.py            # from the repo root, inside the project venv
    python webui/run.py --port 8010

Needs: fastapi + uvicorn (pip install fastapi uvicorn). Reuses the project's socratic_tutor package
and the local adapters/ dir, and reads the gateway creds from the environment (same as the evals).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    import uvicorn
    print(f"\n  Socratic Tutor Explorer  ->  http://{a.host}:{a.port}\n", file=sys.stderr)
    uvicorn.run("server:app", host=a.host, port=a.port, reload=False)
