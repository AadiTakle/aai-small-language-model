"""Reconcile a human review_results.json against the golden set and PROPOSE label edits
for the items the reviewer didn't personally decide — calibrated to the reviewer's own
demonstrated standard. NEVER mutates eval/gold/frozen_eval.jsonl; writes a proposal only.

Pipeline:
 1) Parse the reviewer's decisions; report their calibration (overturn matrix + notes).
 2) Build a GUIDED adjudication prompt = taxonomy (SYSTEM_PROMPT) + the reviewer's
    demonstrated rules (their overturns as few-shot + their notes verbatim).
 3) Guided gpt-4.1 pass over every frozen item the reviewer did NOT decide -> proposed
    verdict + confidence + reason (mimicking how the reviewer labels).
 4) Verification pass (independent, taxonomy-only, no calibration) over candidate edits
    -> confidence tier: CONFIRMED / SUPPORTED / TENTATIVE.
 5) Write reconcile_report.md + proposed_edits.json.

Usage:
  python scripts/reconcile_review.py --review "/path/review_results.json"
"""

import argparse
import glob
import json
import os
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from socratic_tutor.io_utils import read_jsonl  # noqa: E402
from socratic_tutor.prompts import SYSTEM_PROMPT, build_user_prompt  # noqa: E402
from socratic_tutor.schema import VERDICTS, parse_model_json  # noqa: E402

FROZEN = "eval/gold/frozen_eval.jsonl"

# Distilled from the reviewer's own notes/overturns (shown to the user for confirmation).
REVIEWER_CRITERIA = (
    "1. LEAK is strict: if the message names or performs the pivotal step, OR reveals a "
    "relationship/comparison/operation the student is supposed to derive (e.g. tells them "
    "'X is bigger than Y', or introduces a quantity/step not yet established), it is "
    "`gives_away_key_step` — NOT adequate. The adequate move is to point the student to WHERE "
    "their mistake is and ask them to find/fix it, without handing over the fix.\n"
    "2. BUILD: if the message doesn't engage the student's SPECIFIC work/attempt — a generic "
    "question or restatement that could apply to any problem — it is `vague_unhelpful`.\n"
    "3. UNDERSTAND: if the message misdiagnoses the student's actual error, or is premised on a "
    "wrong reading of what they did (incl. falsely implying they're close when they misunderstood), "
    "it is `mismatched_calibration`.\n"
    "4. CONFIRMATION: if the student has ALREADY reached the correct answer and the tutor simply "
    "confirms/acknowledges it, that is `adequate` (not `gives_final_answer` — the student already has it).\n"
    "5. Otherwise, if it builds on the student's work, correctly targets the mistake, and reveals "
    "neither answer nor key step, it is `adequate`."
)


def _input(row):
    return {x: row.get(x) for x in ("problem", "correct_solution", "conversation_history", "candidate_message")}


def _client():
    """OpenAI client with a hard per-request timeout + SDK-native rate-limit retries
    (honors Retry-After). Prevents the hang/stall from unbounded requests."""
    from openai import OpenAI
    return OpenAI(timeout=45.0, max_retries=6)


def preflight():
    """One fail-fast probe so a dead key / inactive billing aborts immediately instead of
    grinding 273 calls through retry-backoff. Returns None if OK, else an error string."""
    from openai import OpenAI
    c = OpenAI(timeout=20.0, max_retries=0)
    try:
        c.chat.completions.create(model=os.environ.get("OPENAI_JUDGE_MODEL", "gpt-4.1"),
            temperature=0, max_tokens=1, messages=[{"role": "user", "content": "ok"}])
        return None
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"


def _run_parallel(fn, rows, label, max_workers=6):
    """Run fn over rows concurrently, preserving order, printing live N/total progress."""
    results = [None] * len(rows)
    done = fails = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(fn, r): i for i, r in enumerate(rows)}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                res = fut.result()
            except Exception:  # noqa: BLE001
                res = None
            results[i] = res
            done += 1
            if res is None or (isinstance(res, dict) and res.get("verdict") is None):
                fails += 1
            if done % 20 == 0 or done == len(rows):
                print(f"[reconcile] {label}: {done}/{len(rows)} done (fails={fails})",
                      file=sys.stderr, flush=True)
    return results


