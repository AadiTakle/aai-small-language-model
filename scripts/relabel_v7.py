#!/usr/bin/env python3
"""Decision-tree relabel of the QUALITY-AXIS training verdicts (v6 -> v7).

The safety axis (gives_final_answer / gives_away_key_step) is objective and already
reliable (85-100% inter-judge agreement per docs/rubric_evaluation.md), so it is left
untouched. Nearly all remaining verdict error lives on the quality axis (adequate /
mismatched_calibration / vague_unhelpful), where agreement is low. This re-adjudicates
ONLY those rows against the explicit decision tree now baked into SYSTEM_PROMPT, using
the same gateway-judge machinery as reconcile_review.py:

  guided pass : SYSTEM_PROMPT (with decision tree) + REVIEWER_CRITERIA
  verify pass : SYSTEM_PROMPT only (independent; taxonomy+tree, no criteria)
  A label is flipped ONLY when both passes agree on the SAME new verdict (CONFIRMED) --
  conservative, so boundaries get sharpened without injecting judge noise. Rows where
  the two passes disagree keep their v6 label.

Non-adequate flips get a freshly regenerated reasoning + SAFE rewrite, leak-gated with
rubric._heuristic_safe; if regeneration leaks or fails, the row keeps its v6 label.

Usage:
  python scripts/relabel_v7.py                # full run -> data/raw/v7.jsonl
  python scripts/relabel_v7.py --limit 40     # debug on a small slice
"""

import argparse
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.prompts import SYSTEM_PROMPT, build_user_prompt  # noqa: E402
from socratic_tutor.schema import VERDICTS, parse_model_json  # noqa: E402
from socratic_tutor.rubric import _heuristic_safe  # noqa: E402
from reconcile_review import REVIEWER_CRITERIA  # noqa: E402

SRC = "data/raw/v6_consensus.jsonl"
OUT = "data/raw/v7.jsonl"
REPORT = "eval/results/v7_relabel_report.md"
DROPPED = "eval/results/v7_relabel_dropped.json"
QUALITY = {"adequate", "mismatched_calibration", "vague_unhelpful"}
MODEL = os.environ.get("OPENAI_JUDGE_MODEL", "gpt-4.1")


def _input(row):
    return {x: row.get(x) for x in ("problem", "correct_solution", "conversation_history", "candidate_message")}


def _client():
    from openai import OpenAI
    return OpenAI(timeout=90.0, max_retries=4)


def _gate_call(client, sysmsg, usermsg, temp=0.0):
    """One gateway chat call. OPENAI_JUDGE_MODEL (gpt-5.5) is a reasoning model behind the
    TrueFoundry gateway: never cap max_tokens (it needs a reasoning budget to finish), and
    some gateway models reject `temperature`, so fall back to omitting it. No response_format
    — we parse the JSON out of the text. Mirrors scripts/report_score.py:openai_gen."""
    msgs = [{"role": "system", "content": sysmsg}, {"role": "user", "content": usermsg}]
    for kw in ({"temperature": temp}, {}):
        try:
            r = client.chat.completions.create(model=MODEL, messages=msgs, **kw)
            return r.choices[0].message.content or ""
        except Exception:  # noqa: BLE001
            continue
    return ""


def preflight():
    """Fail-fast probe so a dead key aborts before spending a run's worth of calls.
    No max_tokens cap — a reasoning model can't complete a 1-token budget (that 400s)."""
    txt = _gate_call(_client(), "You are a helpful assistant.", "Reply with the single word OK.")
    return None if txt.strip() else "empty response from gateway (check keys / model route)"


def _run_parallel(fn, rows, label, max_workers=6):
    results = [None] * len(rows)
    done = fails = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(fn, r): i for i, r in enumerate(rows)}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                results[i] = fut.result()
            except Exception:  # noqa: BLE001
                results[i] = None
            done += 1
            if results[i] is None:
                fails += 1
            if done % 25 == 0 or done == len(rows):
                print(f"[v7] {label}: {done}/{len(rows)} (fails={fails})", file=sys.stderr, flush=True)
    return results


def guided_judge(rows):
    client = _client()
    sysmsg = (SYSTEM_PROMPT
              + "\n\n=== OPERATIVE CRITERIA (use to disambiguate while applying the decision procedure above) ===\n"
              + REVIEWER_CRITERIA
              + '\n\nReturn ONLY JSON {"verdict": <one of the 5>, "confidence": "high|medium|low", '
                '"why": "<one sentence citing the specific decision-tree step / criterion>"}.')

    def one(row):
        content = _gate_call(client, sysmsg, build_user_prompt(_input(row)))
        o = parse_model_json(content) or {}
        if o.get("verdict") in VERDICTS:
            return {"verdict": o["verdict"], "confidence": o.get("confidence", "medium"),
                    "why": o.get("why", "")}
        return None
    return _run_parallel(one, rows, "guided")


def verify_judge(rows):
    """Independent verdict — SYSTEM_PROMPT (with tree) only, no criteria. Agreement = robust."""
    client = _client()

    def one(row):
        content = _gate_call(client, SYSTEM_PROMPT, build_user_prompt(_input(row)))
        return (parse_model_json(content) or {}).get("verdict")
    return _run_parallel(one, rows, "verify")


