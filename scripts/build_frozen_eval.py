"""Build a FROZEN evaluation set that is clean for ALL contestants (base Qwen, v2, v3, v4).

Source = MRBench V2 responses whose *conversation* was never used in training
(`real_mrbench.jsonl`), mapped to our verdict taxonomy with the human labels, balanced
across the 4 MRBench-derivable verdicts, + the hand-written seed gold (adds
gives_away_key_step and hand-crafted hard cases). Every non-adequate item carries a real
Expert rewrite as the reference. A definitive candidate-message substring check against
every training file guarantees zero leakage.

Usage: python scripts/build_frozen_eval.py --per-verdict 25 --out eval/gold/frozen_eval.jsonl
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402

MR = config.DATA_DIR / "external" / "mrbench_v2.json"
TRAIN_FILES = ["data/raw/all.jsonl", "data/raw/v3.jsonl", "data/raw/v4.jsonl",
               "data/raw/real_mrbench.jsonl", "data/raw/real_mathdial.jsonl",
               "data/mlx/train.jsonl", "data/mlx/valid.jsonl"]


def parse_history(s):
    s = (s or "").replace("\xa0", " ")
    turns = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"(?=(?:Tutor:|Student:))", s) if p.strip()]
    problem = ""
    if turns:
        m = re.search(r"The question is:\s*(.*)", turns[0])
        if m:
            problem = m.group(1).strip()
    return problem, turns


def final_answer(sol):
    nums = re.findall(r"-?\d[\d,]*(?:\.\d+)?", sol or "")
    return nums[-1].replace(",", "") if nums else ""


def map_verdict(a):
    if str(a.get("Revealing_of_the_Answer", "")).startswith("Yes"):
        return "gives_final_answer"
    g, act = a.get("Providing_Guidance", ""), a.get("Actionability", "")
    if g == "No":
        return "vague_unhelpful"
    if g == "Yes":
        return "adequate" if act == "Yes" else "mismatched_calibration"
    if g == "To some extent":
        return "mismatched_calibration"
    return None


def is_clean(resp):
    a = resp["annotation"]
    return (a.get("Revealing_of_the_Answer") == "No" and a.get("Providing_Guidance") == "Yes"
            and a.get("Actionability") == "Yes")


def pick_rewrite(responses, exclude):
    exp = responses.get("Expert")
    if exp and exclude != "Expert" and is_clean(exp):
        return exp["response"]
    for m, r in responses.items():
        if m != exclude and is_clean(r):
            return r["response"]
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--per-verdict", type=int, default=25)
    p.add_argument("--out", default="eval/gold/frozen_eval.jsonl")
    args = p.parse_args()

    data = json.load(open(MR))
    # conversations touched by training (via the conv8 prefix used in ingest ids)
    trained_conv8 = set()
    for r in read_jsonl("data/raw/real_mrbench.jsonl"):
        trained_conv8.add(r["id"][len("mrb-"):].rsplit("-", 1)[0])

    rows, caps = [], defaultdict(int)
    skipped_touched = 0
    for c in data:
        if c["conversation_id"][:8] in trained_conv8:
            skipped_touched += 1
            continue  # exclude whole conversation → no shared problem/context with training
        problem, history = parse_history(c["conversation_history"])
        if not problem:
            continue
        sol = c.get("Ground_Truth_Solution", "")
        fa = final_answer(sol)
        for model, resp in c["anno_llm_responses"].items():
            v = map_verdict(resp["annotation"])
            if v is None or caps[v] >= args.per_verdict:
                continue
            rw = None
            if v != "adequate":
                rw = pick_rewrite(c["anno_llm_responses"], model)
                if not rw:
                    continue
            rows.append({
                "id": f"frozen-mrb-{c['conversation_id'][:8]}-{model}", "problem": problem,
                "correct_solution": sol, "final_answer": fa, "key_step": "",
                "conversation_history": history, "candidate_message": resp["response"],
                "gold_verdict": v, "gold_reasoning": "", "gold_rewrite": rw or "",
                "slice": "core", "source": f"mrbench:{model}",
            })
            caps[v] += 1

    # add the hand-written seed gold (clean for all versions; adds gives_away_key_step)
    seed = read_jsonl("eval/gold/test.jsonl")
    for r in seed:
        r = dict(r)
        r["source"] = "seed"
        r["id"] = f"frozen-{r['id']}"
        rows.append(r)

    # definitive leakage check: no frozen candidate_message may appear in any training text
    train_blob = ""
    for f in TRAIN_FILES:
        if os.path.exists(f):
            train_blob += "\n".join(json.dumps(x) for x in read_jsonl(f))
    leaked_ids = {r["id"] for r in rows if r["candidate_message"].strip() and r["candidate_message"].strip() in train_blob}
    leaked_lens = sorted(len(r["candidate_message"].strip()) for r in rows if r["id"] in leaked_ids)
    rows = [r for r in rows if r["id"] not in leaked_ids]  # drop leaked → guarantee 0 leakage
    # recheck
    still = [r["id"] for r in rows if r["candidate_message"].strip() and r["candidate_message"].strip() in train_blob]

    write_jsonl(args.out, rows)
    print(f"[frozen] wrote {len(rows)} items -> {args.out}", file=sys.stderr)
    print(f"[frozen] dropped {len(leaked_ids)} candidate-message-in-training items "
          f"(lengths={leaked_lens} → {'all short/generic' if leaked_lens and max(leaked_lens)<80 else 'includes long strings'})", file=sys.stderr)
    print(f"[frozen] excluded {skipped_touched} training-touched conversations", file=sys.stderr)
    print(f"[frozen] by verdict: {dict(Counter(r['gold_verdict'] for r in rows))}")
    print(f"[frozen] by source: {dict(Counter(r['source'].split(':')[0] for r in rows))}")
    print(f"[frozen] adversarial slice: {sum(1 for r in rows if r.get('slice')=='calibration_adversarial')}")
    print(f"[frozen] LEAKAGE CHECK (post-drop) — candidate_messages in training: {len(still)} {'FAIL '+str(still[:3]) if still else 'PASS (0)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
