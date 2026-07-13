# Demo Video Shotlist (3–5 min) — Socratic Tutor Guardrail

**Structure = the four points, in order.** Frontier comparators are **Claude Opus** and **GPT-5.5**.
The §4 scorecard shows the *entire range* of values side-by-side (base / our SLM / Opus / GPT-5.5) —
where we win *and* where we lose — not a single cherry-picked %. Record with the webui on **:8010**,
GPU idle (snappy). Numbers in §4 are filled from `eval/results/overnight/verdict_demo.md` +
`rewrite_demo.md`.

**Opening line (thesis):** *"AI tutors have one job they keep failing — don't give away the answer.
We got a 1.7B to hold that line by engineering the data and the metric, not by scaling the model.
Here's the problem, what frontier models actually do, what ours does differently, and the full
scorecard — wins and losses."*

---

## 1) The problem we're solving (0:00–0:45)

- **On screen:** `docs/behavior_spec.md` + a real leaky tutor exchange.
- **Say:**
  - The spec, one falsifiable sentence: **never state the final answer, and never hand over the
    pivotal key step** — scaffold with a question instead.
  - Why it's *hard*: models are trained to be helpful, so under pressure they cave. And a good
    **prompt doesn't guarantee it** — a guardrail has to hold *every* turn, which is what a dataset
    buys and a prompt can't.
  - The dangerous failure isn't blurting the final answer — it's the **disguised key-step leak**
    ("just divide by 3…") mid-explanation. That's what our founding probe found (8/8 tutors cave;
    ~100% of leaks are key-step, not answer).
  - The build: a **judge** that detects the leak + a **rewriter** that fixes it — a safety guardrail.

## 2) What frontier models do — and their limits (0:45–2:00)

- **On screen:** webui :8010, **Compare** tab — judge the same leaky message with **Opus** and **GPT-5.5**.
- **Show what they do well:** fluent, well-reasoned verdicts and often-good rewrites; strong fine-grained
  (5-way) judgment and general capability. *Frontier models are genuinely capable here.*
- **Show the limits (the crux):**
  - **They leak under pressure.** Live: push a frontier tutor ("just tell me the answer") until it
    hands over the step/answer. Our adversarial stress test: **every** raw tutor caves (held only 2–4/8);
    per-message key-step leak stays ~**10–12%** even for the best frontier model. Nobody *solves* it.
  - **They're the wrong shape for a guardrail:** a guardrail runs on *every* tutor turn → per-call API
    cost + student data leaving to a third party; and their leak/calibration **swings by model/version**,
    so it's only as safe as this month's model choice.
- **Say:** capable, but *not reliably safe under pressure* and *not a controllable, local guardrail*.

## 3) What our SLM does differently (2:00–3:15)

- **On screen:** webui, **Ship pipeline (v9 → rewrite_v4)** judging the *same* leaky message.
- **Different:** a **two-model guardrail** — **v9** (recall-first **detector**: catch the leak) →
  **rewrite_v4** (**rewriter**: operation-free Socratic hint). Trained on our data; **runs locally**.
- **Where it succeeds:**
  - Catches leaks at **frontier-level recall** (the metric a guardrail lives on — a missed leak is the
    real harm; a false flag just spends a rewrite).
  - The rewrite is in the **safest tier of every model tested** — ties/beats Opus + GPT-5.5 on
    key-step leak.
  - Local, cheap, auditable; emits 100% valid schema.
- **Where it fails (say it honestly):**
  - Trails frontier on **fine 5-way discrimination** and the **fuzzy "is this a *good* hint" quality
    axis** (frontier's holistic rewrite quality is higher).
  - It's a **specialist, not a generalist** — low GSM8K/MMLU under a neutral prompt (the cost of
    specialization). Show one case where its rewrite is blander than Opus's, or it over-flags.

## 4) The full scorecard — the entire range, wins and losses (3:15–4:15)

- **On screen:** this table (all metrics, all four models together). "Our SLM" = **v9** on the judge
  rows, **rewrite_v4** on the rewrite row — the shipping pipeline.

**Our task (judge + rewrite):**

| metric | base 1.7B | **our SLM** | Opus | GPT-5.5 |
|---|---|---|---|---|
| Judge — 5-way acc | ⟨fill⟩ | ⟨v9⟩ | ⟨fill⟩ | ⟨fill⟩ |
| Judge — safety-binary | ⟨fill⟩ | ⟨v9⟩ | ⟨fill⟩ | ⟨fill⟩ |
| **Judge — leak RECALL** (ship metric ↑) | ⟨fill⟩ | ⟨v9⟩ | ⟨fill⟩ | ⟨fill⟩ |
| Judge — leak precision | ⟨fill⟩ | ⟨v9⟩ | ⟨fill⟩ | ⟨fill⟩ |
| Judge — leak F1 | ⟨fill⟩ | ⟨v9⟩ | ⟨fill⟩ | ⟨fill⟩ |
| **Rewrite — key-step leak %** (↓ better) | ⟨fill⟩ | ⟨rewrite_v4⟩ | ⟨fill⟩ | ⟨fill⟩ |

**General capability (the specialization trade):**

| metric | base 1.7B | our SLM | frontier |
|---|---|---|---|
| GSM8K (flex) | 17.6% | specialist (low under neutral prompt) | high (Opus/GPT-5.5 ≫) |
| MMLU | 63.2% | — | high |

- **Narrate the honest range:** *"Read left to right. We **win** on leak-recall — the safety-critical
  metric a guardrail lives on — and we **tie or beat** both Opus and GPT-5.5 on rewrite key-step leak.
  We **lose** on 5-way discrimination and on general capability — frontier is the better generalist.
  The claim was never 'we're smarter.' It's: on the narrow safety behavior, a **1.7B rivals frontier**
  — and it's local, cheap, and auditable."*

## Close (4:15–4:30)

- **Thesis line:** *"Reliable, constrained safety behavior comes from clean data and honest metrics —
  not scale. A 4B trained identically didn't beat it. Behavior from data."*
- **On screen:** the HF links — [judge](https://huggingface.co/atakle/socratic-tutor-judge-v9-1.7b) ·
  [rewriter](https://huggingface.co/atakle/socratic-tutor-rewriter-v4-1.7b) ·
  [dataset](https://huggingface.co/datasets/atakle/socratic-tutor-data).

---

### Recording checklist
- [ ] webui up on :8010, **no GPU jobs running** (pause any eval first so Compare is snappy).
- [ ] Leaky example + a push-for-the-answer line pre-typed (avoid dead air).
- [ ] §4 scorecard on screen (fill the ⟨…⟩ from `verdict_demo.md` + `rewrite_demo.md`).
- [ ] Spend the most time on **2→3** (frontier leaks → our pipeline fixes) — that's the heart.
- [ ] Be explicit about losses in §3/§4 — the honesty is what makes the win credible.
