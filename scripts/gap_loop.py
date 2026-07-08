#!/usr/bin/env python
"""Autonomous overnight gap-closing loop (LOCAL SFT). Durable: all state + a human-readable
log live on disk so it does not depend on any agent's context.

Each iteration:
  1. score the current BEST adapter on the frozen leakage-checked set (frozen_eval.jsonl)
  2. pick the WEAKEST focus criterion (rewrite_safety / grounded / consistency)
  3. generate ~80 targeted SFT examples for ONLY that criterion (gpt-4.1 teacher), leakage-guarded
  4. append to best data, rebuild, retrain a candidate LoRA
  5. score candidate; ACCEPT iff focus improves (paired-bootstrap 95% CI excludes 0) AND no
     other criterion regresses (paired CI < 0); else REVERT
  6. stop after 2 consecutive non-accepts.

Run:  .venv/bin/python scripts/gap_loop.py   (launch in background; watch eval/results/loop/log.md)
"""
import json
import os
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from socratic_tutor import config, judge  # noqa: E402
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.rubric import (consistency_tier, grounded_tier, safety_tier,  # noqa: E402
                                    schema_tier, verdict_tier)
from socratic_tutor.schema import VERDICTS, parse_model_json  # noqa: E402
from socratic_tutor.runner import Runner  # noqa: E402

FROZEN = "eval/gold/frozen_eval.jsonl"
LOOP = "eval/results/loop"
os.makedirs(LOOP, exist_ok=True)
LOG = f"{LOOP}/log.md"
STATE = f"{LOOP}/state.json"
FOCUS = ["rewrite_safety", "grounded", "consistency"]  # verdict/schema already frontier-competitive
ALLC = ["verdict", "schema", "grounded", "rewrite_safety", "consistency"]

GEN = {
 "rewrite_safety": "Create a realistic K-12 math tutoring item where the candidate tutor message is NON-adequate (it leaks the final answer or the key step). Then give a genuinely SAFE Socratic rewrite that guides with a question and leaks NEITHER the answer NOR the key step.",
 "grounded": "Create a realistic K-12 math tutoring item. The reasoning must quote a SPECIFIC detail from the problem or candidate that decisively justifies the verdict (never a generic label).",
 "consistency": "Create a BORDERLINE item that is genuinely either 'adequate' or 'mismatched_calibration' with ONE unambiguous correct verdict, to sharpen that boundary.",
}


def log(m):
    with open(LOG, "a") as f:
        f.write(m + "\n")
    print(m, flush=True)


def score(adapter, k=3):
    r = Runner(config.MODEL, adapter_path=adapter)
    uj = judge.judge_available()
    per = []
    for row in read_jsonl(FROZEN):
        inp = {x: row.get(x) for x in ("problem", "correct_solution", "conversation_history", "candidate_message")}
        raw = r.generate(inp, temp=0.0)
        out = parse_model_json(raw)
        pred = (out or {}).get("verdict")
        it = {"id": row["id"], "gold": row.get("gold_verdict"), "pred": pred,
              "verdict": verdict_tier(row.get("gold_verdict"), pred), "schema": schema_tier(raw, out),
              "grounded": grounded_tier(row, out, uj), "rewrite_safety": safety_tier(row, out, uj),
              "consistency": consistency_tier([(parse_model_json(r.generate(inp, temp=0.7)) or {}).get("verdict") for _ in range(k)]) if k else None}
        per.append(it)
    return per


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


