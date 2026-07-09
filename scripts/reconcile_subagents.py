"""Subagent-driven reconcile (no external API key — uses this session's own model).

  --prep       write recon/criteria.md + recon/batch_XX.jsonl (un-decided items) + recon/meta.json.
               Claude subagents then read criteria.md + their batch and write recon/judged_XX.jsonl
               with one JSON line per item: {id, strict_verdict, calibrated_verdict, confidence, why}.
  --aggregate  read recon/judged_XX.jsonl + the reviewer's overturns -> proposed_edits.json +
               reconcile_report.md. Tiers each edit: CONFIRMED (strict read also != gold, agrees with
               calibrated) / SUPPORTED (strict also rejects gold, differs) / TENTATIVE (only the
               calibrated stricter read flips it) / USER (reviewer decided it). Never mutates gold.

Usage:
  python scripts/reconcile_subagents.py --prep --review "/path/review_results.json" --batches 8
  python scripts/reconcile_subagents.py --aggregate --review "/path/review_results.json"
"""

import argparse
import glob
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.prompts import SYSTEM_PROMPT  # noqa: E402
from socratic_tutor.schema import VERDICTS  # noqa: E402
from reconcile_review import REVIEWER_CRITERIA, build_guidelines, _find_review  # noqa: E402

RECON = "eval/gold/review/recon"
FROZEN = "eval/gold/frozen_eval.jsonl"
ITEM_FIELDS = ("id", "problem", "correct_solution", "final_answer", "key_step",
               "conversation_history", "candidate_message", "gold_verdict")


def prep(review_path, batches):
    review = json.load(open(_find_review(review_path)))
    ritems = review.get("items", review)
    frozen = read_jsonl(FROZEN)
    frozen_by_id = {r["id"]: r for r in frozen}
    decided = [x for x in ritems if x.get("user_verdict")]
    decided_ids = {x["id"] for x in decided}
    rules, shots, notes = build_guidelines(decided, frozen_by_id)

    os.makedirs(RECON, exist_ok=True)
    crit = [
        "# Verdict re-labeling task — apply the REVIEWER'S calibrated standard", "",
        "You are re-labeling K-12 math-tutoring judge items. A senior reviewer hand-corrected a "
        "sample; your job is to label the rest the way THEY would. Read this whole file, then label "
        "every item in your assigned batch file.", "",
        "## Base taxonomy (the 5 verdicts)", SYSTEM_PROMPT, "",
        "## The reviewer's OPERATIVE CRITERIA (apply per item — this is the key calibration)",
        REVIEWER_CRITERIA, "",
        "IMPORTANT: the reviewer only saw a PRE-FILTERED, suspicious sample, so it skews toward "
        "overturning `adequate`. Do NOT assume every `adequate` is wrong — apply the criteria to each "
        "item independently and keep `adequate` when the message genuinely builds on the student's "
        "specific work, correctly targets their actual mistake, and reveals neither answer nor key step.",
        "", "## Reviewer overturn frequencies (their demonstrated tendencies)", rules, "",
        "## Worked examples of the reviewer's own labels", "\n\n---\n\n".join(shots), "",
        "## Reviewer notes (verbatim reasoning)", "\n".join(f"- {n}" for n in notes[:30]) or "(none)", "",
        "## OUTPUT FORMAT (strict)",
        "Write your results to the output path given in your task prompt as JSONL — exactly ONE line "
        "per input item, no prose, each line a JSON object:",
        '  {"id": "<item id>", "strict_verdict": "<one of the 5>", "calibrated_verdict": "<one of the 5>", '
        '"confidence": "high|medium|low", "why": "<one sentence citing the specific criterion>"}',
        "- strict_verdict: apply ONLY the base taxonomy, IGNORING the reviewer calibration (your neutral read).",
        "- calibrated_verdict: apply the reviewer's operative criteria above (their standard).",
        f"- both MUST be one of: {', '.join(VERDICTS)}.",
        "- Do the strict read first and independently, then the calibrated read. Output every item id once.",
    ]
    with open(f"{RECON}/criteria.md", "w") as f:
        f.write("\n".join(crit))

    undecided = [r for r in frozen if r["id"] not in decided_ids]
    per = (len(undecided) + batches - 1) // batches
    nb = 0
    for k in range(batches):
        chunk = undecided[k * per:(k + 1) * per]
        if not chunk:
            continue
        write_jsonl(f"{RECON}/batch_{k:02d}.jsonl", [{f: r.get(f) for f in ITEM_FIELDS} for r in chunk])
        nb += 1
    json.dump({"decided": len(decided), "undecided": len(undecided), "batches": nb,
               "per_batch": per, "review_file": _find_review(review_path)},
              open(f"{RECON}/meta.json", "w"), indent=2)
    print(f"[prep] {len(decided)} decided, {len(undecided)} undecided -> {nb} batches (~{per} each)", file=sys.stderr)
    print(f"[prep] wrote {RECON}/criteria.md + batch_00..{nb-1:02d}.jsonl", file=sys.stderr)
    return 0