def regen_target(row, new_verdict):
    """Regenerate {reasoning, rewritten_message} for a non-adequate flip (leak-gated by caller)."""
    client = _client()
    sysmsg = (SYSTEM_PROMPT
              + "\n\n=== OPERATIVE CRITERIA (what makes a rewrite SAFE) ===\n" + REVIEWER_CRITERIA
              + f"\n\nThe correct verdict for this row is `{new_verdict}`. Produce the corrected target:\n"
                "- reasoning: one-to-two sentences justifying that verdict, citing a SPECIFIC detail.\n"
                "- rewritten_message: a SAFE Socratic hint that NEVER states the final answer and NEVER hands "
                "over the key step; points the student to WHERE their mistake is and asks them to fix it; grounded "
                "in their most recent message.\n"
                'Return ONLY JSON {"reasoning": "...", "rewritten_message": "..."}.')
    content = _gate_call(client, sysmsg, build_user_prompt(_input(row)))
    o = parse_model_json(content) or {}
    rw = (o.get("rewritten_message") or "").strip()
    rs = (o.get("reasoning") or "").strip()
    return {"reasoning": rs, "rewritten_message": rw} if (rw and rs) else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--limit", type=int, default=0, help="debug: cap quality rows judged")
    a = ap.parse_args()

    err = preflight()
    if err:
        print(f"[v7] PREFLIGHT FAILED — gateway unusable: {err}\n  fix key/billing and re-run.", file=sys.stderr)
        return 3

    rows = read_jsonl(a.src)
    quality = [r for r in rows if r.get("verdict") in QUALITY]
    if a.limit:
        quality = quality[:a.limit]
    qids = {r["id"] for r in quality}
    print(f"[v7] {len(rows)} rows; re-judging {len(quality)} quality-axis rows "
          f"(safety-axis left untouched)", file=sys.stderr)

    guided = guided_judge(quality)
    verify = verify_judge(quality)
    gv = {r["id"]: (guided[i], verify[i]) for i, r in enumerate(quality)}

    out = []
    n_flip_adeq = n_flip_regen = n_drop = n_keep = 0
    trans = Counter()
    dropped = []
    for row in rows:
        if row["id"] not in qids:
            out.append(row)  # safety-axis untouched
            continue
        g, v = gv[row["id"]]
        old = row.get("verdict")
        # CONFIRMED flip = guided proposes a new label AND the independent verify pass agrees
        if not g or g["verdict"] == old or v != g["verdict"]:
            out.append(row); n_keep += 1
            continue
        new = g["verdict"]
        nr = dict(row)
        nr["verdict"] = new
        if new == "adequate":
            nr["reasoning"] = g.get("why") or row.get("reasoning") or ""
            nr["rewritten_message"] = None
            nr["relabeled"] = "v7_to_adequate"
            out.append(nr); n_flip_adeq += 1; trans[(old, new)] += 1
        else:
            tgt = regen_target(row, new)
            if not tgt or not _heuristic_safe(row, {"rewritten_message": tgt["rewritten_message"]}):
                out.append(row); n_drop += 1
                dropped.append({"id": row.get("id"), "old": old, "new": new,
                                "reason": "no_regen" if not tgt else "rewrite_leaks"})
                continue
            nr["reasoning"] = tgt["reasoning"]
            nr["rewritten_message"] = tgt["rewritten_message"]
            nr["relabeled"] = "v7_regenerated"
            out.append(nr); n_flip_regen += 1; trans[(old, new)] += 1

    write_jsonl(a.out, out)

    L = ["# v7 decision-tree relabel report", "",
         f"Source: `{a.src}` ({len(rows)} rows) | Judge model: `{MODEL}`  ",
         f"Quality-axis rows re-judged: **{len(quality)}** (safety-axis left untouched).", "",
         f"CONFIRMED flips applied: **{n_flip_adeq + n_flip_regen}** "
         f"(→adequate {n_flip_adeq}, →non-adequate regenerated {n_flip_regen}).  ",
         f"Kept (no confirmed flip): {n_keep}. Dropped (regen failed/leaked → kept v6 label): {n_drop}.", "",
         "## Flip transitions (old → new)", "| old | new | n |", "|---|---|---|"]
    for (o, n2), c in trans.most_common():
        L.append(f"| {o} | {n2} | {c} |")
    L += ["", f"New verdict distribution: `{dict(Counter(r['verdict'] for r in out))}`"]
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        f.write("\n".join(L) + "\n")
    if dropped:
        json.dump(dropped, open(DROPPED, "w"), indent=2)

    print(f"[v7] wrote {len(out)} rows -> {a.out}", file=sys.stderr)
    print(f"[v7] flips: ->adequate {n_flip_adeq}, ->non-adequate {n_flip_regen}, "
          f"kept {n_keep}, dropped {n_drop}", file=sys.stderr)
    print(f"[v7] transitions: {dict(trans)}", file=sys.stderr)
    print(f"[v7] report -> {REPORT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
