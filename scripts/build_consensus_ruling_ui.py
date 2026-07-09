"""Build ONE HTML app to rule on the items where the cross-family jury genuinely split
(NO_CONSENSUS) plus your contested hand-labels. Three buckets in one file:
  - gold-override      : jury disagreed with YOUR hand-label (restored + flagged) — protect or change.
  - gold-noconsensus   : 3-way jury split on a gold item (current label kept).
  - train-noconsensus  : 3-way jury split on a training row (current label kept).

Each card shows the full problem + conversation + candidate message, the 3 model votes side-by-side,
and the current label highlighted. Rule with keys 1-5 (verdict) / c (keep current). Exports
consensus_rulings.json. Joins context from frozen_eval.jsonl (gold) + data/raw/v5.jsonl (train).
Mutates nothing.

Usage: python scripts/build_consensus_ruling_ui.py --out eval/gold/review/consensus/ruling.html
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from socratic_tutor.io_utils import read_jsonl  # noqa: E402
from socratic_tutor.schema import VERDICTS  # noqa: E402

CDIR = "eval/gold/review/consensus"
SHORT = {"openai-group/gpt-4.1": "gpt-4.1", "claude-group/claude-opus-4-8": "claude",
         "gemini-group/gemini-2.5-pro": "gemini"}

HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Rule on jury splits</title>
<style>
 :root{--bg:#0f1115;--card:#1a1d24;--mut:#8a91a0;--fg:#e7ebf0;--acc:#5b9dff;--ok:#3fb950;--bad:#f85149;--warn:#d29922;--stu:#243044;--tut:#2a2f24}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
 header{position:sticky;top:0;background:#0f1115ee;backdrop-filter:blur(6px);border-bottom:1px solid #2a2f3a;padding:10px 16px;z-index:5}
 header .row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
 .bar{height:6px;background:#2a2f3a;border-radius:4px;flex:1;min-width:120px;overflow:hidden}.bar>i{display:block;height:100%;background:var(--acc);width:0}
 .btn{background:#222836;border:1px solid #39415260;color:var(--fg);border-radius:7px;padding:6px 11px;cursor:pointer;font-size:13px}.btn:hover{border-color:var(--acc)}.btn.primary{background:var(--acc);color:#001}
 .filters{display:flex;gap:6px;flex-wrap:wrap}.filters .btn.on{background:var(--acc);color:#001}
 main{max-width:900px;margin:0 auto;padding:18px 16px 140px}
 .card{background:var(--card);border:1px solid #2a2f3a;border-radius:12px;padding:18px 20px}
 .meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:12px;color:var(--mut);margin-bottom:8px}
 .chip{border-radius:20px;padding:2px 10px;font-size:12px;font-weight:600;border:1px solid #39415260}
 .chip.b-gold-override{background:#3a1220;color:#ff9ec1;border-color:#d2006688}
 .chip.b-gold-noconsensus{background:#12203a;color:#9ecbff;border-color:#5b9dff88}
 .chip.b-train-noconsensus{background:#1c2412;color:#c9e08a;border-color:#7fa00088}
 h2.prob{font-size:17px;margin:6px 0 10px} .sol{color:#cdd3dd} details{margin:8px 0} summary{cursor:pointer;color:var(--mut);font-size:13px}
 .kv{font-size:12px;color:var(--mut);margin:4px 0}
 .chat{display:flex;flex-direction:column;gap:7px;margin:12px 0}
 .msg{max-width:82%;padding:8px 12px;border-radius:12px;white-space:pre-wrap;font-size:14px}
 .msg.student{align-self:flex-start;background:var(--stu);border-bottom-left-radius:3px}
 .msg.tutor{align-self:flex-end;background:var(--tut);border-bottom-right-radius:3px}.msg .who{font-size:11px;color:var(--mut);margin-bottom:2px}
 .cand{border:2px solid var(--acc);background:#12203a;border-radius:10px;padding:12px 14px;margin:14px 0}.cand .lbl{font-size:11px;letter-spacing:.05em;color:var(--acc);font-weight:700;margin-bottom:4px}
 .votes{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0;padding:12px 14px;border:1px solid #2a2f3a;border-radius:10px;background:#141821}
 .votes .box{flex:1;min-width:120px}.votes .lab{font-size:10px;letter-spacing:.06em;color:var(--mut);text-transform:uppercase}
 .votes .v{font-weight:700;font-size:14px;margin-top:2px}
 .cur{margin:10px 0;font-size:13px}.cur b{color:#ffd98a}
 .verdicts{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 6px}
 .vbtn{flex:1;min-width:150px;text-align:left;background:#222836;border:1px solid #39415260;border-radius:9px;padding:9px 12px;cursor:pointer}.vbtn:hover{border-color:var(--acc)}.vbtn .num{color:var(--acc);font-weight:700;margin-right:7px}
 .vbtn.current{box-shadow:0 0 0 1px #d2992288 inset}
 .vbtn.chosen{background:#13361b;border-color:var(--ok)}
 .tags{font-size:10px;color:var(--mut)}
 textarea{width:100%;background:#12151b;color:var(--fg);border:1px solid #2a2f3a;border-radius:8px;padding:8px;font:13px/1.4 inherit;margin-top:8px}
 .quick{display:flex;gap:8px;margin:8px 0} .status{font-size:12px;color:var(--mut)} kbd{background:#222836;border:1px solid #394152;border-radius:4px;padding:1px 6px;font-size:11px}
 .done{color:var(--ok);font-weight:700} .chg{color:var(--warn);font-weight:700}
</style></head><body>
<header><div class="row"><strong>Rule on jury splits</strong>
 <span class="status" id="counts"></span><div class="bar"><i id="prog"></i></div><span class="status" id="pos"></span>
 <div class="filters" id="filters"></div>
 <button class="btn" onclick="go(-1)">&larr;</button><button class="btn" onclick="go(1)">&rarr;</button>
 <button class="btn" onclick="document.getElementById('imp').click()">Import</button>
 <input id="imp" type="file" accept="application/json,.json" style="display:none" onchange="importJSON(this.files[0])">
 <button class="btn primary" onclick="exportJSON()">Export rulings</button></div>
 <div class="kv"><kbd>1-5</kbd> pick verdict &middot; <kbd>c</kbd> keep current &middot; <kbd>d</kbd> drop (bad data) &middot; <kbd>n</kbd> notes &middot; <kbd>&larr;/&rarr;</kbd> nav</div>
</header><main id="main"></main>
<script>
const ALL = __DATA__;
const VERDS = __VERDS__;
const KEY = "consensusruling:" + location.pathname;
let cur = 0, filter = "all", store = JSON.parse(localStorage.getItem(KEY) || "{}");
function DATA(){ return filter==="all" ? ALL : ALL.filter(d=>d.bucket===filter); }
function save(){ localStorage.setItem(KEY, JSON.stringify(store)); render(); }
function rec(id){ return store[id] || (store[id]={ruling:null,notes:""}); }
function esc(s){ return (s==null?"":(""+s)).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function ruledCount(){ return DATA().filter(d=>store[d.id]&&store[d.id].ruling).length; }
function bubbles(hist){ if(!hist||!hist.length) return '<div class="kv">(conversation start)</div>';
 return '<div class="chat">'+hist.map(h=>{const m=/^\s*[-*]?\s*(student|tutor)\s*:\s*(.*)$/is.exec(h);const who=m?m[1].toLowerCase():"tutor";const t=m?m[2]:h;
 return '<div class="msg '+(who==="student"?"student":"tutor")+'"><div class="who">'+(who==="student"?"Student":"Tutor")+'</div>'+esc(t)+'</div>';}).join("")+'</div>'; }
function setFilter(f){ filter=f; cur=0; render(); }
function renderFilters(){ const bs=["all","gold-override","gold-noconsensus","train-noconsensus"];
 document.getElementById("filters").innerHTML=bs.map(b=>{const n=b==="all"?ALL.length:ALL.filter(d=>d.bucket===b).length;
  return '<button class="btn '+(filter===b?"on":"")+'" onclick="setFilter(\''+b+'\')">'+b+' ('+n+')</button>';}).join(""); }
function render(){ const data=DATA(); if(cur>=data.length)cur=data.length-1; if(cur<0)cur=0;
 renderFilters(); const d=data[cur], r=rec(d.id);
 document.getElementById("counts").innerHTML='<b>'+ruledCount()+'</b>/'+data.length+' ruled';
 document.getElementById("pos").textContent='item '+(cur+1)+'/'+data.length;
 document.getElementById("prog").style.width=(100*ruledCount()/data.length)+'%';
 const voters={}; for(const m in d.votes){(voters[d.votes[m]]=voters[d.votes[m]]||[]).push(m);}
 const vbtns=VERDS.map((v,i)=>{let c="vbtn";if(v===d.current)c+=" current";if(r.ruling===v)c+=" chosen";
  let tag=[];if(v===d.current)tag.push("current");if(voters[v])tag.push(voters[v].join("+")+" voted");
  return '<div class="'+c+'" onclick="pick(\''+v+'\')"><span class="num">'+(i+1)+'</span>'+esc(v)+(tag.length?' <span class="tags">('+tag.join(" · ")+')</span>':'')+'</div>';}).join("");
 const votesHtml=Object.keys(d.votes).map(m=>'<div class="box"><div class="lab">'+esc(m)+'</div><div class="v">'+esc(d.votes[m]||"—")+'</div></div>').join("");
 const chosen=r.ruling?('<span class="'+(r.ruling===d.current?"done":"chg")+'">'+(r.ruling==="__DROP__"?"RULED: DROP (exclude row)":("RULED: "+esc(r.ruling)+(r.ruling===d.current?" (kept current)":" (CHANGED from "+esc(d.current)+")")))+'</span>'):'<span class="kv">not yet ruled</span>';
 const overrideNote = d.bucket==="gold-override" ? '<div class="cur">⚑ <b>Your hand-label</b>: '+esc(d.current)+' — the jury pushed <b>'+esc(d.jury_label)+'</b>. This is one of your protected labels; keep it unless you now disagree.</div>' : '';
 document.getElementById("main").innerHTML='<div class="card"><div class="meta">'
  +'<span class="chip b-'+d.bucket+'">'+esc(d.bucket)+'</span><span>'+esc(d.id)+'</span>'
  +(d.context_missing?'<span class="chip" style="color:#f85149">context missing</span>':'')+'</div>'
  +'<h2 class="prob">'+(d.problem?esc(d.problem):'<span style="color:#8a91a0;font-weight:400">(no problem statement — MRBench artifact; judge from the conversation, or drop)</span>')+'</h2>'
  +'<details><summary>correct solution</summary><div class="sol">'+esc(d.correct_solution)+'</div></details>'
  +(d.final_answer?'<div class="kv">final answer: '+esc(d.final_answer)+(d.key_step?' &middot; key step: '+esc(d.key_step):'')+'</div>':'')
  +bubbles(d.conversation_history)
  +'<div class="cand"><div class="lbl">CANDIDATE MESSAGE — the one being judged</div>'+esc(d.candidate_message)+'</div>'
  +overrideNote
  +'<div class="votes">'+votesHtml+'</div>'
  +'<div class="cur">current label: <b>'+esc(d.current)+'</b></div>'
  +'<div class="verdicts">'+vbtns+'</div>'
  +'<div class="quick"><button class="btn" onclick="pick(\''+d.current+'\')">c · keep current</button><button class="btn" style="border-color:#f8514966;color:#f85149" onclick="pick(\'__DROP__\')">d · drop (bad data)</button><span class="status" style="align-self:center">'+chosen+'</span></div>'
  +'<textarea id="notes" placeholder="notes (optional)" oninput="onNotes(this.value)">'+esc(r.notes)+'</textarea></div>';
}
function pick(v){ rec(DATA()[cur].id).ruling=v; save(); setTimeout(()=>go(1),140); }
function onNotes(v){ rec(DATA()[cur].id).notes=v; localStorage.setItem(KEY,JSON.stringify(store)); }
function go(d){ const data=DATA(); cur=Math.max(0,Math.min(data.length-1,cur+d)); render(); window.scrollTo(0,0); }
document.addEventListener("keydown",e=>{ if(e.target.tagName==="TEXTAREA"){if(e.key==="Escape")e.target.blur();return;}
 const d=DATA()[cur];
 if(e.key>="1"&&e.key<="5"){pick(VERDS[+e.key-1]);}else if(e.key==="c"){pick(d.current);}else if(e.key==="d"){pick("__DROP__");}
 else if(e.key==="n"){e.preventDefault();document.getElementById("notes").focus();}
 else if(e.key==="ArrowRight"||e.key==="j"){go(1);}else if(e.key==="ArrowLeft"||e.key==="k"){go(-1);}else if(e.key==="e"){exportJSON();}});
function importJSON(f){ if(!f)return; const fr=new FileReader(); fr.onload=()=>{let o;try{o=JSON.parse(fr.result);}catch(e){alert("bad JSON");return;}
 const items=o.items||o; let n=0; for(const x of items){if(x&&x.id&&(x.ruling||x.notes)){store[x.id]={ruling:x.ruling||null,notes:x.notes||""};n++;}} save(); alert("imported "+n);}; fr.readAsText(f); }
function exportJSON(){ const out={reviewed_at_local:new Date().toString(), ruled:ALL.filter(d=>store[d.id]&&store[d.id].ruling).length, total:ALL.length,
 items:ALL.map(d=>{const r=store[d.id]||{}; return {id:d.id,bucket:d.bucket,current:d.current,jury_label:d.jury_label||null,votes:d.votes,
  ruling:(r.ruling==="__DROP__"?null:(r.ruling||null)), drop:r.ruling==="__DROP__", changed:r.ruling?(r.ruling!=="__DROP__"&&r.ruling!==d.current):null, notes:r.notes||""};})};
 const b=new Blob([JSON.stringify(out,null,2)],{type:"application/json"});const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="consensus_rulings.json";a.click(); }
render();
</script></body></html>"""