def aggregate(review_path):
    review = json.load(open(_find_review(review_path)))
    ritems = review.get("items", review)
    frozen = read_jsonl(FROZEN)
    decided = {x["id"]: x for x in ritems if x.get("user_verdict")}
    overturns = [x for x in ritems if x.get("agree_with_gold") is False and x.get("user_verdict")]
    rewrite_flags = [x["id"] for x in ritems if x.get("rewrite_unsafe")]
    gold = {r["id"]: r.get("gold_verdict") for r in frozen}

    judged = {}
    bad = 0
    for f in sorted(glob.glob(f"{RECON}/judged_*.jsonl")):
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
                if o.get("id") and o.get("calibrated_verdict") in VERDICTS:
                    judged[o["id"]] = o
                else:
                    bad += 1
            except Exception:
                bad += 1

    edits = []
    for iid, gv in gold.items():
        if iid in decided:
            x = decided[iid]
            if x.get("agree_with_gold") is False:
                edits.append({"id": iid, "old": gv, "new": x["user_verdict"], "source": "reviewer",
                              "tier": "USER", "confidence": "user", "why": (x.get("notes") or "").strip()})
            continue
        j = judged.get(iid)
        if not j:
            continue
        cal, strict = j["calibrated_verdict"], j.get("strict_verdict")
        if cal != gv:
            if strict == cal:
                tier = "CONFIRMED"
            elif strict and strict != gv:
                tier = "SUPPORTED"
            else:
                tier = "TENTATIVE"
            edits.append({"id": iid, "old": gv, "new": cal, "source": "subagent", "tier": tier,
                          "confidence": j.get("confidence", "medium"), "strict": strict,
                          "why": (j.get("why") or "")[:220]})

    missing = [iid for iid in gold if iid not in decided and iid not in judged]
    order = {"USER": 0, "CONFIRMED": 1, "SUPPORTED": 2, "TENTATIVE": 3}
    edits.sort(key=lambda e: order[e["tier"]])
    json.dump({"review_file": _find_review(review_path), "n_frozen": len(frozen),
               "reviewer_decided": len(decided), "judged": len(judged), "missing": missing,
               "malformed_lines": bad, "edits": edits, "rewrite_flags": rewrite_flags},
              open("eval/gold/review/proposed_edits.json", "w"), indent=2)

    tier_ct = Counter(e["tier"] for e in edits)
    trans_ct = Counter((e["old"], e["new"]) for e in edits)
    L = ["# Reconciliation — proposed edits to the golden set (Claude-subagent judged)", "",
         f"Review file: `{_find_review(review_path)}`  ",
         f"Reviewer decided **{len(decided)}**; subagents judged **{len(judged)}** un-decided items "
         f"(missing/unjudged: {len(missing)}, malformed lines skipped: {bad}).  ",
         f"Rewrites flagged unsafe: **{len(rewrite_flags)}**.", "",
         f"**Proposed verdict edits: {len(edits)}** of {len(frozen)} (unchanged: {len(frozen)-len(edits)}).", "",
         "Tiers: **USER** you decided · **CONFIRMED** both the calibrated and a neutral taxonomy-only read "
         "reject gold and agree on the new label · **SUPPORTED** both reject gold but differ on replacement · "
         "**TENTATIVE** only the stricter calibrated read flips it (hand-check).", "",
         "| tier | count |", "|---|---|"]
    for t in ["USER", "CONFIRMED", "SUPPORTED", "TENTATIVE"]:
        L.append(f"| {t} | {tier_ct.get(t,0)} |")
    L += ["", "## Edit transitions (gold -> proposed)", "| gold | proposed | n |", "|---|---|---|"]
    for (o, n2), c in trans_ct.most_common():
        L.append(f"| {o} | {n2} | {c} |")
    L += ["", "## Full edit list (grouped by tier)"]
    for t in ["USER", "CONFIRMED", "SUPPORTED", "TENTATIVE"]:
        te = [e for e in edits if e["tier"] == t]
        if not te:
            continue
        L.append(f"\n### {t} ({len(te)})")
        for e in te:
            s = f" · strict={e.get('strict')}" if e["source"] == "subagent" else ""
            L.append(f"- `{e['id']}` **{e['old']} -> {e['new']}** ({e['confidence']}{s}) — {e['why'][:180]}")
    with open("eval/gold/review/reconcile_report.md", "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"[aggregate] {len(edits)} edits {dict(tier_ct)}; missing={len(missing)} bad={bad}", file=sys.stderr)
    print("[aggregate] wrote eval/gold/review/reconcile_report.md + proposed_edits.json", file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prep", action="store_true")
    ap.add_argument("--aggregate", action="store_true")
    ap.add_argument("--review", default=None)
    ap.add_argument("--batches", type=int, default=8)
    a = ap.parse_args()
    if a.prep:
        return prep(a.review, a.batches)
    if a.aggregate:
        return aggregate(a.review)
    ap.error("pass --prep or --aggregate")


if __name__ == "__main__":
    raise SystemExit(main())
