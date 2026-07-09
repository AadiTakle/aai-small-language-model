"""Build a focused HTML app to RULE on the borderline reconcile edits (SUPPORTED + TENTATIVE
tiers from proposed_edits.json) — the ones that flip only under the reviewer's strict leak
standard. Each card shows the full item + GOLD vs PROPOSED vs the neutral strict read, and
lets the reviewer accept the proposal, keep gold, or pick another verdict (keys p / g / 1-5).
Exports ruling_results.json. Reads context from frozen_eval.jsonl. Mutates nothing.

Usage: python scripts/build_ruling_ui.py --tiers SUPPORTED,TENTATIVE --out eval/gold/review/ruling.html
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from socratic_tutor.io_utils import read_jsonl  # noqa: E402
from socratic_tutor.schema import VERDICTS  # noqa: E402

EDITS = "eval/gold/review/proposed_edits.json"
FROZEN = "eval/gold/frozen_eval.jsonl"

HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Rule on borderline edits</title>
<style>
 :root{--bg:#0f1115;--card:#1a1d24;--mut:#8a91a0;--fg:#e7ebf0;--acc:#5b9dff;--ok:#3fb950;--bad:#f85149;--warn:#d29922;--stu:#243044;--tut:#2a2f24}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
 header{position:sticky;top:0;background:#0f1115ee;backdrop-filter:blur(6px);border-bottom:1px solid #2a2f3a;padding:10px 16px;z-index:5}
 header .row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
 .bar{height:6px;background:#2a2f3a;border-radius:4px;flex:1;min-width:120px;overflow:hidden}.bar>i{display:block;height:100%;background:var(--acc);width:0}
 .btn{background:#222836;border:1px solid #39415260;color:var(--fg);border-radius:7px;padding:6px 11px;cursor:pointer;font-size:13px}.btn:hover{border-color:var(--acc)}.btn.primary{background:var(--acc);color:#001}
 main{max-width:900px;margin:0 auto;padding:18px 16px 140px}
 .card{background:var(--card);border:1px solid #2a2f3a;border-radius:12px;padding:18px 20px}
 .meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:12px;color:var(--mut);margin-bottom:8px}
 .chip{border-radius:20px;padding:2px 10px;font-size:12px;font-weight:600;border:1px solid #39415260}
 .chip.tier{background:#3a2a12;color:#ffc98a;border-color:#d2660088}
 h2.prob{font-size:17px;margin:6px 0 10px} .sol{color:#cdd3dd} details{margin:8px 0} summary{cursor:pointer;color:var(--mut);font-size:13px}
 .kv{font-size:12px;color:var(--mut);margin:4px 0}
 .chat{display:flex;flex-direction:column;gap:7px;margin:12px 0}
 .msg{max-width:82%;padding:8px 12px;border-radius:12px;white-space:pre-wrap;font-size:14px}
 .msg.student{align-self:flex-start;background:var(--stu);border-bottom-left-radius:3px}
 .msg.tutor{align-self:flex-end;background:var(--tut);border-bottom-right-radius:3px}.msg .who{font-size:11px;color:var(--mut);margin-bottom:2px}
 .cand{border:2px solid var(--acc);background:#12203a;border-radius:10px;padding:12px 14px;margin:14px 0}.cand .lbl{font-size:11px;letter-spacing:.05em;color:var(--acc);font-weight:700;margin-bottom:4px}
 .decision{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0;padding:12px 14px;border:1px solid #2a2f3a;border-radius:10px;background:#141821}
 .decision .box{flex:1;min-width:150px}.decision .lab{font-size:10px;letter-spacing:.06em;color:var(--mut);text-transform:uppercase}
 .decision .v{font-weight:700;font-size:15px} .v.gold{color:#9ecbff}.v.prop{color:#ffc98a}.v.neu{color:#c9d1d9}
 .why{font-size:13px;color:#cdd3dd;margin-top:8px;border-left:2px solid #d2992255;padding-left:10px}
 .verdicts{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 6px}
 .vbtn{flex:1;min-width:150px;text-align:left;background:#222836;border:1px solid #39415260;border-radius:9px;padding:9px 12px;cursor:pointer}.vbtn:hover{border-color:var(--acc)}.vbtn .num{color:var(--acc);font-weight:700;margin-right:7px}
 .vbtn.gold{box-shadow:0 0 0 1px #5b9dff55 inset}.vbtn.prop{box-shadow:0 0 0 1px #d2992288 inset}
 .vbtn.chosen{background:#13361b;border-color:var(--ok)}
 .tags{font-size:10px;color:var(--mut)} textarea{width:100%;background:#12151b;color:var(--fg);border:1px solid #2a2f3a;border-radius:8px;padding:8px;font:13px/1.4 inherit;margin-top:8px}
 .quick{display:flex;gap:8px;margin:8px 0} .status{font-size:12px;color:var(--mut)} kbd{background:#222836;border:1px solid #394152;border-radius:4px;padding:1px 6px;font-size:11px}
 .done{color:var(--ok);font-weight:700}
</style></head><body>
<header><div class="row"><strong>Rule on borderline edits</strong>
 <span class="status" id="counts"></span><div class="bar"><i id="prog"></i></div><span class="status" id="pos"></span>
 <button class="btn" onclick="go(-1)">&larr;</button><button class="btn" onclick="go(1)">&rarr;</button>
 <button class="btn" onclick="document.getElementById('imp').click()">Import</button>
 <input id="imp" type="file" accept="application/json,.json" style="display:none" onchange="importJSON(this.files[0])">
 <button class="btn primary" onclick="exportJSON()">Export rulings</button></div>
 <div class="kv"><kbd>p</kbd> accept proposed &middot; <kbd>g</kbd> keep gold &middot; <kbd>1-5</kbd> pick verdict &middot; <kbd>n</kbd> notes &middot; <kbd>&larr;/&rarr;</kbd> nav</div>
</header><main id="main"></main>
<script>
const DATA = __DATA__;
const VERDS = __VERDS__;
const KEY = "goldruling:" + location.pathname;
let cur = 0, store = JSON.parse(localStorage.getItem(KEY) || "{}");
function save(){ localStorage.setItem(KEY, JSON.stringify(store)); render(); }
function rec(id){ return store[id] || (store[id]={ruling:null,notes:""}); }
function esc(s){ return (s==null?"":(""+s)).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function ruledCount(){ return DATA.filter(d=>store[d.id]&&store[d.id].ruling).length; }
function bubbles(hist){ if(!hist||!hist.length) return '<div class="kv">(conversation start)</div>';
 return '<div class="chat">'+hist.map(h=>{const m=/^\s*[-*]?\s*(student|tutor)\s*:\s*(.*)$/is.exec(h);const who=m?m[1].toLowerCase():"tutor";const t=m?m[2]:h;
 return '<div class="msg '+(who==="student"?"student":"tutor")+'"><div class="who">'+(who==="student"?"Student":"Tutor")+'</div>'+esc(t)+'</div>';}).join("")+'</div>'; }
function render(){ const d=DATA[cur], r=rec(d.id);
 document.getElementById("counts").innerHTML='<b>'+ruledCount()+'</b>/'+DATA.length+' ruled';
 document.getElementById("pos").textContent='item '+(cur+1)+'/'+DATA.length;
 document.getElementById("prog").style.width=(100*ruledCount()/DATA.length)+'%';
 const vbtns=VERDS.map((v,i)=>{let c="vbtn";if(v===d.gold)c+=" gold";if(v===d.proposed)c+=" prop";if(r.ruling===v)c+=" chosen";
  let tag=[];if(v===d.gold)tag.push("current gold");if(v===d.proposed)tag.push("proposed");
  return '<div class="'+c+'" onclick="pick(\''+v+'\')"><span class="num">'+(i+1)+'</span>'+esc(v)+(tag.length?' <span class="tags">('+tag.join(", ")+')</span>':'')+'</div>';}).join("");
 const chosen=r.ruling?('<span class="done">RULED: '+esc(r.ruling)+(r.ruling===d.proposed?' (accepted proposal)':r.ruling===d.gold?' (kept gold)':' (override)')+'</span>'):'<span class="kv">not yet ruled</span>';
 document.getElementById("main").innerHTML='<div class="card"><div class="meta">'
  +'<span class="chip tier">'+esc(d.tier)+' &middot; '+esc(d.confidence)+'</span><span>'+esc(d.id)+'</span></div>'
  +'<h2 class="prob">'+esc(d.problem)+'</h2>'
  +'<details><summary>correct solution</summary><div class="sol">'+esc(d.correct_solution)+'</div></details>'
  +(d.final_answer?'<div class="kv">final answer: '+esc(d.final_answer)+(d.key_step?' &middot; key step: '+esc(d.key_step):'')+'</div>':'')
  +bubbles(d.conversation_history)
  +'<div class="cand"><div class="lbl">CANDIDATE MESSAGE — the one being judged</div>'+esc(d.candidate_message)+'</div>'
  +'<div class="decision"><div class="box"><div class="lab">Current gold</div><div class="v gold">'+esc(d.gold)+'</div></div>'
  +'<div class="box"><div class="lab">Proposed (your strict std)</div><div class="v prop">'+esc(d.proposed)+'</div></div>'
  +'<div class="box"><div class="lab">Neutral strict read</div><div class="v neu">'+esc(d.strict||"—")+'</div></div></div>'
  +'<div class="why"><b>why proposed:</b> '+esc(d.why)+'</div>'
  +'<div class="verdicts">'+vbtns+'</div>'
  +'<div class="quick"><button class="btn" onclick="pick(\''+d.proposed+'\')">p · accept proposed</button>'
  +'<button class="btn" onclick="pick(\''+d.gold+'\')">g · keep gold</button><span class="status" style="align-self:center">'+chosen+'</span></div>'
  +'<textarea id="notes" placeholder="notes (optional)" oninput="onNotes(this.value)">'+esc(r.notes)+'</textarea></div>';
}
function pick(v){ rec(DATA[cur].id).ruling=v; save(); setTimeout(()=>go(1),140); }
function onNotes(v){ rec(DATA[cur].id).notes=v; localStorage.setItem(KEY,JSON.stringify(store)); }
function go(d){ cur=Math.max(0,Math.min(DATA.length-1,cur+d)); render(); window.scrollTo(0,0); }
document.addEventListener("keydown",e=>{ if(e.target.tagName==="TEXTAREA"){if(e.key==="Escape")e.target.blur();return;}
 const d=DATA[cur];
 if(e.key>="1"&&e.key<="5"){pick(VERDS[+e.key-1]);}else if(e.key==="p"){pick(d.proposed);}else if(e.key==="g"){pick(d.gold);}
 else if(e.key==="n"){e.preventDefault();document.getElementById("notes").focus();}
 else if(e.key==="ArrowRight"||e.key==="j"){go(1);}else if(e.key==="ArrowLeft"||e.key==="k"){go(-1);}else if(e.key==="e"){exportJSON();}});
function importJSON(f){ if(!f)return; const fr=new FileReader(); fr.onload=()=>{let o;try{o=JSON.parse(fr.result);}catch(e){alert("bad JSON");return;}
 const items=o.items||o; let n=0; for(const x of items){if(x&&x.id&&(x.ruling||x.notes)){store[x.id]={ruling:x.ruling||null,notes:x.notes||""};n++;}} save(); alert("imported "+n);}; fr.readAsText(f); }
function exportJSON(){ const out={reviewed_at_local:new Date().toString(), ruled:ruledCount(), total:DATA.length,
 items:DATA.map(d=>{const r=store[d.id]||{}; return {id:d.id,tier:d.tier,gold:d.gold,proposed:d.proposed,strict:d.strict,ruling:r.ruling||null,
  accepted_proposal:r.ruling?(r.ruling===d.proposed):null, notes:r.notes||""};})};
 const b=new Blob([JSON.stringify(out,null,2)],{type:"application/json"});const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="ruling_results.json";a.click(); }
render();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--edits", default=EDITS)
    ap.add_argument("--frozen", default=FROZEN)
    ap.add_argument("--tiers", default="SUPPORTED,TENTATIVE")
    ap.add_argument("--out", default="eval/gold/review/ruling.html")
    a = ap.parse_args()
    tiers = set(t.strip() for t in a.tiers.split(","))

    edits = json.load(open(a.edits))["edits"]
    frozen = {r["id"]: r for r in read_jsonl(a.frozen)}
    items = []
    for e in edits:
        if e["tier"] not in tiers:
            continue
        row = frozen.get(e["id"], {})
        items.append({
            "id": e["id"], "tier": e["tier"], "confidence": e.get("confidence", ""),
            "gold": e["old"], "proposed": e["new"], "strict": e.get("strict"), "why": e.get("why", ""),
            "problem": row.get("problem", ""), "correct_solution": row.get("correct_solution", ""),
            "final_answer": row.get("final_answer", ""), "key_step": row.get("key_step", ""),
            "conversation_history": row.get("conversation_history") or [],
            "candidate_message": row.get("candidate_message", ""),
        })
    # tentative (leak judgment calls) first, then supported
    items.sort(key=lambda x: (0 if x["tier"] == "TENTATIVE" else 1, x["id"]))
    html = HTML.replace("__DATA__", json.dumps(items)).replace("__VERDS__", json.dumps(list(VERDICTS)))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        f.write(html)
    print(f"[ruling] {len(items)} items ({a.tiers}) -> {a.out}", file=sys.stderr)
    print(f"\nOpen it:  open '{a.out}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
