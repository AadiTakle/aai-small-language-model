// Socratic Tutor Explorer — frontend logic (vanilla, no build step).
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => (s ?? "").toString().replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const VERDICTS = ["adequate", "gives_final_answer", "gives_away_key_step", "mismatched_calibration", "vague_unhelpful"];
const LEAK = new Set(["gives_final_answer", "gives_away_key_step"]);

async function api(path, body) {
  const opt = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
  const r = await fetch(path, opt);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}
const badge = (v) => `<span class="badge v-${v || "unknown"}">${esc(v || "unknown")}</span>`;

let MODELS = { judges: [], tutors: [] };

// ── tabs ──
$$(".tab").forEach((t) => t.addEventListener("click", () => {
  $$(".tab").forEach((x) => x.classList.toggle("is-active", x === t));
  $$(".panel").forEach((p) => p.classList.toggle("is-active", p.id === t.dataset.tab));
}));

// ── init: load registry, populate dropdowns ──
(async function init() {
  MODELS = await api("/api/models");
  const opt = (m) => `<option value="${m.id}">${esc(m.label || m.id)}</option>`;
  $("#s-tutor").innerHTML = MODELS.tutors.map(opt).join("");
  $("#s-judge").innerHTML = MODELS.judges.map(opt).join("");
  if ([...$("#s-judge").options].some((o) => o.value === "v6")) $("#s-judge").value = "v6";
  $("#c-edit-verdict").innerHTML = VERDICTS.map((v) => `<option value="${v}">${v}</option>`).join("");
  addTurn(); // seed one conversation row in Compare
})();

// ═══════════════ Tab 1: Tutor Session ═══════════════
let convo = [];
const setup = () => ({ problem: $("#s-problem").value, solution: $("#s-solution").value });

function renderChat() {
  const log = $("#chat-log");
  if (!convo.length) { log.innerHTML = `<div class="chat-empty">Send the student's first message to begin.</div>`; return; }
  log.innerHTML = convo.map((t, i) => {
    if (t.role === "student")
      return `<div class="turn student"><div class="who">Student</div><div class="bubble">${esc(t.text)}</div></div>`;
    if (t.error)
      return `<div class="turn"><div class="who">Tutor · ${esc(t.tutor || "")}</div>
        <div class="tutor-card"><div class="meta"><div class="row2">${badge("error")}
        <span class="candidate">tutor call failed: ${esc(t.error)}</span></div></div></div></div>`;
    const flagged = t.verdict && t.verdict !== "adequate";
    const rawLine = flagged
      ? `<div class="candidate">tutor's raw message (flagged): <s>${esc(t.candidate)}</s></div>`
      : "";
    const dflt = VERDICTS.includes(t.verdict) ? t.verdict : "adequate";
    const rwPrefill = t.shown && t.shown !== t.candidate ? t.shown : "";  // the judge's rewrite, to accept or edit
    const label = t.contributed
      ? `<div class="label-row"><span class="tl-status ok">✓ added to dataset as <b>${esc(t.contributed)}</b></span></div>`
      : `<div class="label-row"><span class="k">your label:</span>
          <select class="tl-verdict">${VERDICTS.map((v) => `<option${v === dflt ? " selected" : ""}>${v}</option>`).join("")}</select>
          <button class="tl-add ghost">Add to dataset</button><span class="tl-status"></span>
          <label class="tl-rw-wrap${dflt === "adequate" ? " hidden" : ""}"><span class="k">rewrite for the student — edit the model's or write your own:</span>
            <textarea class="tl-rewrite" rows="2" placeholder="A calibrated Socratic hint: no final answer, no key step, grounded in the student's last message.">${esc(rwPrefill)}</textarea></label>
        </div>`;
    return `<div class="turn" data-i="${i}"><div class="who">Tutor · ${esc(t.tutor)} → judged by ${esc(t.judge)}</div>
      <div class="tutor-card">
        <div class="shown"><b>shown to student:</b> ${esc(t.shown)}</div>
        <div class="meta">
          <div class="row2">${badge(t.verdict)}<span class="candidate">${esc(t.reasoning || "")}</span></div>
          ${rawLine}
        </div>
        ${label}
      </div></div>`;
  }).join("");
  $$("#chat-log .tl-add").forEach((b) => b.addEventListener("click", () => labelAndAdd(+b.closest(".turn").dataset.i, b)));
  $$("#chat-log .tl-verdict").forEach((sel) => sel.addEventListener("change", () => {  // adequate ⇒ no rewrite
    const wrap = sel.closest(".label-row").querySelector(".tl-rw-wrap");
    if (wrap) wrap.classList.toggle("hidden", sel.value === "adequate");
  }));
  log.scrollTop = log.scrollHeight;
}

