# Submission — Socratic Tutor Adequacy Judge & Rewriter (Qwen3-1.7B)

A local, fine-tuned **safety guardrail for AI math tutors**: it judges whether a tutor message leaks
the answer or the pivotal key step, and — if flagged — rewrites it into a safe Socratic hint.

**Behavior spec (the gate, falsifiable):** *A tutor message is adequate iff it neither states the
final answer nor hands over the single key step/insight that trivializes the problem; it scaffolds
with a question or calibrated hint instead. The rewriter turns any flagged message into such a hint.*

**Ship pipeline:** `v9` (verdict-only recall-first **detector**) → if flagged → `rewrite_v4`
(**rewriter**). Both 1.7B QLoRA adapters, run locally.

---

## The 5 deliverables (spec: *Final Submission Package*)

| # | Deliverable | Where | Status |
|---|---|---|---|
| 1 | **Dataset published** (the real artifact) | `data/raw/` (v9 judge data, `rewrite_train_v4`, `boundary_pairs`, human curations) → HF dataset | ⏳ **publish pending** (T80) |
| 2 | **Model on HF + running demo** | HF `atakle/socratic-judge-4b` (scale probe); **ship 1.7B publish pending** (T81). Demo: `webui/` on :8010, **Ship pipeline** judge | 🟡 demo ✅, ship-model publish pending |
| 3 | **Eval harness + results table** (base vs tuned vs frontier) | `scripts/overnight/{eval_verdict,eval_rewrite,eval_sharp,stress_ship,bench_run}.py`; results in `docs/eval_review.md` + `eval/results/overnight/` | ✅ **done** |
| 4 | **Brainlift** (thesis + evidence) | `docs/` brainlift | 🟡 **revamp pending** (T82) |
| 5 | **3–5 min demo video** | shotlist `docs/demo_shotlist.md` → record | ⏳ **record pending** (T83) |
| + | **Stretch ladder** (bonus) | DPO (regressed, `dpo_v1`), adversarial stress (`stress_ship`), composed behavior (judge+rewriter) | ✅ attempted/done |

---

## Headline results (all measured base vs tuned vs frontier)

- **Judge safety:** `v6` **82.2% safety-binary — beats GPT-4o (77.5%) & Claude (78.5%)**; `v9` **90.4%
  leak-recall** (= Opus). Base→tuned leak-recall **2% → 90%**, all from data.
- **Rewriter safety (sharpened detector):** `rewrite_v4` **6.7% key-step leak — safest tier of every
  model tested** (ties sonnet-5, beats gpt-5.6/4o/4.1).
- **Scale isn't the lever:** a 4B judge (identical recipe) ties the 1.7B on safety (recall 93.3 ≈ 90.4)
  and *loses* on 5-way. Clean benchmarks: scale **helps general** ability (4B > 1.7B on GSM8K/MMLU) but
  **not the constrained safety behavior** → **safety is a data property, not a scale property**.
- **Honest metric design was the biggest lever:** the safety-axis reframe (no retrain) and the
  sharpened leak detector each changed the story more than any model change.

---

## Run the demo

```bash
.venv/bin/python webui/run.py --port 8010        # then open http://127.0.0.1:8010
```
Compare tab → pick **"Ship pipeline (v9 → rewrite_v4)"** → paste a leaky tutor message → watch v9 flag
it and rewrite_v4 fix it. (Base/v6/frontier judges available for side-by-side.)

## Repo map

- **`docs/eval_review.md`** — eval suite + results + retrospective + anticipated Q&A (start here).
- **`docs/model_devlog.md`** — per-version dev-log (v1 → ship), goal/change/metrics/learned/decision.
- `docs/honest_eval.md` — detector sharpening + dataset-scaling study.
- `docs/project_report.md` — full experiment log (the climb, the plateau, the reframe).
- `docs/demo_shotlist.md` — the 3–5 min video plan.
- `docs/figures/` — loss curves, dataset composition, detector broad-vs-sharp, scaling curves.
- `scripts/overnight/` — eval + data-gen + scaling pipeline. `webui/` — the inference demo.
- `adapters/` — trained adapters (gitignored; regenerable). Ship: `v9`, `rewrite_v4`.

## Remaining to ship (tasksheet T80–T84)

1. **T81 / T80** — publish ship 1.7B (fuse v9 + rewrite_v4) + the dataset to HF Hub *(needs HF token)*.
2. **T82** — brainlift Part 2 revamp (draft w/ this week's findings → finalize voice).
3. **T83** — record the demo video (shotlist ready).
4. **T84** — consolidate branches (`feat/final-day` + stacked) → clean final state.
