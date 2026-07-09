"""LLM-as-judge framework to relabel TRAINING data against the CORRECTED golden set.

Pass 1 (--prep / judge): build a calibration pack from the corrected frozen_eval (few-shot
per verdict + REVIEWER_CRITERIA + taxonomy) and batch the training rows. Claude subagents
label each row's correct verdict -> recon-train/judged_XX.jsonl
({id, correct_verdict, confidence, why}).

--assemble-judged: read judged_XX.jsonl, flag flips (correct_verdict != stored verdict),
write recon-train/flips.jsonl (rows needing target regeneration) + a verdict-shift report.
Pass 2 (regeneration of full targets for flips) is a separate step.

Usage:
  python scripts/relabel_training.py --prep --batches 14
  python scripts/relabel_training.py --assemble-judged
"""

import argparse
import glob
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.prompts import SYSTEM_PROMPT  # noqa: E402
from socratic_tutor.rubric import _heuristic_safe  # noqa: E402  reuse the leak check
from socratic_tutor.schema import VERDICTS  # noqa: E402
from reconcile_review import REVIEWER_CRITERIA  # noqa: E402

REGEN_FIELDS = ("id", "problem", "correct_solution", "final_answer", "key_step",
                "conversation_history", "candidate_message", "correct_verdict", "why")

TRAIN = "data/raw/v4.jsonl"
FROZEN = "eval/gold/frozen_eval.jsonl"
RT = "eval/gold/review/recon-train"
FIELDS = ("id", "band", "problem", "correct_solution", "final_answer", "key_step",
          "conversation_history", "candidate_message", "verdict")


def _ctx(row, verdict_field, n=4):
    hist = (row.get("conversation_history") or [])[-n:]
    hs = "\n".join(f"  {h[:220]}" for h in hist) if hist else "  (none)"
    return (f"PROBLEM: {row.get('problem','')[:220]}\nFINAL ANSWER: {row.get('final_answer','')}\n"
            f"CONVERSATION (last turns):\n{hs}\n"
            f"CANDIDATE TUTOR MESSAGE: {row.get('candidate_message','')[:380]}\n"
            f"CORRECT VERDICT: {row.get(verdict_field)}")


def golden_fewshot(per_verdict=3):
    """Few-shot examples of each verdict drawn from the CORRECTED golden set."""
    gold = read_jsonl(FROZEN)
    by_v = defaultdict(list)
    for r in gold:
        by_v[r.get("gold_verdict")].append(r)
    shots = []
    for v in VERDICTS:
        picked = by_v.get(v, [])[:per_verdict]
        for r in picked:
            shots.append(_ctx(r, "gold_verdict"))
    return shots, {v: len(by_v.get(v, [])) for v in VERDICTS}


def prep(batches):
    rows = read_jsonl(TRAIN)
    shots, gold_counts = golden_fewshot()
    os.makedirs(RT, exist_ok=True)
    crit = [
        "# TRAINING-DATA verdict relabeling — judge against the corrected golden standard", "",
        "You are auditing the verdict labels on math-tutoring TRAINING rows. For each row, decide "
        "the CORRECT verdict for its candidate_message, applying the standard below. This standard "
        "comes from a corrected, human-anchored golden set — the current training labels are known to "
        "OVER-use `adequate` on messages that actually leak the key step, so judge each on its merits.", "",
        "## Base taxonomy (the 5 verdicts)", SYSTEM_PROMPT, "",
        "## OPERATIVE CRITERIA (apply per row)", REVIEWER_CRITERIA, "",
        "## Worked examples from the CORRECTED golden set (the standard to match)",
        "\n\n---\n\n".join(shots), "",
        "## OUTPUT (strict)",
        "Write to the output path in your task prompt as JSONL — exactly ONE line per input row, no prose:",
        '  {"id": "<row id>", "correct_verdict": "<one of the 5>", "confidence": "high|medium|low", '
        '"why": "<one sentence citing the criterion>"}',
        f"- correct_verdict MUST be one of: {', '.join(VERDICTS)}.",
        "- Judge the candidate_message against the problem, correct solution, and conversation. Output every id once.",
    ]
    with open(f"{RT}/calibration.md", "w") as f:
        f.write("\n".join(crit))
    per = (len(rows) + batches - 1) // batches
    nb = 0
    for k in range(batches):
        chunk = rows[k * per:(k + 1) * per]
        if not chunk:
            continue
        write_jsonl(f"{RT}/batch_{k:02d}.jsonl", [{f: r.get(f) for f in FIELDS} for r in chunk])
        nb += 1
    json.dump({"train_rows": len(rows), "batches": nb, "per_batch": per,
               "golden_fewshot_available": gold_counts},
              open(f"{RT}/meta.json", "w"), indent=2)
    print(f"[prep] {len(rows)} training rows -> {nb} batches (~{per} each)", file=sys.stderr)
    print(f"[prep] calibration.md built from golden set (few-shot per verdict): {gold_counts}", file=sys.stderr)
    print(f"[prep] wrote {RT}/calibration.md + batch_00..{nb-1:02d}.jsonl", file=sys.stderr)
    return 0