def _find_review(path):
    if path and os.path.exists(path):
        return path
    cands = glob.glob(os.path.expanduser("~/Downloads/review_results*.json"))
    if not cands:
        raise SystemExit("no review_results*.json found; pass --review PATH")
    return max(cands, key=os.path.getmtime)


def _ctx(row, max_turns=4):
    """Compact context string for a few-shot example or judge target."""
    hist = row.get("conversation_history") or []
    tail = hist[-max_turns:]
    hs = "\n".join(f"  {h[:240]}" for h in tail) if tail else "  (none)"
    return (f"PROBLEM: {row.get('problem','')[:240]}\n"
            f"FINAL ANSWER: {row.get('final_answer','')}\n"
            f"CONVERSATION (last turns):\n{hs}\n"
            f"CANDIDATE TUTOR MESSAGE: {row.get('candidate_message','')[:400]}")


def build_guidelines(decided, frozen_by_id):
    """Turn the reviewer's overturns + notes into a rules block + few-shot examples."""
    overturns = [x for x in decided if x.get("agree_with_gold") is False and x.get("user_verdict")]
    # transition frequency summary
    trans = Counter((x["gold_verdict"], x["user_verdict"]) for x in overturns)
    rules = ["The senior reviewer re-labeled a sample of this set. Their demonstrated tendencies:"]
    for (g, u), n in trans.most_common():
        rules.append(f"  - relabeled gold `{g}` -> `{u}`  ({n}x)")
    agree = [x for x in decided if x.get("agree_with_gold") is True]
    rules.append(f"They AGREED with gold on {len(agree)} items and overturned {len(overturns)}.")

    # few-shot: up to 2 per transition type, diverse
    by_trans = defaultdict(list)
    for x in overturns:
        by_trans[(x["gold_verdict"], x["user_verdict"])].append(x)
    shots = []
    # one concise example per transition type (prefer ones with a note), keeps prompt small
    for pairs in by_trans.values():
        pairs = sorted(pairs, key=lambda x: 0 if (x.get("notes") or "").strip() else 1)
        x = pairs[0]
        row = frozen_by_id.get(x["id"])
        if not row:
            continue
        note = (x.get("notes") or "").strip()
        shots.append(f"{_ctx(row)}\nGOLD SAID: {x['gold_verdict']}\n"
                     f"REVIEWER'S CORRECT VERDICT: {x['user_verdict']}"
                     + (f"\nREVIEWER NOTE: {note}" if note else ""))
    # one AGREE example so the judge doesn't over-flip
    for x in agree[:1]:
        row = frozen_by_id.get(x["id"])
        if row:
            shots.append(f"{_ctx(row)}\nGOLD SAID: {x['gold_verdict']}\n"
                         f"REVIEWER'S CORRECT VERDICT: {x['user_verdict']} (agreed with gold)")
    notes = [f"[{x['gold_verdict']}->{x.get('user_verdict')}] {x['notes'].strip()}"
             for x in decided if (x.get("notes") or "").strip()]
    return "\n".join(rules), shots, notes


