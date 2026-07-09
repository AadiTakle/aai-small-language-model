"""Validate the calibrated LLM-as-judge against a BLIND human holdout.

  --prep    sample ~N fresh MRBench items the judge never saw (not in training/frozen/few-shot),
            stratified across verdicts; write holdout.jsonl + judge batches + a BLIND labeling UI
            (item only — no gold, no judge verdict). Claude subagents then label the batches 3x
            -> judge_run{1,2,3}.jsonl ({id, verdict}). You label blind in the UI -> user_labels.json.
  --score   read the 3 judge runs + user_labels.json -> agreement %, per-class, confusion,
            Cohen's kappa, binary-safety agreement, and judge self-consistency.

Usage:
  python scripts/judge_validation.py --prep --n 50
  python scripts/judge_validation.py --score --user ~/Downloads/user_labels.json
"""

import argparse
import glob
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from socratic_tutor.schema import VERDICTS  # noqa: E402
from build_frozen_eval import parse_history, map_verdict, final_answer  # noqa: E402

JV = "eval/gold/review/judge_val"
LEAK = {"gives_final_answer", "gives_away_key_step"}

_ROLE_RE = re.compile(r'(?:^|\n|###)\s*(?:Student|Assistant|Tutor)\s*:', re.I)


def is_malformed(cm):
    """A candidate tutor message should be a SINGLE turn. MRBench model responses (esp. Phi3)
    sometimes hallucinate a whole multi-turn dialogue — filter those out."""
    cm = cm or ""
    return "### " in cm or len(_ROLE_RE.findall(cm)) >= 2


def last_role(history):
    """Role of the last conversation turn. A clean item ends on a Student turn (the candidate
    is the tutor's reply); ending on Tutor is the 'ends-on-tutor' MRBench artifact."""
    if not history:
        return "none"
    m = re.match(r"\s*[-*]?\s*(student|tutor)\s*:", history[-1], re.I)
    return m.group(1).lower() if m else "other"


def prep(n, seed=0):
    data = json.load(open(config.DATA_DIR / "external" / "mrbench_v2.json"))
    trained = {r["id"][len("mrb-"):].rsplit("-", 1)[0] for r in read_jsonl("data/raw/real_mrbench.jsonl")}
    frozen_cand = {r["candidate_message"].strip() for r in read_jsonl("eval/gold/frozen_eval.jsonl")}
    train_blob = "\n".join(json.dumps(x) for f in ["data/raw/v4.jsonl", "data/raw/v5.jsonl",
                 "data/raw/real_mrbench.jsonl"] if os.path.exists(f) for x in read_jsonl(f))

    pool = defaultdict(list)  # mapped verdict -> fresh items (never seen)
    for c in data:
        if c["conversation_id"][:8] in trained:
            continue
        problem, history = parse_history(c["conversation_history"])
        if not problem:
            continue
        if last_role(history) != "student":
            continue  # skip 'ends-on-tutor' artifacts — the candidate must reply to a student turn
        sol = c.get("Ground_Truth_Solution", "")
        fa = final_answer(sol)
        for model, resp in c["anno_llm_responses"].items():
            cm = (resp["response"] or "").strip()
            v = map_verdict(resp["annotation"])
            if not cm or v is None or cm in frozen_cand or cm in train_blob or is_malformed(cm):
                continue
            pool[v].append({"id": f"jv-{c['conversation_id'][:8]}-{model}", "problem": problem,
                            "correct_solution": sol, "final_answer": fa, "key_step": "",
                            "conversation_history": history, "candidate_message": cm,
                            "mrb_mapped": v, "source": f"mrbench:{model}"})
    rng = random.Random(seed)
    for v in pool:
        rng.shuffle(pool[v])
    # stratify: over-weight the hard boundary (adequate/mismatched/vague), some leaks
    quota = {"mismatched_calibration": 0.28, "adequate": 0.24, "vague_unhelpful": 0.24,
             "gives_final_answer": 0.12, "gives_away_key_step": 0.12}
    items = []
    for v, frac in quota.items():
        take = min(round(n * frac), len(pool.get(v, [])))
        items += pool[v][:take]
    rng.shuffle(items)
    for i, it in enumerate(items):
        it["n"] = i

    os.makedirs(JV, exist_ok=True)
    write_jsonl(f"{JV}/holdout.jsonl", items)               # full, with mrb_mapped reference (NOT shown)
    # judge batch: inputs only (no reference verdict) — split into 2 batches
    jb = [{k: it.get(k) for k in ("id", "problem", "correct_solution", "final_answer",
           "key_step", "conversation_history", "candidate_message")} for it in items]
    half = (len(jb) + 1) // 2
    write_jsonl(f"{JV}/judge_batch_00.jsonl", jb[:half])
    write_jsonl(f"{JV}/judge_batch_01.jsonl", jb[half:])
    # blind UI (item only — no gold, no judge)
    with open(f"{JV}/holdout_blind.html", "w") as f:
        f.write(_blind_html(items))
    avail = {v: len(pool.get(v, [])) for v in VERDICTS}
    print(f"[jv-prep] sampled {len(items)} fresh items (avail per mapped verdict: {avail})", file=sys.stderr)
    print(f"[jv-prep] mapped-verdict mix: {dict(Counter(it['mrb_mapped'] for it in items))}", file=sys.stderr)
    print(f"[jv-prep] wrote {JV}/holdout.jsonl + judge_batch_00/01.jsonl + holdout_blind.html", file=sys.stderr)
    print(f"\nOpen the blind labeler:  open '{JV}/holdout_blind.html'")
    return 0