def assemble_judged():
    rows = read_jsonl(TRAIN)
    stored = {r["id"]: r for r in rows}
    judged = {}
    bad = 0
    for f in sorted(glob.glob(f"{RT}/judged_*.jsonl")):
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
                if o.get("id") and o.get("correct_verdict") in VERDICTS:
                    judged[o["id"]] = o
                else:
                    bad += 1
            except Exception:
                bad += 1
    flips, kept = [], 0
    for iid, j in judged.items():
        row = stored.get(iid)
        if not row:
            continue
        cv = j["correct_verdict"]
        if cv != row.get("verdict"):
            flips.append({**{k: row.get(k) for k in FIELDS}, "old_verdict": row.get("verdict"),
                          "correct_verdict": cv, "confidence": j.get("confidence"), "why": j.get("why", "")})
        else:
            kept += 1
    missing = [r["id"] for r in rows if r["id"] not in judged]
    write_jsonl(f"{RT}/flips.jsonl", flips)
    trans = Counter((f["old_verdict"], f["correct_verdict"]) for f in flips)
    print(f"[assemble] judged={len(judged)} kept={kept} FLIPS={len(flips)} missing={len(missing)} bad={bad}")
    print("[assemble] flip transitions (old -> correct):")
    for (o, n), c in trans.most_common():
        print(f"    {c:4d}  {o} -> {n}")
    print(f"[assemble] wrote {RT}/flips.jsonl (rows needing target regeneration)")
    if missing:
        print(f"[assemble] WARNING missing {len(missing)} rows (unjudged) — re-run their batches")
    return 0


def prep_regen(batches):
    """Batch the NON-adequate flips for target regeneration (they need a safe rewrite +
    grounded reasoning). ->adequate flips need no generation (rewrite becomes null)."""
    flips = read_jsonl(f"{RT}/flips.jsonl")
    nonadeq = [f for f in flips if f["correct_verdict"] != "adequate"]
    os.makedirs(RT, exist_ok=True)
    crit = [
        "# Regenerate corrected TRAINING targets (grounded reasoning + SAFE rewrite)", "",
        "Each row below has been re-judged to a NEW correct verdict (`correct_verdict`). The old "
        "target is stale. Produce the corrected target fields for the judge-model to learn:", "",
        "## Base taxonomy", SYSTEM_PROMPT, "",
        "## OPERATIVE CRITERIA (what makes a rewrite SAFE)", REVIEWER_CRITERIA, "",
        "## For EACH row produce:",
        "- `reasoning`: one-to-two sentences that JUSTIFY `correct_verdict`, citing a SPECIFIC detail "
        "from the problem / solution / conversation / candidate message (never a bare label).",
        "- `rewritten_message`: a SAFE Socratic hint that (a) NEVER states the final answer, (b) NEVER "
        "hands over the key step/insight or the pivotal relationship, (c) points the student toward WHERE "
        "their mistake is and asks them to find/fix it, (d) is grounded in the student's most recent message. "
        "It must NOT contain the final_answer and must NOT restate the key_step.", "",
        "## OUTPUT (strict)",
        "Write to the output path in your task prompt as JSONL — exactly ONE line per input row, no prose:",
        '  {"id": "...", "reasoning": "...", "rewritten_message": "..."}',
        "Cover every id exactly once. rewritten_message must be a non-empty safe hint (these rows are all NON-adequate).",
    ]
    with open(f"{RT}/criteria_regen.md", "w") as f:
        f.write("\n".join(crit))
    per = (len(nonadeq) + batches - 1) // batches
    nb = 0
    for k in range(batches):
        chunk = nonadeq[k * per:(k + 1) * per]
        if not chunk:
            continue
        write_jsonl(f"{RT}/regen_batch_{k:02d}.jsonl", [{f: r.get(f) for f in REGEN_FIELDS} for r in chunk])
        nb += 1
    to_adeq = len(flips) - len(nonadeq)
    print(f"[prep-regen] {len(flips)} flips: {to_adeq} ->adequate (mechanical), "
          f"{len(nonadeq)} ->non-adequate need regen -> {nb} batches (~{per} each)", file=sys.stderr)
    print(f"[prep-regen] wrote {RT}/criteria_regen.md + regen_batch_00..{nb-1:02d}.jsonl", file=sys.stderr)
    return 0


