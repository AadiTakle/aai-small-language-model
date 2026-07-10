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
  log.innerHTML = convo.map((t) => {
    if (t.role === "student")
      return `<div class="turn student"><div class="who">Student</div><div class="bubble">${esc(t.text)}</div></div>`;
    const flagged = t.verdict && t.verdict !== "adequate";
    const rawLine = flagged
      ? `<div class="candidate">tutor's raw message (flagged): <s>${esc(t.candidate)}</s></div>`
      : "";
    return `<div class="turn"><div class="who">Tutor · ${esc(t.tutor)} → judged by ${esc(t.judge)}</div>
      <div class="tutor-card">
        <div class="shown"><b>shown to student:</b> ${esc(t.shown)}</div>
        <div class="meta">
          <div class="row2">${badge(t.verdict)}<span class="candidate">${esc(t.reasoning || "")}</span></div>
          ${rawLine}
        </div>
      </div></div>`;
  }).join("");
  log.scrollTop = log.scrollHeight;
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
    const candidate = t.candidate_message || "(tutor error)";
    const suite = await api("/api/judge_suite", { problem, solution, conversation, candidate, models: [judgeId] });
    const j = (suite.results || [{}])[0] || {};
    const flagged = j.verdict && j.verdict !== "adequate";
    const shown = flagged && j.rewritten_message ? j.rewritten_message : candidate;
    convo.push({ role: "tutor", tutor: tutorId, judge: judgeId, candidate, shown,
                 verdict: j.verdict, reasoning: j.reasoning || j.error || "" });
    renderChat();
  } catch (e) {
    convo.push({ role: "tutor", tutor: "", judge: "", candidate: "", shown: `error: ${e.message}`, verdict: "error", reasoning: "" });
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
  const rec = {
    problem: c.problem, solution: c.solution, final_answer: c.final_answer, key_step: c.key_step,
    conversation: c.conversation, candidate_message: c.candidate,
    verdict: $("#c-edit-verdict").value, reasoning: $("#c-edit-reasoning").value,
    rewritten_message: $("#c-edit-rewrite").value || null,
    source_model: lastResults[favorite].model, ranked_over: ranked,
  };
  const st = $("#c-status"); st.textContent = "saving…"; st.className = "status";
  try {
    const res = await api("/api/contribute", rec);
    st.textContent = `✓ added to ${res.path}`; st.className = "status ok";
  } catch (e) { st.textContent = `error: ${e.message}`; st.className = "status"; }
});