def guided_judge(rows, rules, shots, notes):
    client = _client()
    model = os.environ.get("OPENAI_JUDGE_MODEL", "gpt-4.1")
    shot_block = "\n\n---\n\n".join(shots)
    note_block = "\n".join(f"  - {n}" for n in notes[:30])
    sysmsg = (SYSTEM_PROMPT
              + "\n\n=== REVIEWER'S OPERATIVE CRITERIA (inferred from their notes — apply PER ITEM) ===\n"
              + REVIEWER_CRITERIA
              + "\n\n=== their overturn frequencies ===\n" + rules
              + ("\n\nReviewer notes (verbatim):\n" + note_block if note_block else "")
              + "\n\nIMPORTANT: the reviewer only reviewed a PRE-FILTERED, suspicious sample (items an "
                "earlier judge had already flagged), so their sample skews toward overturning `adequate`. "
                "Do NOT assume every `adequate` is wrong. Apply the CRITERIA above to THIS item independently: "
                "keep `adequate` when the message genuinely builds on the student's specific work, correctly "
                "targets their actual mistake, and reveals neither the answer nor the pivotal step. Flip it "
                "only when a specific criterion is violated."
              + "\n\nBelow are worked examples of the reviewer's own labels. Return ONLY JSON "
                '{"verdict": <one of the 5>, "confidence": "high|medium|low", "why": "<one sentence citing the specific criterion>"}.')

    def one(row):
        user = ("WORKED EXAMPLES OF THE REVIEWER'S LABELS:\n\n" + shot_block
                + "\n\n=== TARGET (label the CANDIDATE TUTOR MESSAGE as the reviewer would) ===\n"
                + build_user_prompt(_input(row)))
        for _ in range(2):  # SDK already retries 429/5xx internally; this covers parse hiccups
            try:
                r = client.chat.completions.create(model=model, temperature=0,
                    response_format={"type": "json_object"},
                    messages=[{"role": "system", "content": sysmsg}, {"role": "user", "content": user}])
                o = json.loads(r.choices[0].message.content)
                v = o.get("verdict")
                if v in VERDICTS:
                    return {"verdict": v, "confidence": o.get("confidence", "medium"), "why": o.get("why", "")}
            except Exception:  # noqa: BLE001
                pass
        return {"verdict": None, "confidence": "low", "why": "[judge error]"}
    return _run_parallel(one, rows, "guided")