def assemble_v5(out_path):
    v4 = read_jsonl(TRAIN)
    flips = {f["id"]: f for f in read_jsonl(f"{RT}/flips.jsonl")}
    regen = {}
    for f in sorted(glob.glob(f"{RT}/regen_out_*.jsonl")):
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
                if o.get("id") and (o.get("rewritten_message") or "").strip():
                    regen[o["id"]] = o
            except Exception:
                pass
    out, dropped = [], []
    n_kept = n_adeq = n_regen = 0
    for row in v4:
        fl = flips.get(row["id"])
        if not fl:
            out.append(row); n_kept += 1; continue
        cv = fl["correct_verdict"]
        new = dict(row)
        new["verdict"] = cv
        if cv == "adequate":
            new["reasoning"] = (fl.get("why") or row.get("reasoning") or "").strip()
            new["rewritten_message"] = None
            new["relabeled"] = "to_adequate"
            out.append(new); n_adeq += 1
        else:
            g = regen.get(row["id"])
            if not g:
                dropped.append((row["id"], "no_regen_output")); continue
            rw = (g.get("rewritten_message") or "").strip()
            new["reasoning"] = (g.get("reasoning") or fl.get("why") or "").strip()
            new["rewritten_message"] = rw
            if not _heuristic_safe(row, {"rewritten_message": rw}):  # leak gate
                dropped.append((row["id"], "rewrite_leaks")); continue
            new["relabeled"] = "regenerated"
            out.append(new); n_regen += 1
    write_jsonl(out_path, out)
    from collections import Counter
    print(f"[v5] wrote {len(out)} rows -> {out_path}  (kept {n_kept}, ->adequate {n_adeq}, regenerated {n_regen})")
    print(f"[v5] dropped {len(dropped)} flips failing regen/leak-gate: {Counter(d[1] for d in dropped)}")
    print(f"[v5] new verdict dist: {dict(Counter(r['verdict'] for r in out))}")
    if dropped:
        json.dump(dropped, open(f"{RT}/v5_dropped.json", "w"), indent=2)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prep", action="store_true")
    ap.add_argument("--assemble-judged", action="store_true")
    ap.add_argument("--prep-regen", action="store_true")
    ap.add_argument("--assemble-v5", action="store_true")
    ap.add_argument("--batches", type=int, default=14)
    ap.add_argument("--regen-batches", type=int, default=5)
    ap.add_argument("--out", default="data/raw/v5.jsonl")
    a = ap.parse_args()
    if a.prep:
        return prep(a.batches)
    if a.assemble_judged:
        return assemble_judged()
    if a.prep_regen:
        return prep_regen(a.regen_batches)
    if a.assemble_v5:
        return assemble_v5(a.out)
    ap.error("pass --prep / --assemble-judged / --prep-regen / --assemble-v5")


if __name__ == "__main__":
    raise SystemExit(main())
