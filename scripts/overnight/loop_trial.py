"""TRY the judge<->rewrite refinement loop (user's idea): judge a candidate, rewrite, RE-JUDGE the
rewrite, repeat until the judge passes it (adequate) or max_iters -> safe fallback.

Compares single-pass rewrite_v2 vs the loop on the held-out contexts, both measured by the
spec-aligned LLM leak-detector (gpt-4.1). Loop verifier = v9 (the ship judge). Ceiling: the loop
can only remove leaks v9 itself detects — residual = v9's blind spots (operation-naming it misses).

Usage: python scripts/overnight/loop_trial.py --max-iters 3 --out eval/results/overnight/loop_trial.json
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl  # noqa: E402
from socratic_tutor.prompts import build_inference_prompt  # noqa: E402
from socratic_tutor.schema import parse_model_json  # noqa: E402
from overnight.split_common import (  # noqa: E402
    clean_hint, infer_rewrite_prompt, input_dict, llm_leaks, parallel_map, refine_loop,
)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contexts", default="data/raw/rewrite_contexts_eval.jsonl")
    ap.add_argument("--max-iters", type=int, default=3)
    ap.add_argument("--out", default="eval/results/overnight/loop_trial.json")
    a = ap.parse_args()

    ctxs = read_jsonl(a.contexts)
    print(f"[loop-trial] {len(ctxs)} held-out contexts | loading v9 + rewrite_v2 ...", file=sys.stderr)
    from mlx_lm import generate, load
    from mlx_lm.sample_utils import make_sampler
    v9_m, v9_t = load(config.MODEL, adapter_path="adapters/v9")
    rw_m, rw_t = load(config.MODEL, adapter_path="adapters/rewrite_v2")
    samp = make_sampler(temp=0.0)

    def _gen(m, t, prompt, mt):
        return generate(m, t, prompt=prompt, max_tokens=mt, sampler=samp, verbose=False)

    def judge_fn(inp):
        jr = parse_model_json(_gen(v9_m, v9_t, build_inference_prompt(v9_t, inp), 256)) or {}
        return jr.get("verdict"), jr.get("reasoning", "")

    def rewrite_fn(inp, verdict, reason):
        return clean_hint(_gen(rw_m, rw_t, infer_rewrite_prompt(rw_t, inp, verdict, reason), 160))

    singles, loops, metas = [], [], []
    for i, c in enumerate(ctxs, 1):
        inp = input_dict(c)
        singles.append(rewrite_fn(inp, c.get("verdict", ""), c.get("reason", "")))
        res = refine_loop(inp, judge_fn, rewrite_fn, max_iters=a.max_iters)
        loops.append(res["message"])
        metas.append(res)
        if i % 10 == 0 or i == len(ctxs):
            print(f"[loop-trial] {i}/{len(ctxs)} (iters={res['iters']} how={res['how']})", file=sys.stderr, flush=True)

    print("[loop-trial] scoring LLM-leak (gpt-4.1) for single-pass vs loop ...", file=sys.stderr)
    sl = parallel_map(lambda p: llm_leaks(p[0], p[1]), list(zip(singles, ctxs)), workers=6)
    ll = parallel_map(lambda p: llm_leaks(p[0], p[1]), list(zip(loops, ctxs)), workers=6)
    n = len(ctxs)
    single_leak = sum(1 for x in sl if x)
    loop_leak = sum(1 for x in ll if x)
    out = {"n": n, "max_iters": a.max_iters,
           "single_pass_leak": single_leak, "single_pass_leak_pct": round(100 * single_leak / n, 1),
           "loop_leak": loop_leak, "loop_leak_pct": round(100 * loop_leak / n, 1),
           "loop_mean_iters": round(st.mean([m["iters"] for m in metas]), 2),
           "loop_how": dict(Counter(m["how"] for m in metas))}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=2)
    print(f"\nsingle-pass rewrite_v2 LLM-leak : {single_leak}/{n} = {out['single_pass_leak_pct']}%")
    print(f"judge<->rewrite LOOP LLM-leak   : {loop_leak}/{n} = {out['loop_leak_pct']}%")
    print(f"loop mean iters: {out['loop_mean_iters']} | how: {out['loop_how']}")
    print(f"[loop-trial] wrote {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
