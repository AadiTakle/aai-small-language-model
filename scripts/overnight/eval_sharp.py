"""Honest leak re-measure (Phase 1): base / rewrite_v3 / rewrite_v4 + frontier, on the held-out 60,
under BOTH detectors — the BROAD one (llm_leaks: fires on any operation/number mention) and the
SHARPENED one (llm_leaks_sharp: leak only if the hint STATES the answer, TAKES the student's next
unsolved step, or directly CORRECTS their error without nudging; SAFE if it restates the student's
own work / asks about a completed step). Shows honest absolutes + the broad-vs-sharp over-flag gap.

Usage:
  python scripts/overnight/eval_sharp.py --out eval/results/overnight/eval_sharp
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from socratic_tutor.io_utils import read_jsonl  # noqa: E402
from overnight.split_common import llm_leaks, llm_leaks_sharp, parallel_map  # noqa: E402
from overnight.eval_rewrite import mlx_hints, teacher_hints  # noqa: E402

FRONTIER_BENCH = {
    "gpt-4o": "openai-group/gpt-4o",
    "gpt-4.1": "openai-group/gpt-4.1",
    "sonnet-5": "claude-group/claude-sonnet-5",
    "gpt-5.6": "openai-group/gpt-5.6-sol",
    "opus-4.8": "claude-group/claude-opus-4-8",
    "gpt-5.5": "openai-group/gpt-5.5",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contexts", default="data/raw/rewrite_contexts_eval.jsonl")
    ap.add_argument("--adapters", default="rewrite_v3:adapters/rewrite_v3,rewrite_v4:adapters/rewrite_v4")
    ap.add_argument("--frontier", default="gpt-4o,gpt-4.1,sonnet-5,gpt-5.6")
    ap.add_argument("--out", default="eval/results/overnight/eval_sharp")
    a = ap.parse_args()

    ctxs = read_jsonl(a.contexts)
    print(f"[eval-sharp] {len(ctxs)} held-out contexts", file=sys.stderr, flush=True)

    hints = {}
    print("[eval-sharp] base (MLX) ...", file=sys.stderr, flush=True)
    hints["base"] = mlx_hints(None, ctxs)
    for spec in [s for s in a.adapters.split(",") if s.strip()]:
        name, _, path = spec.partition(":")
        name, path = name.strip(), (path.strip() or f"adapters/{name.strip()}")
        if (REPO / path).exists():
            print(f"[eval-sharp] {name} (MLX {path}) ...", file=sys.stderr, flush=True)
            hints[name] = mlx_hints(path, ctxs)
        else:
            print(f"[eval-sharp] SKIP {name}: {path} missing", file=sys.stderr, flush=True)
    for name in [f.strip() for f in a.frontier.split(",") if f.strip()]:
        mid = FRONTIER_BENCH.get(name)
        if not mid:
            continue
        print(f"[eval-sharp] frontier {name} (gateway) ...", file=sys.stderr, flush=True)
        hints[name] = teacher_hints(mid, ctxs)

    def measure(ch):
        c, h = ch
        if not h:
            return (False, False)
        return (bool(llm_leaks(h, c)), bool(llm_leaks_sharp(h, c)))

    rows = []
    for name, hd in hints.items():
        hs = [(c, hd.get(c["id"], "")) for c in ctxs]
        res = parallel_map(measure, hs, workers=6)
        n = len(ctxs)
        broad = sum(1 for b, s in res if b) / n
        sharp = sum(1 for b, s in res if s) / n
        rows.append({"model": name, "broad": round(broad, 3), "sharp": round(sharp, 3), "n": n})
        print(f"[eval-sharp]   {name}: broad={broad:.1%} sharp={sharp:.1%}", file=sys.stderr, flush=True)

    lines = [f"# Honest leak re-measure (held-out n={len(ctxs)}) — broad vs sharpened detector",
             "_broad = llm_leaks (fires on any operation/number mention); sharp = llm_leaks_sharp "
             "(leak only if it states the answer / takes the next step / corrects an error w/o nudging)._",
             "", "| model | broad leak | sharp leak | over-flag gap |", "|---|---|---|---|"]
    for r in rows:
        gap = r["broad"] - r["sharp"]
        lines.append(f"| {r['model']} | {r['broad']:.1%} | {r['sharp']:.1%} | {gap:+.1%} |")
    md = "\n".join(lines) + "\n"
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out + ".md").write_text(md, encoding="utf-8")
    Path(a.out + ".json").write_text(json.dumps({"rows": rows, "raw_hints": hints}, indent=2), encoding="utf-8")
    print(md)
    print(f"[eval-sharp] wrote {a.out}.md/.json", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
