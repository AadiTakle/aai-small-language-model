#!/usr/bin/env python
"""Autonomous gap-closing loop (LOCAL SFT), v2. Durable + halt-able + cumulative-anchor.

Per iteration it picks a MOVE (alternating):
  - ADD  : generate ~80 targeted examples for the weakest focus criterion, append to data.
  - PRUNE: independently re-judge a sample of the training data with gpt-4.1 and drop rows
           whose label the judge disagrees with (data-cleaning; never touches the eval set).
Then it retrains a candidate LoRA and scores it on the frozen leakage-checked set.

ACCEPT iff (vs the FIXED original v4 anchor — cumulative, not vs running best):
  focus criterion improves (paired 95% CI excludes 0) AND no criterion regresses (paired CI < 0).
Else REVERT. Stop after 2 consecutive non-accepts, OR when `eval/results/loop/STOP` appears
(the current iteration finishes first), OR too few examples generated.

API calls (generation + eval judge + prune judge) run with bounded concurrency (WORKERS).
Every iteration is recorded in history.json; at the end an impact ranking is printed.

Run:  .venv/bin/python scripts/gap_loop.py   (background; `touch eval/results/loop/STOP` to halt)
"""
import concurrent.futures as cf
import json
import os
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from socratic_tutor import config, judge  # noqa: E402
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.prompts import SYSTEM_PROMPT, build_user_prompt  # noqa: E402
from socratic_tutor.rubric import (consistency_tier, grounded_tier, safety_tier,  # noqa: E402
                                    schema_tier, verdict_tier)
from socratic_tutor.schema import VERDICTS, parse_model_json  # noqa: E402
from socratic_tutor.runner import Runner  # noqa: E402

FROZEN = "eval/gold/frozen_eval.jsonl"
LOOP = "eval/results/loop"
os.makedirs(LOOP, exist_ok=True)
LOG, STATE, HIST, STOP = f"{LOOP}/log.md", f"{LOOP}/state.json", f"{LOOP}/history.json", f"{LOOP}/STOP"
FOCUS = ["rewrite_safety", "grounded", "consistency"]
ALLC = ["verdict", "schema", "grounded", "rewrite_safety", "consistency"]
WORKERS = 16
GEN = {
 "rewrite_safety": "Create a realistic K-12 math tutoring item where the candidate tutor message is NON-adequate (leaks the final answer or the key step). Then give a genuinely SAFE Socratic rewrite that guides with a question and leaks NEITHER the answer NOR the key step.",
 "grounded": "Create a realistic K-12 math tutoring item. The reasoning must quote a SPECIFIC detail from the problem or candidate that decisively justifies the verdict (never a generic label).",
 "consistency": "Create a BORDERLINE item that is genuinely either 'adequate' or 'mismatched_calibration' with ONE unambiguous correct verdict, to sharpen that boundary.",
}


def log(m):
    with open(LOG, "a") as f:
        f.write(m + "\n")
    print(m, flush=True)


def pmap(fn, items):
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        return list(ex.map(fn, items))


def _oai():
    from openai import OpenAI
    return OpenAI()


def _input(row):
    return {x: row.get(x) for x in ("problem", "correct_solution", "conversation_history", "candidate_message")}


def score(adapter, k=3):
    """Frozen-set per-item tiers. MLX gens serial (single GPU); judge calls parallel."""
    r = Runner(config.MODEL, adapter_path=adapter)
    uj = judge.judge_available()
    gold = read_jsonl(FROZEN)
    staged = []
    for gi, row in enumerate(gold, 1):
        if gi % 20 == 0 or gi == len(gold):
            print(f"[score {adapter}] MLX gen {gi}/{len(gold)}", flush=True)
        inp = _input(row)
        raw = r.generate(inp, temp=0.0)
        out = parse_model_json(raw)
        cons = consistency_tier([(parse_model_json(r.generate(inp, temp=0.7)) or {}).get("verdict")
                                 for _ in range(k)]) if k else None
        staged.append((row, raw, out, cons))

    def finish(t):
        row, raw, out, cons = t
        pred = (out or {}).get("verdict")
        return {"id": row["id"], "gold": row.get("gold_verdict"), "pred": pred,
                "verdict": verdict_tier(row.get("gold_verdict"), pred), "schema": schema_tier(raw, out),
                "grounded": grounded_tier(row, out, uj), "rewrite_safety": safety_tier(row, out, uj),
                "consistency": cons}
    return pmap(finish, staged)


def cmean(per, c):
    v = [i[c] for i in per if i.get(c) is not None]
    return round(sum(v) / len(v), 3) if v else 0.0


def paired(cand, base, c):
    bi = {i["id"]: i for i in base}
    d = [ci[c] - bi[ci["id"]][c] for ci in cand
         if ci["id"] in bi and ci[c] is not None and bi[ci["id"]][c] is not None]
    if not d:
        return (0.0, 0.0, 0.0)
    rng = random.Random(0)
    n = len(d)
    bs = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(2000))
    return (round(sum(d) / n, 3), round(bs[50], 3), round(bs[1950], 3))