def _card(rec, bucket, src, jury_label=None):
    row = src.get(rec["id"], {})
    return {
        "id": rec["id"], "bucket": bucket,
        "current": rec.get("current") or rec.get("your_label"),
        "jury_label": jury_label if jury_label is not None else rec.get("majority"),
        "votes": {SHORT.get(m, m): v for m, v in (rec.get("votes") or {}).items()},
        "problem": row.get("problem", ""), "correct_solution": row.get("correct_solution", ""),
        "final_answer": row.get("final_answer", ""), "key_step": row.get("key_step", ""),
        "conversation_history": row.get("conversation_history") or [],
        "candidate_message": row.get("candidate_message", ""),
        "context_missing": rec["id"] not in src,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frozen", default="eval/gold/frozen_eval.jsonl")
    ap.add_argument("--train", default="data/raw/v5.jsonl")
    ap.add_argument("--out", default=f"{CDIR}/ruling.html")
    a = ap.parse_args()

    gold = {r["id"]: r for r in read_jsonl(a.frozen)}
    train = {r["id"]: r for r in read_jsonl(a.train)}

    items = []
    for rec in read_jsonl(f"{CDIR}/frozen_human_overrides.jsonl"):
        rec2 = {"id": rec["id"], "current": rec.get("your_label"), "votes": rec.get("votes")}
        items.append(_card(rec2, "gold-override", gold, jury_label=rec.get("jury_label")))
    for rec in read_jsonl(f"{CDIR}/frozen_flagged.jsonl"):
        items.append(_card(rec, "gold-noconsensus", gold))
    for rec in read_jsonl(f"{CDIR}/train_flagged.jsonl"):
        items.append(_card(rec, "train-noconsensus", train))

    miss = [it["id"] for it in items if it["context_missing"]]
    if miss:
        print(f"[ruling] WARNING: {len(miss)} items missing source context: {miss[:8]}", file=sys.stderr)

    html = HTML.replace("__DATA__", json.dumps(items)).replace("__VERDS__", json.dumps(list(VERDICTS)))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        f.write(html)
    n = {"gold-override": 0, "gold-noconsensus": 0, "train-noconsensus": 0}
    for it in items:
        n[it["bucket"]] += 1
    print(f"[ruling] {len(items)} items ({n}) -> {a.out}", file=sys.stderr)
    print(f"\nOpen it:  open '{a.out}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
