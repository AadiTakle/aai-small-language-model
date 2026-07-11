"""Task 2 generation: bench-off frontier rewriters -> pick winner -> distill full target set.

Phase A (bench-off): sample real flagged contexts, generate a rewrite from each candidate teacher
(Opus-4.8 / GPT-5.6 / GPT-5.5), and have a cross-family jury rank them (anonymized). Lowest mean
rank wins; leak rate is a tiebreaker/guard.

Phase B (distill): the winning teacher generates a rewrite target for every train context. GSM8K
needs_synth contexts first get a synthesized flawed candidate + verdict. Leaky targets are dropped.
Writes are chunk-checkpointed so a mid-run failure keeps progress.

Usage:
  python scripts/overnight/gen_rewrites.py --bench-n 30 --out data/raw/rewrite_train.jsonl \
      --winner-out eval/results/overnight/benchoff.json
  python scripts/overnight/gen_rewrites.py --winner opus-4.8   # skip bench-off, force teacher
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.schema import parse_model_json  # noqa: E402
from overnight.split_common import (  # noqa: E402
    FRONTIER, REWRITE_SYSTEM, build_rewrite_user_prompt, clean_hint, gate_chat, input_dict,
    jury_rank, parallel_map, rewrite_leaks,
)

CANDIDATES = ["opus-4.8", "gpt-5.6", "gpt-5.5"]           # bench-off teachers
JURORS = ["gpt-5.6-luna", "sonnet-5"]                    # cross-family; not exact bench candidates
FLAWED = ["gives_final_answer", "gives_away_key_step", "mismatched_calibration", "vague_unhelpful"]

SYNTH_SYS = ("You simulate a realistic K-12 math tutoring exchange to build ONE training example. "
             "You never reveal the solution to the student.")


def rewrite_one(model_id: str, ctx: dict, temp: float = 0.4) -> str:
    inp = input_dict(ctx)
    verdict, reason = ctx.get("verdict") or "", ctx.get("reason") or ""
    hint = clean_hint(gate_chat(model_id, REWRITE_SYSTEM, build_rewrite_user_prompt(inp, verdict, reason), temp=temp))
    if hint and rewrite_leaks(hint, ctx):  # one stricter retry
        strict = build_rewrite_user_prompt(inp, verdict,
                                            (reason + " CRITICAL: your hint must not mention the final "
                                             "answer or the key step in any form.").strip())
        h2 = clean_hint(gate_chat(model_id, REWRITE_SYSTEM, strict, temp=0.2))
        return h2 or hint
    return hint


def synth_context(model_id: str, ctx: dict) -> dict | None:
    """Fill a bare (GSM8K) context with a synthesized flawed candidate + verdict."""
    rng = random.Random(zlib_seed(ctx.get("id")))
    tv = rng.choice(FLAWED)
    user = (f"PROBLEM:\n{ctx['problem']}\n\nCORRECT SOLUTION (never reveal to the student):\n"
            f"{ctx['correct_solution']}\n\nWrite a SHORT realistic exchange (1-2 'Student:' turns) then a "
            f"single flawed tutor message that clearly exemplifies the category \"{tv}\".\n"
            f'Return ONLY JSON: {{"conversation_history":["Student: ..."],"candidate_message":"...",'
            f'"reason":"one sentence: why it is {tv}"}}')
    o = parse_model_json(gate_chat(model_id, SYNTH_SYS, user, temp=0.7))
    if not o or not (o.get("candidate_message") or "").strip():
        return None
    c = dict(ctx)
    c["conversation_history"] = o.get("conversation_history") or []
    c["candidate_message"] = o["candidate_message"]
    c["verdict"] = tv
    c["reason"] = o.get("reason", "")
    c["needs_synth"] = False
    return c


def zlib_seed(x):
    import zlib
    return zlib.crc32(str(x).encode())


def bench_off(sample, out_path):
    print(f"[bench] generating rewrites from {CANDIDATES} on {len(sample)} contexts ...", file=sys.stderr)
    gens = {}
    for m in CANDIDATES:
        hints = parallel_map(lambda c, mm=m: rewrite_one(FRONTIER[mm], c), sample, workers=6)
        gens[m] = {c["id"]: (h or "") for c, h in zip(sample, hints)}
        got = sum(1 for v in gens[m].values() if v)
        print(f"[bench]   {m}: {got}/{len(sample)} non-empty", file=sys.stderr)

    def judge(c):
        opts = {m: gens[m][c["id"]] for m in CANDIDATES if gens[m][c["id"]]}
        return jury_rank([FRONTIER[j] for j in JURORS], c, opts) if len(opts) >= 2 else None

    print(f"[bench] jury ranking ({JURORS}) ...", file=sys.stderr)
    ranks = parallel_map(judge, sample, workers=6)
    agg = {m: [] for m in CANDIDATES}
    for r in ranks:
        if r:
            for m, rk in r.items():
                agg[m] += rk
    leaks = {m: sum(1 for c in sample if gens[m][c["id"]] and rewrite_leaks(gens[m][c["id"]], c)) for m in CANDIDATES}
    mean_rank = {m: (round(sum(agg[m]) / len(agg[m]), 3) if agg[m] else 9.9) for m in CANDIDATES}
    winner = min(CANDIDATES, key=lambda m: (mean_rank[m], leaks[m]))
    payload = {"candidates": CANDIDATES, "jurors": JURORS, "n": len(sample),
               "mean_rank": mean_rank, "leaks": leaks, "winner": winner}
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[bench] mean_rank={mean_rank}  leaks={leaks}  ->  WINNER = {winner}", file=sys.stderr)
    return winner


def distill(winner, contexts, out_path, chunk=150):
    mid = FRONTIER[winner]
    need = [c for c in contexts if c.get("needs_synth")]
    ready = [c for c in contexts if not c.get("needs_synth")]
    if need:
        print(f"[distill] synthesizing {len(need)} GSM8K contexts via {winner} ...", file=sys.stderr)
        synthed = parallel_map(lambda c: synth_context(mid, c), need, workers=6)
        ready += [s for s in synthed if s]
    print(f"[distill] generating targets for {len(ready)} contexts via {winner} (chunk={chunk}) ...", file=sys.stderr)
    rows, kept, dropped = [], 0, 0
    for i in range(0, len(ready), chunk):
        part = ready[i:i + chunk]
        hints = parallel_map(lambda c: rewrite_one(mid, c), part, workers=6)
        for c, h in zip(part, hints):
            if not (h and h.strip()) or rewrite_leaks(h, c):
                dropped += 1
                continue
            rows.append({**{k: c[k] for k in ("id", "source", "problem", "correct_solution",
                                              "final_answer", "key_step", "conversation_history",
                                              "candidate_message", "verdict", "reason")},
                         "target_rewrite": h.strip(), "teacher": winner})
            kept += 1
        write_jsonl(out_path, rows)  # checkpoint after each chunk
        print(f"[distill]   {min(i + chunk, len(ready))}/{len(ready)}  kept={kept} dropped={dropped}", file=sys.stderr, flush=True)
    print(f"[distill] DONE kept={kept} dropped(leak/empty)={dropped} -> {out_path}", file=sys.stderr)
    return kept


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contexts", default="data/raw/rewrite_contexts_train.jsonl")
    ap.add_argument("--out", default="data/raw/rewrite_train.jsonl")
    ap.add_argument("--winner-out", default="eval/results/overnight/benchoff.json")
    ap.add_argument("--bench-n", type=int, default=30)
    ap.add_argument("--winner", default=None, help="skip bench-off, force this teacher key")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    contexts = read_jsonl(a.contexts)
    real = [c for c in contexts if not c.get("needs_synth") and c.get("candidate_message")]

    if a.winner:
        winner = a.winner
        print(f"[gen] winner forced = {winner} (bench-off skipped)", file=sys.stderr)
    else:
        rng = random.Random(a.seed)
        sample = rng.sample(real, min(a.bench_n, len(real)))
        winner = bench_off(sample, a.winner_out)

    distill(winner, contexts, a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