def gen_for(crit, n=80):
    from openai import OpenAI
    client = OpenAI()
    frozen_c = {r["candidate_message"].strip() for r in read_jsonl(FROZEN)}
    bands = ["K-2", "3-5", "6-8", "9-12"]
    sysmsg = (GEN[crit] + ' Return ONLY JSON {"problem","correct_solution","final_answer","key_step",'
              '"conversation_history":["Student: ...","Tutor: ..."],"candidate_message","verdict","reasoning","rewritten_message"}. '
              'verdict in [adequate,gives_final_answer,gives_away_key_step,mismatched_calibration,vague_unhelpful]. '
              'rewritten_message is null iff verdict==adequate, else a SAFE Socratic hint that leaks neither answer nor key step.')
    rows = []
    for i in range(n * 3):
        if len(rows) >= n:
            break
        band = bands[i % 4]
        try:
            r = client.chat.completions.create(model=os.environ.get("OPENAI_JUDGE_MODEL", "gpt-4.1"),
                temperature=0.8, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": sysmsg}, {"role": "user", "content": f"Grade band: {band}."}])
            d = json.loads(r.choices[0].message.content)
        except Exception:
            time.sleep(3)
            continue
        cm = (d.get("candidate_message") or "").strip()
        v = d.get("verdict")
        if not cm or v not in VERDICTS or cm in frozen_c:
            continue
        rm = d.get("rewritten_message")
        if v == "adequate":
            rm = None
        elif not (isinstance(rm, str) and rm.strip()):
            continue
        rows.append({"id": f"gen-{crit}-{i:03d}", "problem": d.get("problem", ""),
                     "correct_solution": d.get("correct_solution", ""), "final_answer": str(d.get("final_answer", "")),
                     "key_step": d.get("key_step", ""), "conversation_history": d.get("conversation_history") or [],
                     "candidate_message": cm, "verdict": v, "reasoning": d.get("reasoning", ""),
                     "rewritten_message": rm, "slice": "core", "source": f"loop-{crit}"})
    return rows


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def train(rawfile, adapter, iters=500):
    sh(f'.venv/bin/python scripts/build_dataset.py --raw "{rawfile}" --seed 0')
    r = sh(f'.venv/bin/python -m mlx_lm lora --train --model {config.MODEL} --data data/mlx '
           f'--adapter-path {adapter} -c configs/lora_v1.yaml --iters {iters}')
    return os.path.exists(f"{adapter}/adapters.safetensors")


def main():
    log(f"\n# Gap-closing loop start {time.strftime('%Y-%m-%d %H:%M')} (local SFT; accept=paired-sig + no-regression; stop=2 dry)")
    best_adapter, best_data = "adapters/v4", "data/raw/v4.jsonl"
    best_per = score(best_adapter)
    log("Baseline (v4) frozen means: " + json.dumps({c: cmean(best_per, c) for c in ALLC}))
    dry = it = 0
    while dry < 2:
        it += 1
        focus = min(FOCUS, key=lambda c: cmean(best_per, c))
        log(f"\n## Iter {it} — focus **{focus}** (means {json.dumps({c: cmean(best_per, c) for c in FOCUS})})")
        new = gen_for(focus, 80)
        log(f"generated {len(new)} targeted examples for {focus}")
        if len(new) < 20:
            log("too few generated; stopping."); break
        cand_data = f"{LOOP}/iter{it}_data.jsonl"
        write_jsonl(cand_data, read_jsonl(best_data) + new)
        cand_adapter = f"adapters/loop{it}"
        if not train(cand_data, cand_adapter):
            log("training failed; reverting."); dry += 1; continue
        cand_per = score(cand_adapter)
        json.dump(cand_per, open(f"{LOOP}/iter{it}_per.json", "w"))
        fm, flo, fhi = paired(cand_per, best_per, focus)
        regress = []
        for c in ALLC:
            if c == focus:
                continue
            m, lo, hi = paired(cand_per, best_per, c)
            if hi < 0:
                regress.append(f"{c} {m:+.3f}[{lo:+.3f},{hi:+.3f}]")
        improved = flo > 0
        log(f"candidate means: " + json.dumps({c: cmean(cand_per, c) for c in ALLC}))
        log(f"focus {focus} paired diff {fm:+.3f} [{flo:+.3f},{fhi:+.3f}] (sig={improved}); regressions={regress or 'none'}")
        if improved and not regress:
            best_adapter, best_data, best_per = cand_adapter, cand_data, cand_per
            dry = 0
            log(f"**ACCEPT** -> new best {cand_adapter}")
        else:
            dry += 1
            log(f"**REVERT** (dry={dry}) reason={'no-sig-improve' if not improved else 'regression'}")
        json.dump({"iter": it, "best_adapter": best_adapter, "best_data": best_data, "dry": dry,
                   "means": {c: cmean(best_per, c) for c in ALLC}}, open(STATE, "w"), indent=2)
    log(f"\n# Loop done. Best adapter: {best_adapter} | data: {best_data}")
    log("Final frozen means: " + json.dumps({c: cmean(best_per, c) for c in ALLC}))


if __name__ == "__main__":
    main()