async function labelAndAdd(i, btn) {
  const turn = convo[i];
  const row = btn.parentElement;                          // .label-row
  const verdict = row.querySelector(".tl-verdict").value;
  const st = row.querySelector(".tl-status");
  const rwEl = row.querySelector(".tl-rewrite");
  const rewrite = verdict === "adequate" ? null : (rwEl ? rwEl.value.trim() : "");
  if (verdict !== "adequate" && !rewrite) {               // never save the invalid flagged+empty combo
    st.textContent = "write a rewrite first (a flagged message needs one)"; st.className = "tl-status";
    if (rwEl) rwEl.focus();
    return;
  }
  const conversation = convo.slice(0, i).map((t) => (t.role === "student" ? `Student: ${t.text}` : `Tutor: ${t.shown}`));
  const slmRewrite = turn.shown && turn.shown !== turn.candidate ? turn.shown : null;  // provenance: what the judge proposed
  btn.disabled = true; st.textContent = "saving…"; st.className = "tl-status";
  try {
    await api("/api/contribute", {
      problem: $("#s-problem").value, solution: $("#s-solution").value,
      final_answer: $("#s-answer").value, key_step: $("#s-keystep").value,
      conversation, candidate_message: turn.candidate, verdict,
      reasoning: turn.reasoning || "", rewritten_message: rewrite,
      source_model: turn.tutor, slm_verdict: turn.verdict || "", slm_rewrite: slmRewrite,
      mode: "tutor_session",
    });
    turn.contributed = verdict; renderChat();            // persist across re-renders
  } catch (e) { st.textContent = "error: " + e.message; btn.disabled = false; }
}

$("#s-reset").addEventListener("click", () => { convo = []; renderChat(); });

$("#s-send").addEventListener("click", async () => {
  const text = $("#s-student").value.trim();
  if (!text) return;
  const btn = $("#s-send"); btn.disabled = true; btn.textContent = "…";
  convo.push({ role: "student", text }); $("#s-student").value = ""; renderChat();
  const conversation = convo.map((t) => (t.role === "student" ? `Student: ${t.text}` : `Tutor: ${t.shown}`));
  try {
    const tutorId = $("#s-tutor").value, judgeId = $("#s-judge").value;
    const { problem, solution } = setup();
    const t = await api("/api/tutor", { tutor: tutorId, problem, solution, conversation });
    if (!t.candidate_message) {  // tutor failed — surface it, don't judge a placeholder
      convo.push({ role: "tutor", tutor: tutorId, error: t.error || "tutor returned no message" });
      renderChat(); return;
    }
    const candidate = t.candidate_message;
    const suite = await api("/api/judge_suite", { problem, solution, conversation, candidate, models: [judgeId] });
    const j = (suite.results || [{}])[0] || {};
    const flagged = j.verdict && j.verdict !== "adequate";
    const shown = flagged && j.rewritten_message ? j.rewritten_message : candidate;
    convo.push({ role: "tutor", tutor: tutorId, judge: judgeId, candidate, shown,
                 verdict: j.verdict, reasoning: j.reasoning || j.error || "" });
    renderChat();
  } catch (e) {
    convo.push({ role: "tutor", tutor: tutorId, error: e.message });
    renderChat();
  } finally { btn.disabled = false; btn.textContent = "Send"; }
});

