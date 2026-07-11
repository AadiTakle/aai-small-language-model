"""Task 2 eval: rewrite quality on held-out contexts for base / rewrite_v1 / teacher(frontier).

Each contestant generates a hint for the same held-out flagged contexts; a cross-family jury
(two strong models, chosen to EXCLUDE the winning teacher's own model) ranks the anonymized hints.
Reports mean jury rank, win-rate of rewrite_v1 vs teacher and vs base, plus deterministic
leak-rate and mean length. Quality (jury) + safety (leak) + concision (length) together.

Usage:
  python scripts/overnight/eval_rewrite.py --out eval/results/overnight/rewrite_eval
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl  # noqa: E402
from overnight.split_common import (  # noqa: E402
    FRONTIER, REWRITE_SYSTEM, build_rewrite_user_prompt, clean_hint, gate_chat, infer_rewrite_prompt,
    input_dict, jury_rank, parallel_map, rewrite_leaks,
)


def mlx_hints(adapter, ctxs, max_tokens=128):
    from mlx_lm import generate, load
    from mlx_lm.sample_utils import make_sampler
    model, tok = load(config.MODEL, adapter_path=adapter)
    sampler = make_sampler(temp=0.0)
    out = {}
    for c in ctxs:
        prompt = infer_rewrite_prompt(tok, input_dict(c), c.get("verdict") or "", c.get("reason") or "")
        raw = generate(model, tok, prompt=prompt, max_tokens=max_tokens, sampler=sampler, verbose=False)
        out[c["id"]] = clean_hint(raw)
    return out


def teacher_hints(model_id, ctxs):
    def one(c):
        return (c["id"], clean_hint(gate_chat(model_id, REWRITE_SYSTEM,
                build_rewrite_user_prompt(input_dict(c), c.get("verdict") or "", c.get("reason") or ""), temp=0.3)))
    return {k: v for k, v in parallel_map(one, ctxs, workers=6) if k}


def pick_jurors(winner_id):
    claude_j = FRONTIER["opus-4.8"] if winner_id != FRONTIER["opus-4.8"] else FRONTIER["sonnet-5"]
    openai_j = FRONTIER["gpt-5.6"] if winner_id != FRONTIER["gpt-5.6"] else FRONTIER["gpt-5.5"]
    return [claude_j, openai_j]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contexts", default="data/raw/rewrite_contexts_eval.jsonl")
    ap.add_argument("--benchoff", default="eval/results/overnight/benchoff.json")
    ap.add_argument("--winner", default=None)
    ap.add_argument("--adapter", default="adapters/rewrite_v1")
    ap.add_argument("--out", default="eval/results/overnight/rewrite_eval")
    a = ap.parse_args()

    winner = a.winner
    if not winner and Path(a.benchoff).exists():
        winner = json.loads(Path(a.benchoff).read_text()).get("winner")
    winner = winner or "opus-4.8"
    winner_id = FRONTIER[winner]
    jurors = pick_jurors(winner_id)
    ctxs = read_jsonl(a.contexts)
    print(f"[eval-rewrite] {len(ctxs)} held-out contexts | teacher={winner} | jurors={jurors}", file=sys.stderr)

    hints = {}
    print("[eval-rewrite] base (MLX) ...", file=sys.stderr)
    hints["base"] = mlx_hints(None, ctxs)
    if (REPO / a.adapter).exists():
        print("[eval-rewrite] rewrite_v1 (MLX) ...", file=sys.stderr)
        hints["rewrite_v1"] = mlx_hints(a.adapter, ctxs)
    else:
        print(f"[eval-rewrite] SKIP rewrite_v1: {a.adapter} missing", file=sys.stderr)
    print(f"[eval-rewrite] teacher {winner} (gateway) ...", file=sys.stderr)
    hints[f"teacher:{winner}"] = teacher_hints(winner_id, ctxs)

    names = list(hints)
    ranks = {n: [] for n in names}
    item_ranks = {}  # id -> {name: mean-rank-over-jurors}

    def judge(c):
        opts = {n: hints[n].get(c["id"], "") for n in names if hints[n].get(c["id"], "")}
        return (c["id"], jury_rank(jurors, c, opts)) if len(opts) >= 2 else (c["id"], None)

    for cid, r in parallel_map(judge, ctxs, workers=6):
        if r:
            item_ranks[cid] = {n: sum(rk) / len(rk) for n, rk in r.items()}
            for n, rk in r.items():
                ranks[n] += rk

    tkey = f"teacher:{winner}"

    def winrate(a_name, b_name):
        both = [ir for ir in item_ranks.values() if a_name in ir and b_name in ir]
        if not both:
            return None
        score = sum((ir[a_name] < ir[b_name]) + 0.5 * (ir[a_name] == ir[b_name]) for ir in both)
        return round(score / len(both), 3)

    def summ(n):
        hs = [hints[n].get(c["id"], "") for c in ctxs]
        leak = sum(1 for c, h in zip(ctxs, hs) if h and rewrite_leaks(h, c))
        got = [h for h in hs if h]
        mean_len = sum(len(h.split()) for h in got) / len(got) if got else 0
        mr = sum(ranks[n]) / len(ranks[n]) if ranks[n] else None
        return {"mean_rank": round(mr, 3) if mr is not None else None,
                "leak_rate": round(leak / len(ctxs), 3), "mean_len_words": round(mean_len, 1),
                "n_hints": len(got), "winrate_vs_teacher": (winrate(n, tkey) if n != tkey else None)}

    stats = {n: summ(n) for n in names}
    lines = [f"# Task 2 — rewrite eval (held-out n={len(ctxs)}) | base={config.MODEL} | teacher={winner}",
             f"_jury (rank 1=best): {jurors}; win-rate = share of items ranked at least as good as the teacher._", "",
             "| model | mean jury rank | win-rate vs teacher | leak rate | mean length (words) | hints |",
             "|---|---|---|---|---|---|"]
    for n in names:
        s = stats[n]
        wr = "—" if s["winrate_vs_teacher"] is None else f"{s['winrate_vs_teacher']:.1%}"
        lines.append(f"| {n} | {s['mean_rank']} | {wr} | {s['leak_rate']:.1%} | {s['mean_len_words']} | {s['n_hints']}/{len(ctxs)} |")
    md = "\n".join(lines) + "\n"
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out + ".md").write_text(md, encoding="utf-8")
    Path(a.out + ".json").write_text(json.dumps({"winner": winner, "jurors": jurors, "stats": stats,
                                                  "raw_hints": hints}, indent=2), encoding="utf-8")
    print(md)
    print(f"[eval-rewrite] wrote {a.out}.md/.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
