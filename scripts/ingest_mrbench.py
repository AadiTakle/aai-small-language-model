"""Ingest MRBench V2 (human-annotated tutor responses) into our judge/rewriter schema.

MRBench (Maurya et al., NAACL 2025; CC-BY-SA-4.0), built on MathDial+Bridge, labels each
tutor response on 8 pedagogical dimensions. We map the HUMAN labels to our verdict taxonomy
and use a clean Expert/sibling response as the real safe `rewrite` target (real contrastive
pairs). Only `reasoning` is model-written (grounded), via socratic_tutor.annotate.

Verdict mapping:
  Revealing_of_the_Answer startswith "Yes"           -> gives_final_answer
  Providing_Guidance == "No"                          -> vague_unhelpful
  Providing_Guidance == "Yes" & Actionability == Yes  -> adequate
  Providing_Guidance == "Yes" (not actionable)        -> mismatched_calibration
  Providing_Guidance == "To some extent"              -> mismatched_calibration
(gives_away_key_step is NOT derivable from MRBench — it stays with the synthetic data.)

Usage:
  python scripts/ingest_mrbench.py --dry
  python scripts/ingest_mrbench.py --annotate --cap 90 --out data/raw/real_mrbench.jsonl
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from socratic_tutor import annotate, config  # noqa: E402
from socratic_tutor.io_utils import write_jsonl  # noqa: E402
from socratic_tutor.schema import validate_output  # noqa: E402

URL = "https://raw.githubusercontent.com/kaushal0494/UnifyingAITutorEvaluation/main/MRBench/MRBench_V2.json"
EXT = config.DATA_DIR / "external" / "mrbench_v2.json"


def download() -> list:
    if not EXT.exists():
        EXT.parent.mkdir(parents=True, exist_ok=True)
        print(f"[mrbench] downloading -> {EXT}", file=sys.stderr)
        urllib.request.urlretrieve(URL, EXT)
    return json.load(open(EXT))


def parse_history(s: str):
    s = (s or "").replace("\xa0", " ")
    parts = re.split(r"(?=(?:Tutor:|Student:))", s)
    turns = [re.sub(r"\s+", " ", p).strip() for p in parts if p.strip()]
    problem = ""
    if turns:
        m = re.search(r"The question is:\s*(.*)", turns[0])
        if m:
            problem = m.group(1).strip()
    return problem, turns


def final_answer(sol: str) -> str:
    nums = re.findall(r"-?\d[\d,]*(?:\.\d+)?", sol or "")
    return nums[-1].replace(",", "") if nums else ""


def map_verdict(a: dict):
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


def is_clean(resp: dict) -> bool:
    a = resp["annotation"]
    return (a.get("Revealing_of_the_Answer") == "No"
            and a.get("Providing_Guidance") == "Yes"
            and a.get("Actionability") == "Yes")


def pick_rewrite(responses: dict, exclude_model: str):
    exp = responses.get("Expert")
    if exp and exclude_model != "Expert" and is_clean(exp):
        return exp["response"]
    for m, r in responses.items():
        if m != exclude_model and is_clean(r):
            return r["response"]
    return None


def build_rows(data: list, cap=None, annotate_reasoning=False):
    rows, by_verdict, skipped, caps = [], Counter(), Counter(), defaultdict(int)
    for c in data:
        problem, history = parse_history(c["conversation_history"])
        sol = c.get("Ground_Truth_Solution", "")
        fa = final_answer(sol)
        for model, resp in c["anno_llm_responses"].items():
            v = map_verdict(resp["annotation"])
            if v is None:
                skipped["unmappable"] += 1
                continue
            if cap and caps[v] >= cap:
                skipped["capped"] += 1
                continue
            rw = None
            if v != "adequate":
                rw = pick_rewrite(c["anno_llm_responses"], model)
                if not rw:
                    skipped["no_safe_rewrite"] += 1
                    continue
            rows.append({
                "id": f"mrb-{c['conversation_id'][:8]}-{model}",
                "problem": problem, "correct_solution": sol, "final_answer": fa,
                "key_step": "", "conversation_history": history,
                "candidate_message": resp["response"], "verdict": v,
                "reasoning": "", "rewritten_message": rw,
                "source": "mrbench_v2", "slice": "core",
            })
            by_verdict[v] += 1
            caps[v] += 1

    if annotate_reasoning:
        for i, row in enumerate(rows, 1):
            r = annotate.write_reasoning(row["problem"], row["conversation_history"],
                                         row["candidate_message"], row["verdict"])
            row["reasoning"] = r or f"The response's guidance/answer-revealing pattern matches {row['verdict']}."
            if i % 25 == 0 or i == len(rows):
                print(f"[mrbench] reasoning {i}/{len(rows)}", file=sys.stderr, flush=True)
    else:
        for row in rows:
            row["reasoning"] = f"[placeholder-reasoning] {row['verdict']}"
    return rows, by_verdict, skipped


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry", action="store_true", help="mapping stats + samples, no API/write")
    p.add_argument("--annotate", action="store_true", help="write grounded reasoning via gpt-4.1")
    p.add_argument("--cap", type=int, default=None, help="max rows per verdict (balance)")
    p.add_argument("--out", default="data/raw/real_mrbench.jsonl")
    args = p.parse_args()

    data = download()
    rows, bv, sk = build_rows(data, cap=args.cap,
                              annotate_reasoning=(args.annotate and not args.dry))
    print(f"[mrbench] {len(rows)} rows | by verdict: {dict(bv)} | skipped: {dict(sk)}", file=sys.stderr)

    if args.dry:
        for v in ["adequate", "gives_final_answer", "mismatched_calibration", "vague_unhelpful"]:
            ex = next((r for r in rows if r["verdict"] == v), None)
            if ex:
                print(f"\n--- {v} ---")
                print("  candidate:", ex["candidate_message"][:160])
                print("  rewrite:  ", (ex["rewritten_message"] or "None")[:160])
        return 0

    good = [r for r in rows if validate_output(
        {"verdict": r["verdict"], "reasoning": r["reasoning"],
         "rewritten_message": r["rewritten_message"]})[0]]
    write_jsonl(args.out, good)
    print(f"[mrbench] wrote {len(good)}/{len(rows)} schema-valid rows -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