def verify(rows):
    """Independent taxonomy-only verdict (no calibration) for confidence tiering."""
    client = _client()
    model = os.environ.get("OPENAI_JUDGE_MODEL", "gpt-4.1")

    def one(row):
        for _ in range(2):
            try:
                r = client.chat.completions.create(model=model, temperature=0,
                    messages=[{"role": "system", "content": SYSTEM_PROMPT},
                              {"role": "user", "content": build_user_prompt(_input(row))}])
                return (parse_model_json(r.choices[0].message.content) or {}).get("verdict")
            except Exception:  # noqa: BLE001
                pass
        return None
    return _run_parallel(one, rows, "verify")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--review", default=None)
    ap.add_argument("--frozen", default=FROZEN)
    ap.add_argument("--out-dir", default="eval/gold/review")
    ap.add_argument("--limit", type=int, default=0, help="debug: cap guided-judge items")
    args = ap.parse_args()

    err = preflight()
    if err:
        print(f"[reconcile] PREFLIGHT FAILED — OpenAI is unusable: {err}\n"
              f"  → fix billing or set a working OPENAI_API_KEY, then re-run. Aborting before "
              f"spending calls.", file=sys.stderr)
        return 3

    rpath = _find_review(args.review)
    review = json.load(open(rpath))
    ritems = review.get("items", review)
    frozen = read_jsonl(args.frozen)
    frozen_by_id = {r["id"]: r for r in frozen}
    ruser = {x["id"]: x for x in ritems}

    decided = [x for x in ritems if x.get("user_verdict")]
    overturns = [x for x in decided if x.get("agree_with_gold") is False]
    rewrite_flags = [x for x in ritems if x.get("rewrite_unsafe")]
    print(f"[reconcile] review file: {rpath}", file=sys.stderr)
    print(f"[reconcile] reviewer decided {len(decided)} items "
          f"({len(overturns)} overturned gold, {len(rewrite_flags)} rewrites flagged unsafe)", file=sys.stderr)

    rules, shots, notes = build_guidelines(decided, frozen_by_id)
    print(f"[reconcile] built {len(shots)} few-shot examples from reviewer overturns/agreements", file=sys.stderr)

    # items the reviewer did NOT personally decide -> guided pass
    todo = [r for r in frozen if r["id"] not in {x["id"] for x in decided}]
    if args.limit:
        todo = todo[:args.limit]
    print(f"[reconcile] guided-judging {len(todo)} un-decided items with reviewer calibration ...", file=sys.stderr)
    props = guided_judge(todo, rules, shots, notes) if todo else []

    # assemble proposed final verdicts
    edits = []  # verdict changes vs gold
    for r, p in zip(todo, props):
        gv = r.get("gold_verdict")
        pv = p["verdict"]
        if pv and pv != gv:
            edits.append({"id": r["id"], "old": gv, "new": pv, "source": "guided-judge",
                          "confidence": p["confidence"], "why": p["why"]})
    # reviewer's own overturns are authoritative edits
    for x in overturns:
        edits.append({"id": x["id"], "old": x["gold_verdict"], "new": x["user_verdict"],
                      "source": "reviewer", "confidence": "user", "why": (x.get("notes") or "").strip()})

    # verification pass over guided-judge edits only
    gj_edit_rows = [frozen_by_id[e["id"]] for e in edits if e["source"] == "guided-judge"]
    vv = verify(gj_edit_rows) if gj_edit_rows else []
    vmap = {row["id"]: v for row, v in zip(gj_edit_rows, vv)}
    for e in edits:
        if e["source"] != "guided-judge":
            e["tier"] = "USER"
            continue
        v = vmap.get(e["id"])
        if v == e["new"]:
            e["tier"] = "CONFIRMED"      # independent verifier agrees with the new label
        elif v and v != e["old"]:
            e["tier"] = "SUPPORTED"      # verifier also thinks gold is wrong, differs on replacement
        else:
            e["tier"] = "TENTATIVE"      # verifier reverts to gold
        e["verifier_verdict"] = v

    # ---- report ----
    os.makedirs(args.out_dir, exist_ok=True)
    edits.sort(key=lambda e: {"USER": 0, "CONFIRMED": 1, "SUPPORTED": 2, "TENTATIVE": 3}[e["tier"]])
    json.dump({"review_file": rpath, "n_frozen": len(frozen), "reviewer_decided": len(decided),
               "edits": edits, "rewrite_flags": [x["id"] for x in rewrite_flags]},
              open(os.path.join(args.out_dir, "proposed_edits.json"), "w"), indent=2)

    tier_ct = Counter(e["tier"] for e in edits)
    trans_ct = Counter((e["old"], e["new"]) for e in edits)
    L = ["# Reconciliation — proposed edits to the golden set", "",
         f"Review file: `{rpath}`  ", f"Reviewer decided **{len(decided)}** items; "
         f"guided-judged **{len(todo)}** un-decided items with the reviewer's calibration.  ",
         f"Rewrites flagged unsafe: **{len(rewrite_flags)}**.", "",
         f"**Proposed verdict edits: {len(edits)}** of {len(frozen)} items "
         f"(unchanged: {len(frozen)-len(edits)}).", "",
         "Confidence tiers: **USER** = you decided it · **CONFIRMED** = guided-judge edit an independent "
         "taxonomy-only verifier also agrees with · **SUPPORTED** = verifier also rejects gold but proposes "
         "a different label · **TENTATIVE** = verifier reverts to gold (review by hand).", "",
         "| tier | count |", "|---|---|"]
    for t in ["USER", "CONFIRMED", "SUPPORTED", "TENTATIVE"]:
        L.append(f"| {t} | {tier_ct.get(t,0)} |")
    L += ["", "## Edit transitions (gold -> proposed)", "| gold | proposed | n |", "|---|---|---|"]
    for (o, n2), c in trans_ct.most_common():
        L.append(f"| {o} | {n2} | {c} |")
    L += ["", "## Full edit list (grouped by confidence)"]
    for t in ["USER", "CONFIRMED", "SUPPORTED", "TENTATIVE"]:
        te = [e for e in edits if e["tier"] == t]
        if not te:
            continue
        L.append(f"\n### {t} ({len(te)})")
        for e in te:
            vv_s = f" · verifier={e.get('verifier_verdict')}" if e["source"] == "guided-judge" else ""
            L.append(f"- `{e['id']}` **{e['old']} -> {e['new']}** ({e['confidence']}{vv_s}) — {e['why'][:200]}")
    with open(os.path.join(args.out_dir, "reconcile_report.md"), "w") as f:
        f.write("\n".join(L) + "\n")

    print(f"[reconcile] proposed {len(edits)} edits: {dict(tier_ct)}", file=sys.stderr)
    print(f"[reconcile] wrote {args.out_dir}/reconcile_report.md + proposed_edits.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
