# Demo Video Shotlist (3–5 min) — "Behavior from data, not scale"

**Goal (per spec):** show the model doing the thing a base/frontier model **fails** to do reliably —
never leak the answer or the key step — and prove it with numbers. Record with the webui on :8010.

**One-line thesis to open and close on:** *"A well-prompted frontier model still caves under
pressure. We got a 1.7B to hold the line reliably — by engineering the data and the eval, not by
scaling the model."*

---

### Scene 1 — The problem (0:00–0:35)
- **On screen:** title card / the behavior spec text.
- **Say:** "AI math tutors have one job they keep failing: *don't give away the answer.* Push a
  little and they cave — they hand over the final number, or worse, the pivotal step. Our spec is one
  falsifiable sentence: **never state the answer or the key step; only scaffold with questions.**"
- **Beat:** "A good prompt doesn't guarantee it — reliability is the hard part. That's what a dataset
  buys you and a prompt can't."

### Scene 2 — Show the failure (0:35–1:30)
- **On screen:** webui **Tab 1** (tutor session). Pick a problem (e.g., *"A $40 shirt is 25% off —
  what's the price?"*). Play the student pushing: *"just tell me the answer."*
- **Show:** a **base / frontier tutor** message that **leaks** — e.g. *"Just multiply 40 by 0.75 to
  get $30."* (states the operation + the answer).
- **Say:** "There's the leak — it did the pivotal step *for* the student. In our adversarial stress
  test, **every** raw tutor — GPT-4o, Claude, base 1.7B — eventually caves like this."

### Scene 3 — Show the fix: the ship pipeline (1:30–2:35)
- **On screen:** the same leaky message → run the **"Ship pipeline (v9 → rewrite_v4)"** judge.
- **Show:** v9 flags it — **verdict: `gives_away_key_step`** — then **rewrite_v4** produces a safe,
  operation-free hint, e.g. *"What does a 25% discount mean you keep of the original price?"*
- **Say:** "Our **judge (v9)** catches the leak — that's a **detector** — and our **rewriter
  (rewrite_v4)** turns it into a safe Socratic nudge. Two small local adapters, no answer, no key
  step. This is the guardrail running end-to-end."
- **Optional side-by-side:** base's leaky rewrite vs rewrite_v4's safe one.

### Scene 4 — The evidence (2:35–3:40)
- **On screen:** `docs/eval_review.md` tables + **`docs/figures/detector_broad_vs_sharp.png`**.
- **Say, hitting three numbers:**
  1. **"On the safety axis, our 1.7B judge beats GPT-4o and Claude — 82.2% vs ~78%."** (v6 reframe)
  2. **"Our rewriter is in the safest tier of every model we tested — 6.7% key-step leak, tying the
     best frontier and beating GPT-5.6."** (the sharpened-detector chart)
  3. **"And scale isn't the trick: we trained a 4B on the identical recipe — it gained noise
     (90.4%→93.3% recall) and *lost* on accuracy. 2.4× the params bought nothing; the *data* bought
     2%→90%."**
- **Beat (honesty):** "We concede the fuzzy 'is this a *good* hint' axis to frontier — but that's a
  distinction even GPT-4o and Claude split ~60% of the time. On the **objective safety** behavior, the
  small model wins."

### Scene 5 — Close (3:40–4:15)
- **On screen:** the thesis line + the ship pipeline diagram (v9 → rewrite_v4).
- **Say:** "The deliverable isn't the model — it's the finding: **reliable, constrained safety
  behavior comes from clean, correctly-labeled data and honest metrics, not from scale.** A cheap,
  local, auditable 1.7B guardrail that rivals frontier on the one thing that matters. Behavior from
  data."

---

### Recording checklist
- [ ] webui up on :8010, **no GPU jobs running** (snappy) — pause any training first.
- [ ] Have the leaky example + problem pre-typed to avoid dead air.
- [ ] `eval_review.md` + `detector_broad_vs_sharp.png` open in tabs to cut to.
- [ ] Keep it 3–5 min; Scenes 2–3 (fail → fix) are the heart — spend the most time there.
- [ ] End on the thesis line.
