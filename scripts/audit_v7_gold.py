#!/usr/bin/env python3
"""Is v7 actually better and the frozen GOLD just poor? Adjudicate the v6-vs-v7
disagreements with an INDEPENDENT blind jury.

On every frozen item where sft_v6 and v7 give different (valid) verdicts, a 2-model jury
(Claude-opus + gpt-4o) re-judges BLIND: current decision-tree SYSTEM_PROMPT, no gold shown,
no model identities. Neither juror produced v7's labels (those came from gpt-5.5), so this is
independent of v7's training signal. We then ask, on the items where both jurors AGREE
(confident rulings):
  - does the jury match v7 more than sft_v6?  (v7 the better model?)
  - does the jury match the frozen GOLD?       (is the gold the weak yardstick?)
Focus on "v7-LOST" items (gold==v6, v7 differs): if the jury backs v7 there, the gold is poor.

This can DISCONFIRM too: if the jury backs gold/v6, v7 is genuinely worse.

Usage: python scripts/audit_v7_gold.py
"""

import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl  # noqa: E402
from socratic_tutor.prompts import SYSTEM_PROMPT, build_user_prompt  # noqa: E402
from socratic_tutor.schema import VERDICTS, parse_model_json  # noqa: E402

RES = str(config.RESULTS_DIR / "v7_frozen.json")
FROZEN = str(config.GOLD_DIR / "frozen_eval.jsonl")
OUT = str(config.RESULTS_DIR / "v7_gold_audit")
ARBITERS = {"claude": "claude-group/claude-opus-4-8", "gpt4o": "openai-group/gpt-4o"}


def _input(row):
    return {k: row.get(k) for k in ("problem", "correct_solution", "conversation_history", "candidate_message")}


def blind_judge(model, rows):
    from openai import OpenAI
    client = OpenAI(timeout=90, max_retries=4)

    def one(row):
        msgs = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(_input(row))}]
        for kw in ({"temperature": 0}, {}):  # some gateway models reject temperature
            try:
                r = client.chat.completions.create(model=model, messages=msgs, **kw)
                v = (parse_model_json(r.choices[0].message.content or "") or {}).get("verdict")
                if v in VERDICTS:
                    return v
            except Exception:  # noqa: BLE001
                continue
        return None

    with ThreadPoolExecutor(max_workers=6) as ex:
        out = list(ex.map(one, rows))
    print(f"[audit] {model}: {sum(v is not None for v in out)}/{len(rows)} judged", file=sys.stderr)
    return out


def _tally(subset, label):
    n = len(subset)
    v7 = sum(1 for d in subset if d["jury"] == d["v7"])
    v6 = sum(1 for d in subset if d["jury"] == d["v6"])
    gold = sum(1 for d in subset if d["jury"] == d["gold"])
    print(f"  {label} (n={n}): jury matches v7={v7}  sft_v6={v6}  frozen_gold={gold}")
    return {"n": n, "jury_v7": v7, "jury_v6": v6, "jury_gold": gold}


def main():
    res = json.load(open(RES))
    frozen = {r["id"]: r for r in read_jsonl(FROZEN)}
    pi6 = {d["id"]: d for d in res["sft_v6"]["per_item"]}
    pi7 = {d["id"]: d for d in res["v7"]["per_item"]}

    dis = []
    for i in pi7:
        g, v7 = pi7[i]["gold"], pi7[i]["pred"]
        v6 = pi6.get(i, {}).get("pred")
        if v6 != v7 and v6 is not None and v7 is not None:
            dis.append({"id": i, "gold": g, "v6": v6, "v7": v7, "row": frozen[i]})
    print(f"[audit] {len(dis)} valid v6!=v7 disagreements", file=sys.stderr)

    rows = [d["row"] for d in dis]
    for name, model in ARBITERS.items():
        verdicts = blind_judge(model, rows)
        for d, v in zip(dis, verdicts):
            d[name] = v

    for d in dis:
        d["jury"] = d["claude"] if (d["claude"] == d["gpt4o"] and d["claude"] is not None) else None
    conf = [d for d in dis if d["jury"] is not None]
    print(f"[audit] jury CONFIDENT (both arbiters agree) on {len(conf)}/{len(dis)}\n", file=sys.stderr)

    print("=== independent-jury adjudication of the disagreements ===")
    t_all = _tally(conf, "ALL confident disagreements")
    lost = [d for d in conf if d["gold"] == d["v6"] and d["v7"] != d["gold"]]
    t_lost = _tally(lost, "v7-LOST items (gold==v6, v7 differs)")
    won = [d for d in conf if d["gold"] == d["v7"] and d["v6"] != d["gold"]]
    t_won = _tally(won, "v7-WON items (gold==v7, v6 differs)")

    gold_poor = [d for d in lost if d["jury"] == d["v7"]]      # jury backs v7 over gold => gold poor
    v7_wrong = [d for d in lost if d["jury"] == d["gold"]]     # jury backs gold => v7 wrong

    # report
    L = ["# v7 vs frozen-gold audit — independent blind jury", "",
         f"Jury: {', '.join(ARBITERS.values())} (blind: decision-tree prompt, no gold, no identities; "
         f"neither produced v7's gpt-5.5 labels).", "",
         f"Valid v6!=v7 disagreements: **{len(dis)}**; jury confident (both agree): **{len(conf)}**.", "",
         "| subset | n | jury=v7 | jury=sft_v6 | jury=frozen_gold |", "|---|---|---|---|---|",
         f"| all confident disagreements | {t_all['n']} | {t_all['jury_v7']} | {t_all['jury_v6']} | {t_all['jury_gold']} |",
         f"| v7-LOST (gold==v6) | {t_lost['n']} | {t_lost['jury_v7']} | {t_lost['jury_v6']} | {t_lost['jury_gold']} |",
         f"| v7-WON (gold==v7) | {t_won['n']} | {t_won['jury_v7']} | {t_won['jury_v6']} | {t_won['jury_gold']} |", "",
         f"**On v7-LOST items the jury backs v7 (gold poor) in {len(gold_poor)}, backs gold (v7 wrong) in {len(v7_wrong)}.**", "",
         "## Clearest 'gold looks poor' cases (v7-lost, jury unanimously sided with v7)"]
    for d in gold_poor[:12]:
        r = d["row"]
        L.append(f"\n- `{d['id']}` — gold=`{d['gold']}` · v7=`{d['v7']}` · jury=`{d['jury']}`\n"
                 f"    problem: {(r.get('problem') or '')[:160]}\n"
                 f"    candidate: {(r.get('candidate_message') or '')[:240]}")
    md = "\n".join(L) + "\n"
    with open(OUT + ".md", "w") as f:
        f.write(md)
    json.dump([{k: d[k] for k in ("id", "gold", "v6", "v7", "claude", "gpt4o", "jury")} for d in dis],
              open(OUT + ".json", "w"), indent=2)

    print(md)
    print(f"[audit] wrote {OUT}.md / {OUT}.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