def gen_add(crit, n=80):
    client = _oai()
    frozen_c = {r["candidate_message"].strip() for r in read_jsonl(FROZEN)}
    bands = ["K-2", "3-5", "6-8", "9-12"]
    sysmsg = (GEN[crit] + ' Return ONLY JSON {"problem","correct_solution","final_answer","key_step",'
              '"conversation_history":["Student: ...","Tutor: ..."],"candidate_message","verdict","reasoning","rewritten_message"}. '
              'verdict in [adequate,gives_final_answer,gives_away_key_step,mismatched_calibration,vague_unhelpful]. '
              'rewritten_message null iff verdict==adequate, else a SAFE Socratic hint (no answer/key-step leak).')

    def one(i):
        try:
            r = client.chat.completions.create(model=os.environ.get("OPENAI_JUDGE_MODEL", "gpt-4.1"),
                temperature=0.8, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": sysmsg}, {"role": "user", "content": f"Grade band: {bands[i % 4]}."}])
            return json.loads(r.choices[0].message.content)
        except Exception:
            return None
    rows = []
    for i, d in enumerate(pmap(one, list(range(n * 2)))):
        if len(rows) >= n or not d:
            continue
        cm, v = (d.get("candidate_message") or "").strip(), d.get("verdict")
        if not cm or v not in VERDICTS or cm in frozen_c:
            continue
        rm = None if v == "adequate" else d.get("rewritten_message")
        if v != "adequate" and not (isinstance(rm, str) and rm.strip()):
            continue
        rows.append({"id": f"gen-{crit}-{i:03d}", "problem": d.get("problem", ""),
                     "correct_solution": d.get("correct_solution", ""), "final_answer": str(d.get("final_answer", "")),
                     "key_step": d.get("key_step", ""), "conversation_history": d.get("conversation_history") or [],
                     "candidate_message": cm, "verdict": v, "reasoning": d.get("reasoning", ""),
                     "rewritten_message": rm, "slice": "core", "source": f"loop-add-{crit}"})
    return rows


def prune_noisy(best_data, sample_n=150):
    """Drop training rows whose stored label an independent gpt-4.1 judge disagrees with."""
    client = _oai()
    rows = read_jsonl(best_data)
    idx = list(range(len(rows)))
    random.Random(0).shuffle(idx)
    check = idx[:sample_n]

    def jverdict(i):
        row = rows[i]
        try:
            r = client.chat.completions.create(model=os.environ.get("OPENAI_JUDGE_MODEL", "gpt-4.1"),
                temperature=0, messages=[{"role": "system", "content": SYSTEM_PROMPT},
                                         {"role": "user", "content": build_user_prompt(_input(row))}])
            return (i, (parse_model_json(r.choices[0].message.content) or {}).get("verdict"))
        except Exception:
            return (i, None)
    drop = set()
    for i, jv in pmap(jverdict, check):
        if jv in VERDICTS and jv != rows[i].get("verdict"):
            drop.add(i)
    kept = [r for j, r in enumerate(rows) if j not in drop]
    return kept, len(drop), len(check)


def sh(cmd):
    # stream subprocess output to the loop's stdout (visible live in the run log) — not captured
    return subprocess.run(cmd, shell=True)


def train(rawfile, adapter, iters=500):
    sh(f'.venv/bin/python scripts/build_dataset.py --raw "{rawfile}" --seed 0')
    sh(f'.venv/bin/python -m mlx_lm lora --train --model {config.MODEL} --data data/mlx '
       f'--adapter-path {adapter} -c configs/lora_v1.yaml --iters {iters}')
    return os.path.exists(f"{adapter}/adapters.safetensors")


def score_subproc(adapter):
    """Run score() in a FRESH subprocess so the parent process never holds MLX memory.
    This prevents the train-time double-load (parent MLX cache + training subprocess)
    that caused swap; only one MLX process is ever resident at a time."""
    outp = f"{LOOP}/_score_{adapter.replace('/', '_')}.json"
    if os.path.exists(outp):
        os.remove(outp)
    sh(f'.venv/bin/python scripts/gap_loop.py --score-adapter {adapter} --score-out "{outp}"')
    return json.load(open(outp))


def main():
    if os.path.exists(STOP):
        os.remove(STOP)  # clear a stale halt flag on startup
    log(f"\n# Gap loop v2 start {time.strftime('%Y-%m-%d %H:%M')} (parallel API; cumulative-anchor; halt via STOP file; add+prune moves)")
    anchor_adapter, anchor_data = "adapters/v4", "data/raw/v4.jsonl"
    log(f"scoring anchor v4 ({time.strftime('%H:%M:%S')}) ...")
    anchor_per = score_subproc(anchor_adapter)
    best_adapter, best_data, best_per = anchor_adapter, anchor_data, anchor_per
    anchor_means = {c: cmean(anchor_per, c) for c in ALLC}
    log("Anchor (v4) frozen means: " + json.dumps(anchor_means))
    history = [{"iter": 0, "move": "anchor", "means": anchor_means, "accept": True}]
    json.dump(history, open(HIST, "w"), indent=2)
    dry = it = 0
    while dry < 2:
        if os.path.exists(STOP):
            log("STOP file present — halting after previous iteration."); break
        it += 1
        move = "add" if it % 2 == 1 else "prune"
        focus = min(FOCUS, key=lambda c: cmean(best_per, c))
        cand_data = f"{LOOP}/iter{it}_data.jsonl"
        if move == "add":
            new = gen_add(focus, 80)
            log(f"\n## Iter {it} — MOVE=add focus=**{focus}** — generated {len(new)} examples")
            if len(new) < 20:
                log("too few generated; stopping."); break
            write_jsonl(cand_data, read_jsonl(best_data) + new)
            change = f"add:{focus}"
        else:
            kept, dropped, checked = prune_noisy(best_data)
            log(f"\n## Iter {it} — MOVE=prune — dropped {dropped}/{checked} judged-mislabeled rows (kept {len(kept)})")
            if dropped == 0:
                log("nothing to prune; skipping (counts as dry)."); dry += 1
                history.append({"iter": it, "move": "prune", "accept": False, "note": "nothing_flagged"})
                json.dump(history, open(HIST, "w"), indent=2)
                continue
            write_jsonl(cand_data, kept)
            change = f"prune:{dropped}"
        cand_adapter = f"adapters/loop{it}"
        log(f"training {cand_adapter} ({time.strftime('%H:%M:%S')}) — ~500 iters, watch mlx output ...")
        if not train(cand_data, cand_adapter):
            log("training failed; revert."); dry += 1; continue
        log(f"scoring {cand_adapter} ({time.strftime('%H:%M:%S')}) ...")
        cand_per = score_subproc(cand_adapter)
        json.dump(cand_per, open(f"{LOOP}/iter{it}_per.json", "w"))
        fm, flo, fhi = paired(cand_per, anchor_per, focus)          # focus vs ANCHOR (cumulative)
        regress = []
        for c in ALLC:
            m, lo, hi = paired(cand_per, anchor_per, c)
            if hi < 0:
                regress.append(f"{c} {m:+.3f}[{lo:+.3f},{hi:+.3f}]")
        improved = flo > 0
        means = {c: cmean(cand_per, c) for c in ALLC}
        vs_anchor = {c: round(cmean(cand_per, c) - anchor_means[c], 3) for c in ALLC}
        log(f"candidate means: {json.dumps(means)}")
        log(f"vs anchor: {json.dumps(vs_anchor)}")
        log(f"focus {focus} vs-anchor {fm:+.3f} [{flo:+.3f},{fhi:+.3f}] (sig={improved}); regressions_vs_anchor={regress or 'none'}")
        accept = improved and not regress
        if accept:
            best_adapter, best_data, best_per = cand_adapter, cand_data, cand_per
            dry = 0
            log(f"**ACCEPT** -> new best {cand_adapter}")
        else:
            dry += 1
            log(f"**REVERT** (dry={dry}) reason={'no-sig-improve' if not improved else 'regression'}")
        history.append({"iter": it, "move": change, "focus": focus, "means": means,
                        "vs_anchor": vs_anchor, "focus_diff_ci": [fm, flo, fhi],
                        "regressions": regress, "accept": accept})
        json.dump(history, open(HIST, "w"), indent=2)
        json.dump({"iter": it, "best_adapter": best_adapter, "best_data": best_data, "dry": dry,
                   "best_means": {c: cmean(best_per, c) for c in ALLC}}, open(STATE, "w"), indent=2)

    # impact ranking
    log(f"\n# Loop done. Best: {best_adapter} | data: {best_data}")
    log("Final best frozen means: " + json.dumps({c: cmean(best_per, c) for c in ALLC}))
    acc = [h for h in history if h.get("accept") and h.get("iter", 0) > 0]
    log("\n## Impact ranking (accepted moves, by focus gain vs anchor)")
    for h in sorted(acc, key=lambda x: -(x.get("focus_diff_ci", [0])[0] or 0)):
        log(f"- iter {h['iter']} [{h['move']}] focus={h.get('focus')} focus_gain={h.get('focus_diff_ci',['?'])[0]:+} vs_anchor={h.get('vs_anchor')}")


if __name__ == "__main__":
    if "--score-adapter" in sys.argv:
        _a = sys.argv[sys.argv.index("--score-adapter") + 1]
        _o = sys.argv[sys.argv.index("--score-out") + 1]
        json.dump(score(_a), open(_o, "w"))
    else:
        main()