// ═══════════════ Tab 2: Compare & Label ═══════════════
function addTurn(val = "") {
  const row = document.createElement("div");
  row.className = "convo-row";
  row.innerHTML = `<input placeholder="e.g. Student: I think it's 26?" value="${esc(val)}" /><button title="remove">×</button>`;
  row.querySelector("button").addEventListener("click", () => row.remove());
  $("#c-convo").appendChild(row);
}
$("#c-addturn").addEventListener("click", () => addTurn());

const gatherCompare = () => ({
  problem: $("#c-problem").value, solution: $("#c-solution").value,
  final_answer: $("#c-answer").value, key_step: $("#c-keystep").value,
  conversation: $$("#c-convo .convo-row input").map((i) => i.value).filter(Boolean),
  candidate: $("#c-candidate").value,
});

let lastResults = [], favorite = null;

$("#c-run").addEventListener("click", async () => {
  const c = gatherCompare();
  if (!c.candidate.trim()) { $("#c-results").innerHTML = `<div class="spinner">Enter a candidate message first.</div>`; return; }
  $("#c-results").innerHTML = `<div class="spinner">Running ${MODELS.judges.length} models…</div>`;
  $("#c-submit").classList.add("hidden"); favorite = null;
  try {
    const { results } = await api("/api/judge_suite", { problem: c.problem, solution: c.solution, conversation: c.conversation, candidate: c.candidate });
    lastResults = results;
    renderResults();
  } catch (e) { $("#c-results").innerHTML = `<div class="spinner">Error: ${esc(e.message)}</div>`; }
});

function renderResults() {
  $("#c-results").innerHTML = lastResults.map((r, i) => {
    const body = r.error
      ? `<div class="err">${esc(r.error)}</div>`
      : `<div class="field"><span class="k">reasoning</span><br>${esc(r.reasoning) || "—"}</div>
         <div class="field"><span class="k">rewrite</span><br>${r.rewritten_message ? esc(r.rewritten_message) : '<span class="none">— (none / adequate)</span>'}</div>`;
    const head = r.error ? `<span class="name">${esc(r.label)}</span>` :
      `<span class="name">${esc(r.label)}</span>${badge(r.verdict)}`;
    return `<div class="model-card" data-i="${i}">
      <div class="head">${head}</div>
      ${body}
      ${r.error ? "" : `<div class="card-actions">
        <button class="star" title="favorite">★</button>
        <label style="margin:0;font-size:12px;color:var(--ink-soft)">rank<input class="rank" type="number" min="1" style="margin-top:2px" /></label>
      </div>`}
    </div>`;
  }).join("");
  $$("#c-results .star").forEach((s) => s.addEventListener("click", () => {
    const i = +s.closest(".model-card").dataset.i;
    setFavorite(i);
  }));
}