def _blind_html(items):
    data = [{k: it.get(k) for k in ("id", "n", "problem", "correct_solution", "final_answer",
             "key_step", "conversation_history", "candidate_message")} for it in items]
    tmpl = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Blind judge-validation labeling</title><style>
 :root{--bg:#0f1115;--card:#1a1d24;--mut:#8a91a0;--fg:#e7ebf0;--acc:#5b9dff;--ok:#3fb950;--stu:#243044;--tut:#2a2f24}
 *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
 header{position:sticky;top:0;background:#0f1115ee;backdrop-filter:blur(6px);border-bottom:1px solid #2a2f3a;padding:10px 16px;z-index:5}
 .row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.bar{height:6px;background:#2a2f3a;border-radius:4px;flex:1;min-width:120px;overflow:hidden}.bar>i{display:block;height:100%;background:var(--acc);width:0}
 .btn{background:#222836;border:1px solid #39415260;color:var(--fg);border-radius:7px;padding:6px 11px;cursor:pointer;font-size:13px}.btn:hover{border-color:var(--acc)}.btn.primary{background:var(--acc);color:#001}
 main{max-width:900px;margin:0 auto;padding:18px 16px 120px}.card{background:var(--card);border:1px solid #2a2f3a;border-radius:12px;padding:18px 20px}
 h2{font-size:17px;margin:6px 0 10px}details{margin:8px 0}summary{cursor:pointer;color:var(--mut);font-size:13px}.kv{font-size:12px;color:var(--mut)}
 .chat{display:flex;flex-direction:column;gap:7px;margin:12px 0}.msg{max-width:82%;padding:8px 12px;border-radius:12px;white-space:pre-wrap;font-size:14px}
 .msg.student{align-self:flex-start;background:var(--stu);border-bottom-left-radius:3px}.msg.tutor{align-self:flex-end;background:var(--tut);border-bottom-right-radius:3px}.msg .who{font-size:11px;color:var(--mut)}
 .cand{border:2px solid var(--acc);background:#12203a;border-radius:10px;padding:12px 14px;margin:14px 0}.cand .lbl{font-size:11px;letter-spacing:.05em;color:var(--acc);font-weight:700;margin-bottom:4px}
 .verdicts{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}.vbtn{flex:1;min-width:150px;text-align:left;background:#222836;border:1px solid #39415260;border-radius:9px;padding:9px 12px;cursor:pointer}.vbtn:hover{border-color:var(--acc)}.vbtn.chosen{background:#13361b;border-color:var(--ok)}.vbtn .num{color:var(--acc);font-weight:700;margin-right:7px}
 textarea{width:100%;background:#12151b;color:var(--fg);border:1px solid #2a2f3a;border-radius:8px;padding:8px;font:13px/1.4 inherit;margin-top:8px}
 kbd{background:#222836;border:1px solid #394152;border-radius:4px;padding:1px 6px;font-size:11px}
</style></head><body>
<header><div class="row"><strong>Blind labeling</strong><span class="kv" id="counts"></span><div class="bar"><i id="prog"></i></div><span class="kv" id="pos"></span>
 <button class="btn" onclick="go(-1)">&larr;</button><button class="btn" onclick="go(1)">&rarr;</button><button class="btn primary" onclick="exportJSON()">Export</button></div>
 <div class="kv"><kbd>1</kbd>-<kbd>5</kbd> pick the correct verdict &middot; <kbd>n</kbd> notes &middot; label WITHOUT any hint of the "right" answer — this is the ground truth we test the judge against.</div></header>
<main id="main"></main><script>
const DATA=__DATA__; const VERDS=__VERDS__;
const KEY="jvblind:"+location.pathname; let cur=0, store=JSON.parse(localStorage.getItem(KEY)||"{}");
function save(){localStorage.setItem(KEY,JSON.stringify(store));render();}
function rec(id){return store[id]||(store[id]={verdict:null,notes:""});}
function esc(s){return (s==null?"":(""+s)).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}
function done(){return DATA.filter(d=>store[d.id]&&store[d.id].verdict).length;}
function bubbles(h){if(!h||!h.length)return '<div class="kv">(conversation start)</div>';return '<div class="chat">'+h.map(x=>{const m=/^\s*[-*]?\s*(student|tutor)\s*:\s*(.*)$/is.exec(x);const w=m?m[1].toLowerCase():"tutor";const t=m?m[2]:x;return '<div class="msg '+(w==="student"?"student":"tutor")+'"><div class="who">'+(w==="student"?"Student":"Tutor")+'</div>'+esc(t)+'</div>';}).join("")+'</div>';}
function render(){const d=DATA[cur],r=rec(d.id);
 document.getElementById("counts").innerHTML="<b>"+done()+"</b>/"+DATA.length+" labeled";
 document.getElementById("pos").textContent="item "+(cur+1)+"/"+DATA.length;
 document.getElementById("prog").style.width=(100*done()/DATA.length)+"%";
 const vb=VERDS.map((v,i)=>'<div class="vbtn'+(r.verdict===v?" chosen":"")+'" onclick="pick(\''+v+'\')"><span class="num">'+(i+1)+'</span>'+esc(v)+'</div>').join("");
 document.getElementById("main").innerHTML='<div class="card"><div class="kv">item '+(d.n+1)+' &middot; '+esc(d.id)+'</div>'
  +'<h2>'+esc(d.problem)+'</h2><details><summary>correct solution</summary><div class="kv">'+esc(d.correct_solution)+'</div></details>'
  +(d.final_answer?'<div class="kv">final answer: '+esc(d.final_answer)+'</div>':'')+bubbles(d.conversation_history)
  +'<div class="cand"><div class="lbl">CANDIDATE MESSAGE — judge this</div>'+esc(d.candidate_message)+'</div>'
  +'<div class="kv">What is the correct verdict?</div><div class="verdicts">'+vb+'</div>'
  +'<textarea id="notes" placeholder="notes (optional)" oninput="onNotes(this.value)">'+esc(r.notes)+'</textarea></div>';}
function pick(v){rec(DATA[cur].id).verdict=v;save();setTimeout(()=>go(1),120);}
function onNotes(v){rec(DATA[cur].id).notes=v;localStorage.setItem(KEY,JSON.stringify(store));}
function go(d){cur=Math.max(0,Math.min(DATA.length-1,cur+d));render();scrollTo(0,0);}
document.addEventListener("keydown",e=>{if(e.target.tagName==="TEXTAREA"){if(e.key==="Escape")e.target.blur();return;}
 if(e.key>="1"&&e.key<="5")pick(VERDS[+e.key-1]);else if(e.key==="n"){e.preventDefault();document.getElementById("notes").focus();}
 else if(e.key==="ArrowRight"||e.key==="j")go(1);else if(e.key==="ArrowLeft"||e.key==="k")go(-1);else if(e.key==="e")exportJSON();});
function exportJSON(){const out={labeled:done(),total:DATA.length,items:DATA.map(d=>{const r=store[d.id]||{};return {id:d.id,verdict:r.verdict||null,notes:r.notes||""};})};
 const b=new Blob([JSON.stringify(out,null,2)],{type:"application/json"});const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="user_labels.json";a.click();}
render();</script></body></html>"""
    return tmpl.replace("__DATA__", json.dumps(data)).replace("__VERDS__", json.dumps(list(VERDICTS)))


def _kappa(pairs, labels):
    """Cohen's kappa between two raters over pairs of (a,b)."""
    n = len(pairs)
    if not n:
        return None
    po = sum(1 for a, b in pairs if a == b) / n
    ca = Counter(a for a, _ in pairs)
    cb = Counter(b for _, b in pairs)
    pe = sum((ca.get(l, 0) / n) * (cb.get(l, 0) / n) for l in labels)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0


def score(user_path):
    holdout = {r["id"]: r for r in read_jsonl(f"{JV}/holdout.jsonl")}
    runs = []
    for f in sorted(glob.glob(f"{JV}/judge_run[123].jsonl")):  # Claude runs only (not gpt5)
        runs.append({o["id"]: o.get("verdict") for o in read_jsonl(f) if o.get("verdict") in VERDICTS})
    if not runs:
        print("no judge_run[123].jsonl found", file=sys.stderr); return 2
    gpt5 = {}
    if os.path.exists(f"{JV}/judge_run_gpt5.jsonl"):
        gpt5 = {o["id"]: o.get("verdict") for o in read_jsonl(f"{JV}/judge_run_gpt5.jsonl")
                if o.get("verdict") in VERDICTS}
    user = {o["id"]: o.get("verdict") for o in json.load(open(user_path))["items"] if o.get("verdict") in VERDICTS}

    # judge majority verdict + self-consistency per item
    judge, selfcons = {}, []
    for iid in holdout:
        votes = [r[iid] for r in runs if iid in r]
        if not votes:
            continue
        top, cnt = Counter(votes).most_common(1)[0]
        judge[iid] = top
        selfcons.append(cnt / len(votes))

    ids = [i for i in holdout if i in judge and i in user]
    pairs = [(judge[i], user[i]) for i in ids]
    agree = sum(1 for a, b in pairs if a == b)
    bin_agree = sum(1 for a, b in pairs if (a in LEAK) == (b in LEAK))
    kappa = _kappa(pairs, VERDICTS)

    print(f"=== JUDGE vs BLIND HUMAN (n={len(ids)}) ===")
    print(f"  raw agreement: {agree}/{len(ids)} = {100*agree/len(ids):.0f}%")
    print(f"  Cohen's kappa: {kappa}   (>0.6 substantial, >0.8 near-perfect)")
    print(f"  binary safety (leak vs not) agreement: {bin_agree}/{len(ids)} = {100*bin_agree/len(ids):.0f}%")
    print(f"  judge self-consistency (mean across {len(runs)} runs): {sum(selfcons)/len(selfcons):.2f}")
    print("\n  where they DIVERGE (judge -> human):")
    for (j, u), c in Counter((a, b) for a, b in pairs if a != b).most_common():
        print(f"    {c:3d}  judge={j:24s} human={u}")
    print("\n  per-verdict agreement (by human label):")
    for v in VERDICTS:
        sub = [(j, u) for j, u in pairs if u == v]
        if sub:
            print(f"    {v:26s} {sum(1 for j,u in sub if j==u)}/{len(sub)} = {100*sum(1 for j,u in sub if j==u)/len(sub):.0f}%")
    if gpt5:
        gids = [i for i in ids if i in gpt5]
        gp = [(gpt5[i], user[i]) for i in gids]
        ga = sum(1 for a, b in gp if a == b)
        gbin = sum(1 for a, b in gp if (a in LEAK) == (b in LEAK))
        cg = sum(1 for i in gids if judge[i] == gpt5[i])
        print(f"\n=== GPT-5.5 judge vs BLIND HUMAN (n={len(gids)}) — cross-family ===")
        print(f"  raw agreement: {ga}/{len(gids)} = {100*ga/len(gids):.0f}%  |  kappa: {_kappa(gp, VERDICTS)}"
              f"  |  binary-safety: {100*gbin/len(gids):.0f}%")
        print(f"  Claude-judge vs GPT-5.5-judge: {cg}/{len(gids)} = {100*cg/len(gids):.0f}%")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prep", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--user", default=os.path.expanduser("~/Downloads/user_labels.json"))
    a = ap.parse_args()
    if a.prep:
        return prep(a.n)
    if a.score:
        return score(a.user)
    ap.error("pass --prep or --score")


if __name__ == "__main__":
    raise SystemExit(main())
