"""Build a self-contained HTML app for MANUAL human review of the golden eval set.

Runs an INDEPENDENT gpt-4.1 relabel over every item in the frozen eval set (same
SYSTEM_PROMPT + user prompt the loop's prune step uses), flags any disagreement with the
stored `gold_verdict` as 'contested', and renders a keyboard-driven review app
(chat-bubble cards, localStorage autosave, JSON export).

Review scope = ALL contested items (judge disagreed or judge errored) + a random
spot-check of items the judge agreed on. The reviewer always just picks the verdict they
believe is correct (keys 1-5); the app derives agree/disagree-with-gold from that.

Usage:
  python scripts/build_review.py --n-agreed 20 --out eval/gold/review/frozen_review.html
  python scripts/build_review.py --dry-run            # skip the API relabel (review all, no flags)
"""

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from socratic_tutor.io_utils import read_jsonl  # noqa: E402
from socratic_tutor.prompts import SYSTEM_PROMPT, build_user_prompt  # noqa: E402
from socratic_tutor.schema import VERDICTS, parse_model_json  # noqa: E402

FROZEN = "eval/gold/frozen_eval.jsonl"


def _input(row):
    return {x: row.get(x) for x in ("problem", "correct_solution", "conversation_history", "candidate_message")}


def relabel_all(rows):
    """Independent gpt-4.1 verdict per item (temp 0), with backoff. Returns list of
    {verdict, reasoning} aligned to rows; verdict None on persistent failure."""
    from openai import OpenAI
    client = OpenAI()
    model = os.environ.get("OPENAI_JUDGE_MODEL", "gpt-4.1")

    def one(row):
        delays = [0, 2, 5, 10, 20, 40]
        last = None
        for d in delays:
            if d:
                time.sleep(d)
            try:
                r = client.chat.completions.create(
                    model=model, temperature=0,
                    messages=[{"role": "system", "content": SYSTEM_PROMPT},
                              {"role": "user", "content": build_user_prompt(_input(row))}])
                o = parse_model_json(r.choices[0].message.content) or {}
                return {"verdict": o.get("verdict"), "reasoning": o.get("reasoning", "")}
            except Exception as e:  # noqa: BLE001
                last = e
        return {"verdict": None, "reasoning": f"[judge error: {last}]"}

    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(one, rows))


def build_items(rows, n_agreed, dry_run):
    judged = ([{"verdict": None, "reasoning": "(relabel skipped: --dry-run)"} for _ in rows]
              if dry_run else relabel_all(rows))
    contested, agreed = [], []
    for row, j in zip(rows, judged):
        jv = j.get("verdict")
        item = {
            "id": row["id"], "problem": row.get("problem", ""),
            "correct_solution": row.get("correct_solution", ""),
            "final_answer": str(row.get("final_answer", "")), "key_step": row.get("key_step", ""),
            "conversation_history": row.get("conversation_history") or [],
            "candidate_message": row.get("candidate_message", ""),
            "gold_verdict": row.get("gold_verdict"), "gold_rewrite": row.get("gold_rewrite", ""),
            "judge_verdict": jv, "judge_reasoning": j.get("reasoning", ""),
            "slice": row.get("slice", ""), "source": row.get("source", ""),
        }
        # contested = judge picked a valid verdict that differs from gold, OR judge errored
        if jv is None or (jv in VERDICTS and jv != row.get("gold_verdict")):
            item["section"] = "contested"
            contested.append(item)
        else:
            agreed.append(item)

    random.Random(0).shuffle(agreed)
    spot = agreed[:n_agreed]
    for it in spot:
        it["section"] = "spotcheck"
    # contested first (sorted by gold verdict for rhythm), then the agreed spot-check
    contested.sort(key=lambda x: (x["gold_verdict"] or ""))
    review = contested + spot
    for i, it in enumerate(review):
        it["n"] = i
    meta = {"total_frozen": len(rows), "contested": len(contested), "spotcheck": len(spot),
            "review_n": len(review), "dry_run": dry_run,
            "judge_errors": sum(1 for it in contested if it["judge_verdict"] is None),
            "verdicts": list(VERDICTS)}
    return review, meta


HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Golden-set manual review</title>
<style>
 :root{--bg:#0f1115;--card:#1a1d24;--mut:#8a91a0;--fg:#e7ebf0;--acc:#5b9dff;--ok:#3fb950;--bad:#f85149;--warn:#d29922;--stu:#243044;--tut:#2a2f24}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
 header{position:sticky;top:0;background:#0f1115ee;backdrop-filter:blur(6px);border-bottom:1px solid #2a2f3a;padding:10px 16px;z-index:5}
 header .row{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
 .bar{height:6px;background:#2a2f3a;border-radius:4px;flex:1;min-width:120px;overflow:hidden}
 .bar>i{display:block;height:100%;background:var(--acc);width:0}
 .btn{background:#222836;border:1px solid #39415260;color:var(--fg);border-radius:7px;padding:6px 11px;cursor:pointer;font-size:13px}
 .btn:hover{border-color:var(--acc)} .btn.primary{background:var(--acc);color:#001}
 main{max-width:900px;margin:0 auto;padding:18px 16px 120px}
 .card{background:var(--card);border:1px solid #2a2f3a;border-radius:12px;padding:18px 20px;margin-bottom:20px}
 .meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:12px;color:var(--mut);margin-bottom:8px}
 .chip{border-radius:20px;padding:2px 10px;font-size:12px;font-weight:600;border:1px solid #39415260}
 .chip.contested{background:#3a1d1d;color:#ffb4ac;border-color:#f8514966}
 .chip.spotcheck{background:#20242e;color:var(--mut)}
 .chip.gold{background:#20303f;color:#9ecbff;border-color:#5b9dff55}
 .chip.judge{background:#332a12;color:#ffd7a0;border-color:#d2992255}
 h2.prob{font-size:17px;margin:6px 0 10px} .sol{color:#cdd3dd} details{margin:8px 0} summary{cursor:pointer;color:var(--mut);font-size:13px}
 .kv{font-size:12px;color:var(--mut);margin:4px 0}
 .chat{display:flex;flex-direction:column;gap:7px;margin:12px 0}
 .msg{max-width:82%;padding:8px 12px;border-radius:12px;white-space:pre-wrap;font-size:14px}
 .msg.student{align-self:flex-start;background:var(--stu);border-bottom-left-radius:3px}
 .msg.tutor{align-self:flex-end;background:var(--tut);border-bottom-right-radius:3px}
 .msg .who{font-size:11px;color:var(--mut);margin-bottom:2px}
 .cand{border:2px solid var(--acc);background:#12203a;border-radius:10px;padding:12px 14px;margin:14px 0}
 .cand .lbl{font-size:11px;letter-spacing:.05em;color:var(--acc);font-weight:700;margin-bottom:4px}
 .judgebox{border:1px solid #d2992255;background:#241d0f;border-radius:10px;padding:10px 14px;margin:12px 0;font-size:13px}
 .rw{border:1px dashed #3fb95055;background:#112014;border-radius:10px;padding:10px 14px;margin:12px 0;font-size:13px}
 .verdicts{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 6px}
 .vbtn{flex:1;min-width:150px;text-align:left;background:#222836;border:1px solid #39415260;border-radius:9px;padding:9px 12px;cursor:pointer}
 .vbtn:hover{border-color:var(--acc)} .vbtn .num{color:var(--acc);font-weight:700;margin-right:7px}
 .vbtn.gold{border-color:#5b9dff88;box-shadow:0 0 0 1px #5b9dff33 inset}
 .vbtn.picked-ok{background:#13361b;border-color:var(--ok)} .vbtn.picked-bad{background:#3a1717;border-color:var(--bad)}
 .ctrls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:10px}
 textarea{width:100%;background:#12151b;color:var(--fg);border:1px solid #2a2f3a;border-radius:8px;padding:8px;font:13px/1.4 inherit;margin-top:8px}
 .status{font-size:12px;color:var(--mut)} .status b{color:var(--fg)}
 .toggle{cursor:pointer;border:1px solid #39415260;border-radius:7px;padding:6px 10px;font-size:13px}
 .toggle.on{background:#3a1717;border-color:var(--bad);color:#ffb4ac}
 kbd{background:#222836;border:1px solid #394152;border-radius:4px;padding:1px 6px;font-size:11px}
 .help{font-size:12px;color:var(--mut);margin-top:6px}
</style></head><body>
<header><div class="row">
  <strong>Golden-set review</strong>
  <span class="status" id="counts"></span>
  <div class="bar"><i id="prog"></i></div>
  <span class="status" id="pos"></span>
  <button class="btn" onclick="go(-1)">&larr; Prev</button>
  <button class="btn" onclick="go(1)">Next &rarr;</button>
  <button class="btn primary" onclick="exportJSON()">Export JSON</button>
</div>
<div class="help">Keys: <kbd>1</kbd>-<kbd>5</kbd> pick the verdict you think is correct (matching gold = agree) &middot; <kbd>u</kbd> unsure &middot; <kbd>r</kbd> rewrite leaks &middot; <kbd>n</kbd> notes &middot; <kbd>&larr;/&rarr;</kbd> or <kbd>j</kbd>/<kbd>k</kbd> navigate</div>
</header>
<main id="main"></main>
<script>
const DATA = __DATA__;
const META = __META__;
const VLABEL = {adequate:"adequate",gives_final_answer:"gives_final_answer",gives_away_key_step:"gives_away_key_step",mismatched_calibration:"mismatched_calibration",vague_unhelpful:"vague_unhelpful"};
const VERDS = META.verdicts;
const KEY = "goldreview:" + (location.pathname);
let cur = 0;
let store = JSON.parse(localStorage.getItem(KEY) || "{}");
function save(){ localStorage.setItem(KEY, JSON.stringify(store)); render(); }
function rec(id){ return store[id] || (store[id] = {user_verdict:null, unsure:false, rewrite_unsafe:false, notes:""}); }
function esc(s){ return (s==null?"":(""+s)).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function reviewedCount(){ return DATA.filter(d=>{const r=store[d.id]; return r && (r.user_verdict||r.unsure);}).length; }

function bubbles(hist){
  if(!hist||!hist.length) return '<div class="kv">(conversation start — no history)</div>';
  return '<div class="chat">'+hist.map(h=>{
    const m=/^\s*[-*]?\s*(student|tutor)\s*:\s*(.*)$/is.exec(h);
    const who = m? m[1].toLowerCase():"tutor"; const txt = m? m[2]:h;
    return '<div class="msg '+(who==="student"?"student":"tutor")+'"><div class="who">'+(who==="student"?"Student":"Tutor")+'</div>'+esc(txt)+'</div>';
  }).join("")+'</div>';
}

function render(){
  const d = DATA[cur]; const r = rec(d.id);
  document.getElementById("counts").innerHTML = "<b>"+reviewedCount()+"</b>/"+DATA.length+" reviewed &middot; "+META.contested+" contested, "+META.spotcheck+" spot-check";
  document.getElementById("pos").textContent = "item "+(cur+1)+"/"+DATA.length;
  document.getElementById("prog").style.width = (100*reviewedCount()/DATA.length)+"%";
  const nonAdequate = d.gold_verdict !== "adequate";
  const judge = d.judge_verdict==null
     ? '<div class="judgebox">⚠ independent judge <b>errored</b> on this item — verify carefully. '+esc(d.judge_reasoning)+'</div>'
     : (d.section==="contested"
        ? '<div class="judgebox">⚑ Independent gpt-4.1 labeled this <b>'+esc(d.judge_verdict)+'</b> (gold says <b>'+esc(d.gold_verdict)+'</b>).<br><span class="kv">judge reasoning: '+esc(d.judge_reasoning)+'</span></div>'
        : '');
  const rw = (nonAdequate && d.gold_rewrite) ? '<div class="rw"><b>Gold reference rewrite (should be SAFE):</b><br>'+esc(d.gold_rewrite)+'</div>' : "";
  const vbtns = VERDS.map((v,i)=>{
    let cls="vbtn"; if(v===d.gold_verdict) cls+=" gold";
    if(r.user_verdict===v) cls += (v===d.gold_verdict?" picked-ok":" picked-bad");
    return '<div class="'+cls+'" onclick="pick(\''+v+'\')"><span class="num">'+(i+1)+'</span>'+esc(VLABEL[v])+(v===d.gold_verdict?' <span class="kv">(gold)</span>':'')+'</div>';
  }).join("");
  const decided = r.user_verdict ? (r.user_verdict===d.gold_verdict?'<b style="color:var(--ok)">AGREES with gold</b>':'<b style="color:var(--bad)">DISAGREES → '+esc(r.user_verdict)+'</b>') : (r.unsure?'<b style="color:var(--warn)">unsure</b>':'<span class="kv">not yet judged</span>');
  document.getElementById("main").innerHTML =
   '<div class="card"><div class="meta">'
   +'<span class="chip '+d.section+'">'+d.section+'</span>'
   +'<span class="chip gold">gold: '+esc(d.gold_verdict)+'</span>'
   +'<span>'+esc(d.id)+'</span><span>&middot; '+esc(d.source)+'</span>'+(d.slice?'<span>&middot; '+esc(d.slice)+'</span>':'')+'</div>'
   +'<h2 class="prob">'+esc(d.problem)+'</h2>'
   +'<details><summary>correct solution (ground truth)</summary><div class="sol">'+esc(d.correct_solution)+'</div></details>'
   +(d.final_answer?'<div class="kv">final answer: '+esc(d.final_answer)+(d.key_step?' &middot; key step: '+esc(d.key_step):'')+'</div>':'')
   +bubbles(d.conversation_history)
   +'<div class="cand"><div class="lbl">CANDIDATE MESSAGE — the one being judged</div>'+esc(d.candidate_message)+'</div>'
   +judge+rw
   +'<div class="kv" style="margin-top:14px">Q: what is the CORRECT verdict for the candidate message?</div>'
   +'<div class="verdicts">'+vbtns+'</div>'
   +'<div class="ctrls">'
   +'<button class="toggle'+(r.unsure?" on":"")+'" onclick="toggleUnsure()">u · unsure</button>'
   +(nonAdequate?'<button class="toggle'+(r.rewrite_unsafe?" on":"")+'" onclick="toggleRW()">r · gold rewrite leaks</button>':'')
   +'<span class="status">'+decided+(r.rewrite_unsafe?' · <b style="color:var(--bad)">rewrite flagged</b>':'')+'</span></div>'
   +'<textarea id="notes" placeholder="notes (optional)" oninput="onNotes(this.value)">'+esc(r.notes)+'</textarea>'
   +'</div>';
}
function pick(v){ const d=DATA[cur]; const r=rec(d.id); r.user_verdict=v; r.unsure=false; save(); setTimeout(()=>go(1),120); }
function toggleUnsure(){ const r=rec(DATA[cur].id); r.unsure=!r.unsure; if(r.unsure) r.user_verdict=null; save(); }
function toggleRW(){ const r=rec(DATA[cur].id); r.rewrite_unsafe=!r.rewrite_unsafe; save(); }
function onNotes(v){ rec(DATA[cur].id).notes=v; localStorage.setItem(KEY, JSON.stringify(store)); }
function go(dir){ cur=Math.max(0,Math.min(DATA.length-1,cur+dir)); render(); window.scrollTo(0,0); }
document.addEventListener("keydown",e=>{
  if(e.target.tagName==="TEXTAREA"){ if(e.key==="Escape") e.target.blur(); return; }
  if(e.key>="1"&&e.key<="5"){ pick(VERDS[+e.key-1]); }
  else if(e.key==="u"){ toggleUnsure(); }
  else if(e.key==="r"){ toggleRW(); }
  else if(e.key==="n"){ e.preventDefault(); document.getElementById("notes").focus(); }
  else if(e.key==="ArrowRight"||e.key==="j"){ go(1); }
  else if(e.key==="ArrowLeft"||e.key==="k"){ go(-1); }
  else if(e.key==="e"){ exportJSON(); }
});
function exportJSON(){
  const out = { meta: META, reviewed_at_local: new Date().toString(),
    reviewed_count: reviewedCount(),
    items: DATA.map(d=>{ const r=store[d.id]||{}; return {
      id:d.id, section:d.section, gold_verdict:d.gold_verdict, judge_verdict:d.judge_verdict,
      user_verdict:r.user_verdict||null, unsure:!!r.unsure,
      agree_with_gold: r.user_verdict? (r.user_verdict===d.gold_verdict) : null,
      rewrite_unsafe:!!r.rewrite_unsafe, notes:r.notes||"" };})};
  const blob=new Blob([JSON.stringify(out,null,2)],{type:"application/json"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(blob);
  a.download="review_results.json"; a.click();
}
render();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frozen", default=FROZEN)
    ap.add_argument("--n-agreed", type=int, default=20)
    ap.add_argument("--out", default="eval/gold/review/frozen_review.html")
    ap.add_argument("--dry-run", action="store_true", help="skip the gpt-4.1 relabel (review all, no flags)")
    a = ap.parse_args()

    rows = read_jsonl(a.frozen)
    print(f"[review] {len(rows)} frozen items; {'DRY-RUN (no relabel)' if a.dry_run else 'relabeling with gpt-4.1 ...'}",
          file=sys.stderr, flush=True)
    review, meta = build_items(rows, a.n_agreed, a.dry_run)

    html = HTML.replace("__DATA__", json.dumps(review)).replace("__META__", json.dumps(meta))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        f.write(html)
    # also drop the machine-readable selection alongside, for reconciliation later
    with open(a.out.replace(".html", "_manifest.json"), "w") as f:
        json.dump({"meta": meta, "items": review}, f, indent=2)
    print(f"[review] contested={meta['contested']} (judge_errors={meta['judge_errors']}) "
          f"+ spotcheck={meta['spotcheck']} → review_n={meta['review_n']}", file=sys.stderr)
    print(f"[review] wrote {a.out} (+ _manifest.json)", file=sys.stderr)
    print(f"\nOpen it:  open '{a.out}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