function setFavorite(i) {
  favorite = i;
  $$("#c-results .model-card").forEach((c) => c.classList.toggle("fav", +c.dataset.i === i));
  $$("#c-results .star").forEach((s) => s.classList.toggle("on", +s.closest(".model-card").dataset.i === i));
  const r = lastResults[i];
  $("#c-fav").textContent = r.label;
  $("#c-edit-verdict").value = VERDICTS.includes(r.verdict) ? r.verdict : "adequate";
  $("#c-edit-reasoning").value = r.reasoning || "";
  $("#c-edit-rewrite").value = r.rewritten_message || "";
  $("#c-submit").classList.remove("hidden");
  $("#c-status").textContent = "";
  $("#c-submit").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

$("#c-contribute").addEventListener("click", async () => {
  if (favorite === null) return;
  const c = gatherCompare();
  const ranked = $$("#c-results .model-card").map((card) => ({
    id: lastResults[+card.dataset.i].model, rank: +(card.querySelector(".rank")?.value || 0),
  })).filter((x) => x.rank > 0).sort((a, b) => a.rank - b.rank).map((x) => x.id);
  const fav = lastResults[favorite];
  const rec = {
    problem: c.problem, solution: c.solution, final_answer: c.final_answer, key_step: c.key_step,
    conversation: c.conversation, candidate_message: c.candidate,
    verdict: $("#c-edit-verdict").value, reasoning: $("#c-edit-reasoning").value,
    rewritten_message: $("#c-edit-rewrite").value || null,
    source_model: fav.model, ranked_over: ranked,
    slm_verdict: fav.verdict || "", slm_rewrite: fav.rewritten_message || null, mode: "compare",
  };
  const st = $("#c-status"); st.textContent = "saving…"; st.className = "status";
  try {
    const res = await api("/api/contribute", rec);
    st.textContent = `✓ added to ${res.path}`; st.className = "status ok";
  } catch (e) { st.textContent = `error: ${e.message}`; st.className = "status"; }
});

// ═══════════════ Tab 3: Curate (rewrite feed) ═══════════════
let CU = { queue: [], pos: 0, stats: {}, loading: false, loaded: false };

async function cuEnsureLoaded() { if (!CU.loaded && !CU.loading) cuLoad(); }

async function cuLoad() {
  CU.loading = true;
  try {
    const r = await api("/api/curate/next?count=25");
    CU.stats = r; CU.queue = r.items || []; CU.pos = 0; CU.loaded = true;
    if (!r.ready) { $("#cu-card").innerHTML = `<div class="spinner">Feed not built yet — the side-by-side data is still generating.</div>`; return; }
    cuRender();
  } catch (e) { $("#cu-card").innerHTML = `<div class="spinner">Error: ${esc(e.message)}</div>`; }
  finally { CU.loading = false; }
}

const cuCurrent = () => CU.queue[CU.pos];

function cuProgress() {
  const s = CU.stats;
  $("#cu-progress").innerHTML = s.total
    ? `reviewed <b>${s.reviewed || 0}</b> / ${s.total} · <b>${s.remaining || 0}</b> left`
    : "no items";
}

async function cuRefillIfLow() {
  if (CU.pos < CU.queue.length - 3) return;
  try {
    const r = await api("/api/curate/next?count=25");
    CU.stats = r;
    const seen = new Set(CU.queue.map((x) => x.id));
    (r.items || []).forEach((it) => { if (!seen.has(it.id)) CU.queue.push(it); });
  } catch { /* keep going on the buffered items */ }
}

function cuRender() {
  cuProgress();
  const it = cuCurrent();
  if (!it) { $("#cu-card").innerHTML = `<div class="spinner">🎉 All caught up — nothing left to review.</div>`; return; }
  const convo = (it.conversation_history || []).map((h) => `<div class="cu-turn">${esc(h)}</div>`).join("")
    || `<div class="cu-turn none">(no conversation yet)</div>`;
  const wc = (t) => (t || "").trim().split(/\s+/).filter(Boolean).length;
  const pane = (name, label, text) => text ? `
    <div class="rw-pane">
      <div class="rw-head"><span class="rw-label">${label}</span></div>
      <div class="rw-text">${esc(text)}</div>
      <button class="rw-approve primary" data-choice="${name}">✓ Approve <span class="rw-len">(${wc(text)}w)</span></button>
    </div>` : "";
  const panes = [pane("teacher", "gpt-5.6", it.teacher_rewrite), pane("slm", "rewrite_v1", it.slm_rewrite)].filter(Boolean).join("");
  $("#cu-card").innerHTML = `
    <div class="cu-context">
      <span class="cu-fuzzy">fuzzy ${it.fuzzy ?? "—"}</span>
      <div class="cu-problem"><b>Problem.</b> ${esc(it.problem)}</div>
      <div class="cu-convo">${convo}</div>
      <div class="cu-flagged">${badge(it.verdict)}<span class="cu-flagged-msg">flagged: “${esc(it.candidate_message)}”</span></div>
      ${it.reason ? `<div class="cu-reason">why flagged: ${esc(it.reason)}</div>` : ""}
    </div>
    <div class="rw-panes ${it.slm_rewrite ? "two" : "one"}">${panes}</div>
    <div class="cu-actions">
      <button id="cu-better-btn" class="ghost">✍ Neither — write a better one (e)</button>
      <button id="cu-skip" class="ghost">Skip (s)</button>
    </div>
    <div id="cu-better" class="cu-better hidden">
      <textarea id="cu-better-text" rows="2" placeholder="Write the ideal Socratic hint: one focused question, no answer, no key-step giveaway…"></textarea>
      <button id="cu-better-save" class="primary">Save better rewrite</button>
    </div>`;
  $$("#cu-card .rw-approve").forEach((b) => b.addEventListener("click", () => cuApprove(b.dataset.choice)));
  $("#cu-better-btn").addEventListener("click", cuWriteBetter);
  $("#cu-skip").addEventListener("click", cuSkip);
  $("#cu-better-save").addEventListener("click", cuSaveBetter);
}

async function cuSubmit(decision, rewrite) {
  const it = cuCurrent();
  if (!it || !rewrite) return;
  try {
    await api("/api/curate/submit", {
      id: it.id, decision, rewrite,
      problem: it.problem, correct_solution: it.correct_solution, final_answer: it.final_answer,
      key_step: it.key_step, conversation_history: it.conversation_history || [],
      candidate_message: it.candidate_message, verdict: it.verdict, reason: it.reason,
      teacher_rewrite: it.teacher_rewrite, slm_rewrite: it.slm_rewrite, source: it.source || "",
    });
    CU.stats.reviewed = (CU.stats.reviewed || 0) + 1;
    CU.stats.remaining = Math.max(0, (CU.stats.remaining || 1) - 1);
    CU.pos++; await cuRefillIfLow(); cuRender();
  } catch (e) { $("#cu-progress").innerHTML = `error: ${esc(e.message)}`; }
}

function cuApprove(choice) {
  const it = cuCurrent(); if (!it) return;
  if (choice === "slm" && !it.slm_rewrite) return;
  cuSubmit(choice === "slm" ? "approve_slm" : "approve_teacher",
           choice === "slm" ? it.slm_rewrite : it.teacher_rewrite);
}

function cuWriteBetter() {
  const box = $("#cu-better"); if (!box) return;
  box.classList.remove("hidden");
  const t = $("#cu-better-text"), it = cuCurrent();
  if (t && !t.value) t.value = it.teacher_rewrite || it.slm_rewrite || "";
  if (t) t.focus();
}

function cuSaveBetter() {
  const t = $("#cu-better-text"), v = (t?.value || "").trim();
  if (!v) { t?.focus(); return; }
  cuSubmit("rewrite", v);
}

function cuSkip() { CU.pos++; cuRefillIfLow().then(cuRender); }

const _cuTab = document.querySelector('.tab[data-tab="curate"]');
if (_cuTab) _cuTab.addEventListener("click", cuEnsureLoaded);
document.addEventListener("keydown", (e) => {
  const p = document.getElementById("curate");
  if (!p || !p.classList.contains("is-active")) return;
  if (e.target && (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT")) return;
  const k = (e.key || "").toLowerCase();
  if (k === "1") cuApprove("teacher");
  else if (k === "2") cuApprove("slm");
  else if (k === "e") { e.preventDefault(); cuWriteBetter(); }
  else if (k === "s") cuSkip();
});

// ═══════════════ Tab 4: Pairs (boundary curation) ═══════════════
// Show one leaky/safe minimal pair at a time, side by side, and let the human confirm the
// labels (approve), swap them (flip), or replace either side's text (edit_leaky / edit_safe).
let BP = { queue: [], pos: 0, stats: {}, loading: false, loaded: false, editing: null };

async function bpEnsureLoaded() { if (!BP.loaded && !BP.loading) bpLoad(); }

async function bpLoad() {
  BP.loading = true;
  try {
    const r = await api("/api/boundary/next?count=25");
    BP.stats = r; BP.queue = r.items || []; BP.pos = 0; BP.loaded = true;
    if (!r.ready) { $("#bp-card").innerHTML = `<div class="spinner">Pairs not built yet — data/raw/boundary_pairs.jsonl is missing.</div>`; return; }
    bpRender();
  } catch (e) { $("#bp-card").innerHTML = `<div class="spinner">Error: ${esc(e.message)}</div>`; }
  finally { BP.loading = false; }
}

const bpCurrent = () => BP.queue[BP.pos];

function bpProgress() {
  const s = BP.stats;
  $("#bp-progress").innerHTML = s.total
    ? `reviewed <b>${s.reviewed || 0}</b> / ${s.total} · <b>${s.remaining || 0}</b> left`
    : "no items";
}

async function bpRefillIfLow() {
  if (BP.pos < BP.queue.length - 3) return;
  try {
    const r = await api("/api/boundary/next?count=25");
    BP.stats = r;
    const seen = new Set(BP.queue.map((x) => x.id));
    (r.items || []).forEach((it) => { if (!seen.has(it.id)) BP.queue.push(it); });
  } catch { /* keep going on the buffered items */ }
}

// corrective-cue check (mirrors engine.CORRECTIVE_CUES) — only to badge the row in the UI
const BP_CUES = ["not quite", "you're close", "you are close", "actually", "remember", "should be",
  "the mistake", "you made", "incorrect", "wrong", "instead of", "you forgot"];
const bpHasCue = (t) => { const s = (t || "").toLowerCase(); return BP_CUES.some((c) => s.includes(c)); };

function bpRender() {
  bpProgress();
  const it = bpCurrent();
  if (!it) { $("#bp-card").innerHTML = `<div class="spinner">🎉 All caught up — no pairs left to review.</div>`; return; }
  const convo = (it.conversation_history || []).map((h) => `<div class="cu-turn">${esc(h)}</div>`).join("")
    || `<div class="cu-turn none">(no conversation yet)</div>`;
  const wc = (t) => (t || "").trim().split(/\s+/).filter(Boolean).length;
  const cue = bpHasCue(it.leaky_candidate);
  // one pane per side; when editing that side, swap the text for an editable textarea
  const pane = (side, cls, label, text) => {
    const body = BP.editing === side
      ? `<textarea class="bp-edit" rows="3" data-side="${side}">${esc(text)}</textarea>`
      : `<div class="rw-text">${esc(text)}</div>`;
    return `<div class="bp-pane ${cls}">
      <div class="rw-head"><span class="rw-label ${cls}">${label}</span><span class="rw-len">(${wc(text)}w)</span></div>
      <div class="bp-tag">${cls === "leaky" ? "should LEAK the key step" : "should stay SAFE (hint only)"}</div>
      ${body}
    </div>`;
  };
  const editing = BP.editing;  // "leaky" | "safe" | null
  const actions = editing
    ? `<button id="bp-save" class="primary">Save edited ${editing}</button>
       <button id="bp-cancel" class="ghost">Cancel</button>`
    : `<button id="bp-approve" class="primary">✓ Approve (1)</button>
       <button id="bp-flip" class="ghost">⇄ Flip labels (f)</button>
       <button id="bp-edit-leaky" class="ghost">✍ Edit leaky (l)</button>
       <button id="bp-edit-safe" class="ghost">✍ Edit safe (s)</button>
       <button id="bp-skip" class="ghost">Skip (k)</button>`;
  $("#bp-card").innerHTML = `
    <div class="cu-context">
      ${cue ? `<span class="bp-cue">corrective-framed</span>` : ""}
      <div class="cu-problem"><b>Problem.</b> ${esc(it.problem)}</div>
      <div class="cu-convo">${convo}</div>
      <div class="bp-keystep"><b>Key step to protect.</b> ${esc(it.key_step) || "—"}</div>
    </div>
    <div class="bp-panes">
      ${pane("leaky", "leaky", "Leaky candidate (left)", it.leaky_candidate)}
      ${pane("safe", "safe", "Safe rewrite (right)", it.safe_rewrite)}
    </div>
    <div class="bp-actions">${actions}</div>`;
  if (editing) {
    $("#bp-save").addEventListener("click", bpSaveEdit);
    $("#bp-cancel").addEventListener("click", () => { BP.editing = null; bpRender(); });
    const ta = $("#bp-card .bp-edit"); if (ta) ta.focus();
  } else {
    $("#bp-approve").addEventListener("click", () => bpSubmit("approve"));
    $("#bp-flip").addEventListener("click", bpFlip);
    $("#bp-edit-leaky").addEventListener("click", () => { BP.editing = "leaky"; bpRender(); });
    $("#bp-edit-safe").addEventListener("click", () => { BP.editing = "safe"; bpRender(); });
    $("#bp-skip").addEventListener("click", () => bpSubmit("skip"));
  }
}

async function bpSubmit(decision, over) {
  const it = bpCurrent();
  if (!it) return;
  // over: {leaky_candidate, safe_rewrite} to override the pair's text (edits/flips); else send as-is
  const leaky = over && "leaky_candidate" in over ? over.leaky_candidate : it.leaky_candidate;
  const safe = over && "safe_rewrite" in over ? over.safe_rewrite : it.safe_rewrite;
  try {
    await api("/api/boundary/submit", {
      id: it.id, decision, leaky_candidate: leaky, safe_rewrite: safe,
      problem: it.problem, correct_solution: it.correct_solution, final_answer: it.final_answer,
      key_step: it.key_step, conversation_history: it.conversation_history || [],
      source: it.source || "",
    });
    BP.stats.reviewed = (BP.stats.reviewed || 0) + 1;
    BP.stats.remaining = Math.max(0, (BP.stats.remaining || 1) - 1);
    BP.editing = null; BP.pos++; await bpRefillIfLow(); bpRender();
  } catch (e) { $("#bp-progress").innerHTML = `error: ${esc(e.message)}`; }
}

function bpFlip() {
  const it = bpCurrent(); if (!it) return;      // labels backwards: swap the two sides
  bpSubmit("flip", { leaky_candidate: it.safe_rewrite, safe_rewrite: it.leaky_candidate });
}

function bpSaveEdit() {
  const ta = $("#bp-card .bp-edit"); if (!ta) return;
  const v = ta.value.trim();
  if (!v) { ta.focus(); return; }
  const side = ta.dataset.side;                 // "leaky" | "safe"
  const over = side === "leaky" ? { leaky_candidate: v } : { safe_rewrite: v };
  bpSubmit(side === "leaky" ? "edit_leaky" : "edit_safe", over);
}

const _bpTab = document.querySelector('.tab[data-tab="pairs"]');
if (_bpTab) _bpTab.addEventListener("click", bpEnsureLoaded);
document.addEventListener("keydown", (e) => {
  const p = document.getElementById("pairs");
  if (!p || !p.classList.contains("is-active")) return;
  if (e.target && (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT")) return;
  if (BP.editing) return;  // while editing, keys type into the textarea
  const k = (e.key || "").toLowerCase();
  if (k === "1") bpSubmit("approve");
  else if (k === "f") bpFlip();
  else if (k === "l") { e.preventDefault(); BP.editing = "leaky"; bpRender(); }
  else if (k === "s") { e.preventDefault(); BP.editing = "safe"; bpRender(); }
  else if (k === "k") bpSubmit("skip");
});
