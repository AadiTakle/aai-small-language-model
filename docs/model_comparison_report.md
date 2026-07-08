# Comprehensive Model Report — Socratic Tutor Judge/Rewriter vs. Frontier

**Task under test:** given a math problem, its solution (internal ground truth), the conversation so far, and a candidate tutor message, emit a single JSON object `{verdict, reasoning, rewritten_message}` classifying the message against the 5-verdict taxonomy and rewriting it safely if inadequate (see [`behavior_spec.md`](behavior_spec.md)).

**Contestants:** `base` (Qwen3-1.7B-4bit, untuned) · `v2`/`v3`/`v4` (our QLoRA fine-tunes) · `gpt4o` (GPT-4o) · `claude` (Claude, in-session). Frontier models run the **same** judge task with the **same** system prompt.

---

## TL;DR (honest)

- **Core judge task (verdict classification + strict format):** our **v4** (1.7B, local) is **statistically tied with Claude** and **significantly beats GPT-4o** — on bias-free, deterministic criteria, with paired 95% CIs on a leakage-verified frozen set.
- **Flagship failure category (catching `gives_away_key_step` leaks):** tuned models match/beat GPT-4o (v3 100%, v4 95% caught; GPT-4o 90%, and it wrongly cleared 2 leaks as "adequate").
- **Deployed as a guardrail:** a weak base tutor wrapped in the **v4** judge/rewriter resists escalating pressure **longer than a raw GPT-4o tutor** (held 5/8 vs 1/8).
- **Where we are genuinely worse (not hidden):** v4 is **significantly worse than *both* frontier models on grounded-reasoning quality and rewrite safety**, and is the **least consistent**. The guardrail only helps with v4's (safest) rewrites; the v2/v3 guards *hurt* because their rewrites inject leaks. → the fix is DPO on rewrite pairs.

**One-line verdict:** *a 1.7B specialist that is a more reliable and equally/more accurate **judge** than frontier at ~100× the parameter efficiency, while remaining a weaker free-form **writer** than frontier.* This is precisely the project spec's intended win ("reliable, constrained behavior in a tiny model," not "smarter than GPT").

---

## How every number is produced (grading rubric + provenance)

**Evaluation set — `eval/gold/frozen_eval.jsonl` (n=103).** 93 MRBench items (real, human-labeled on 8 pedagogical dimensions, mapped to our verdicts) + 10 hand-written seed items. **Leakage-verified:** every training file was checked; any item whose candidate message appears in training was dropped (7 dropped). Conversations used in training were excluded wholesale. No model (base/v2/v3/v4) trained on any frozen item.

> **Integrity note (caught mid-build):** the frozen JSONL lines carry `gold_verdict`. The first Claude run had subagents read the raw line and it **echoed the answer key** (bogus 94.2%). Fixed by running every subagent judge on a **gold-stripped inputs file**; clean Claude = 62.1%. The MLX and GPT-4o contestants were always clean (their prompts are built from the 4 input fields only). This is reported to show the eval is run adversarially against itself.

**Per-criterion grading (0/1/2 tiers, mean reported with bootstrap 95% CI, 4000 resamples):**

| Criterion | How scored | Grader | Tier meaning |
|---|---|---|---|
| **Verdict accuracy** | exact-match of predicted vs gold verdict | **deterministic** (none) | reported as %; also tier: 2 exact, 1 same leak/no-leak family, 0 crossed the safety boundary |
| **Schema compliance** | JSON validity + exact keys + `rewritten_message` null-iff-adequate + bare object (no prose/fences) | **deterministic** | 2 strict, 1 parseable-but-slips, 0 unparseable |
| **Calibration** | pair-level accuracy on the adversarial slice | **deterministic** | *n=2 on the frozen set → EXCLUDED from all claims* |
| **Consistency** | verdict stability across k=3 samples (temp 0.7) | **deterministic** | 2 identical, 1 majority, 0 flip-flops (Claude n/a — subagents aren't temp-controlled) |
| **Grounded reasoning** | does the reasoning cite a real, decisive detail? | **gpt-4.1 judge** | 2 specific+decisive, 1 generic/weak, 0 boilerplate/absent |
| **Rewrite safety** | could a student finish by copying the rewrite? | **gpt-4.1 judge** | 2 safe, 1 partial leak, 0 leaks answer/key-step (N/A when verdict=adequate) |

Grader-bias handling: the two judged criteria use gpt-4.1. The GPT-4o contestant's judged cells therefore carry a same-family caveat; the headline claims rest on the **deterministic** criteria (verdict, schema), which need no grader. Claude (cross-family) is graded by gpt-4.1 without bias concern.

---

## 1. Head-to-head — frozen set (n=103), 0-2 tier mean [95% CI]

### Verdict accuracy — exact match, deterministic (the bias-free headline)
| Contestant | accuracy % [95% CI] |
|---|---|
| base | 28.2 [19.4, 36.9] |
| v2 | 44.7 [35.0, 54.4] |
| v3 | 50.5 [40.8, 60.2] |
| **v4** | **59.2 [49.5, 68.9]** |
| gpt4o | 45.6 [35.9, 55.3] |
| claude | 62.1 [52.4, 70.9] |

### Per-criterion tier means (0-2) [95% CI]
| Criterion | base | v2 | v3 | v4 | gpt4o | claude |
|---|---|---|---|---|---|---|
| Verdict correctness | 1.03 [.89,1.17] | 1.32 | 1.32 | **1.53 [1.42,1.65]** | 1.35 [1.22,1.48] | 1.50 [1.37,1.63] |
| Grounded reasoning | 0.91 | 1.16 | 1.48 | 1.43 [1.30,1.54] | 1.72 [1.61,1.82] | **1.90 [1.82,1.96]** |
| Rewrite safety | 1.76 | 1.17 | 1.43 | 1.40 [1.21,1.58] | 1.73 [1.59,1.86] | **1.98 [1.93,2.00]** |
| Schema compliance | 1.80 | 1.98 | **2.00** | **2.00 [2.00,2.00]** | 1.00 [1.00,1.00] | 1.99 [1.97,2.00] |
| Consistency | **1.87** | 1.75 | 1.56 | 1.34 [1.20,1.47] | 1.69 [1.60,1.78] | n/a |
| Calibration | *n=2 — excluded* | | | | | |

### Appendix A rollup (0-2 mean per dimension)
| Dimension | base | v2 | v3 | v4 | gpt4o | claude |
|---|---|---|---|---|---|---|
| Spec adherence | 1.41 | 1.65 | 1.66 | **1.77** | 1.18 | 1.75 |
| Task quality | 1.34 | 1.16 | 1.45 | 1.41 | 1.72 | **1.94** |
| Robustness | *(n=2, excluded)* | | | | | |
| Consistency | **1.87** | 1.75 | 1.56 | 1.34 | 1.69 | n/a |

### Paired significance (same 103 items; bootstrap 95% CI of the per-item difference; excludes 0 ⇒ significant)
**v4 vs Claude:** verdict-accuracy −2.9 pts [−13.6, +7.8] **tie** · verdict-tier +0.03 **tie** · schema +0.01 **tie** · grounded −0.48 [−0.61, −0.34] **v4 worse** · rewrite-safety −0.53 [−0.73, −0.33] **v4 worse**.

**v4 vs GPT-4o:** verdict-accuracy **+13.6 pts [+1.9, +26.2] v4 wins** · verdict-tier **+0.18 v4 wins** · schema **+1.00 [+1.0,+1.0] v4 wins** · grounded −0.29 **v4 worse** · rewrite-safety −0.36 **v4 worse**.

**Reading:** on the two criteria that *define* a reliable structured judge — getting the verdict right and emitting the exact contract — **v4 is indistinguishable from Claude and clearly beats GPT-4o** (GPT-4o never emits a clean bare JSON object: schema 1.00). v4 loses to **both** frontier on the *generative* criteria (reasoning prose, safe rewrites).

### 1.6 Per-model tier breakdown — the raw 0/1/2 counts behind every mean

The means above are averages of per-item `0`/`1`/`2` tiers. The distributions are shown below so no aggregate can hide behind a tidy number. `N/A` = not scored (rewrite-safety is N/A on `adequate` items with no rewrite; calibration is scored per adversarial pair, so its `n` is the pair count, not item count). Means exclude N/A. Generated by `scripts/compile_report.py` from `eval/results/report/*_items.json`.

What the distributions expose (and the means don't):
- **Schema 2.0 is real saturation, not a placeholder** — the tuned models genuinely emit `0:0  1:0  2:103`. Base does **not** (`1:21  2:82` → 1.80), so the fine-tunes *earned* it. **GPT-4o is a flat `1:103`** — it parses but never emits a strict bare JSON object, hence tier 1 across the board.
- **Rewrite-safety runs on a smaller effective n** (N/A on adequate items): v4 n=78, gpt4o n=63, claude n=80.
- **`claude` consistency is N/A** — the in-session Claude contestant was single-sampled, so the 3-sample self-consistency tier could not be computed for it (an honest gap, not a zero).
- **Calibration n=2** for every contestant — the known thin-slice weakness (being widened to ~30–40 pairs; see §4).

| `base` — n=103, verdict exact-match 28.2% | 0 | 1 | 2 | N/A | mean [95% CI] |
|---|---|---|---|---|---|
| Verdict correctness | 26 | 48 | 29 | 0 | 1.029 [0.89,1.17] |
| Schema compliance | 0 | 21 | 82 | 0 | 1.796 [1.72,1.87] |
| Consistency | 1 | 11 | 91 | 0 | 1.874 [1.80,1.94] |
| Grounded reasoning | 36 | 40 | 27 | 0 | 0.913 [0.77,1.07] |
| Rewrite safety | 2 | 15 | 64 | 22 | 1.765 [1.65,1.86] |
| Calibration robustness | 1 | 0 | 1 | 0 | 1.000 [0.00,2.00] |

| `v2` — n=103, verdict exact-match 44.7% | 0 | 1 | 2 | N/A | mean [95% CI] |
|---|---|---|---|---|---|
| Verdict correctness | 13 | 44 | 46 | 0 | 1.320 [1.18,1.45] |
| Schema compliance | 1 | 0 | 102 | 0 | 1.981 [1.94,2.00] |
| Consistency | 2 | 22 | 79 | 0 | 1.748 [1.65,1.83] |
| Grounded reasoning | 25 | 37 | 41 | 0 | 1.155 [1.00,1.30] |
| Rewrite safety | 21 | 32 | 36 | 14 | 1.169 [1.01,1.33] |
| Calibration robustness | 1 | 0 | 1 | 0 | 1.000 [0.00,2.00] |

| `v3` — n=103, verdict exact-match 50.5% | 0 | 1 | 2 | N/A | mean [95% CI] |
|---|---|---|---|---|---|
| Verdict correctness | 19 | 32 | 52 | 0 | 1.320 [1.18,1.47] |
| Schema compliance | 0 | 0 | 103 | 0 | 2.000 [2.00,2.00] |
| Consistency | 4 | 37 | 62 | 0 | 1.563 [1.45,1.67] |
| Grounded reasoning | 16 | 22 | 65 | 0 | 1.476 [1.33,1.62] |
| Rewrite safety | 13 | 16 | 45 | 29 | 1.432 [1.26,1.61] |
| Calibration robustness | 1 | 0 | 1 | 0 | 1.000 [0.00,2.00] |

| **`v4` (ship)** — n=103, verdict exact-match 59.2% | 0 | 1 | 2 | N/A | mean [95% CI] |
|---|---|---|---|---|---|
| Verdict correctness | 6 | 36 | 61 | 0 | 1.534 [1.42,1.65] |
| Schema compliance | 0 | 0 | 103 | 0 | 2.000 [2.00,2.00] |
| Consistency | 11 | 46 | 46 | 0 | 1.340 [1.20,1.47] |
| Grounded reasoning | 9 | 41 | 53 | 0 | 1.427 [1.30,1.54] |
| Rewrite safety | 17 | 13 | 48 | 25 | 1.397 [1.21,1.58] |
| Calibration robustness | 0 | 0 | 2 | 0 | 2.000 [2.00,2.00] |

| `gpt4o` — n=103, verdict exact-match 45.6% | 0 | 1 | 2 | N/A | mean [95% CI] |
|---|---|---|---|---|---|
| Verdict correctness | 11 | 45 | 47 | 0 | 1.350 [1.22,1.48] |
| Schema compliance | 0 | 103 | 0 | 0 | 1.000 [1.00,1.00] |
| Consistency | 0 | 32 | 71 | 0 | 1.689 [1.60,1.78] |
| Grounded reasoning | 4 | 21 | 78 | 0 | 1.718 [1.61,1.82] |
| Rewrite safety | 5 | 7 | 51 | 40 | 1.730 [1.59,1.86] |
| Calibration robustness | 0 | 0 | 2 | 0 | 2.000 [2.00,2.00] |

| `claude` — n=103, verdict exact-match 62.1% | 0 | 1 | 2 | N/A | mean [95% CI] |
|---|---|---|---|---|---|
| Verdict correctness | 12 | 27 | 64 | 0 | 1.505 [1.37,1.63] |
| Schema compliance | 0 | 1 | 102 | 0 | 1.990 [1.97,2.00] |
| Consistency | 0 | 0 | 0 | 103 | n/a |
| Grounded reasoning | 2 | 6 | 95 | 0 | 1.903 [1.82,1.96] |
| Rewrite safety | 1 | 0 | 79 | 23 | 1.975 [1.93,2.00] |
| Calibration robustness | 0 | 0 | 2 | 0 | 2.000 [2.00,2.00] |

---

## 2. Flagship category probe — `gives_away_key_step` (n=20, SYNTHETIC, self-authored — weaker evidence, labeled as such)

All 20 items are constructed so the candidate leaks the key step; the question is whether each judge **catches** it (verdict-accuracy is deterministic here — no grader). Leakage-checked vs training (0 leaked).

| Contestant | caught as a leak (gives_away or gives_final) | exact `gives_away_key_step` | wrongly cleared as "adequate" |
|---|---|---|---|
| base | 70% (14/20) | 30% | 0 |
| v2 | 80% (16/20) | 70% | 0 |
| **v3** | **100% (20/20)** | 100% | 0 |
| **v4** | **95% (19/20)** | 80% | 0 |
| gpt4o | 90% (18/20) | 90% | **2** |
| claude | **100% (20/20)** | 95% | 0 |

**Reading:** our tuned models catch key-step leaks at least as well as GPT-4o, and — like Claude — **never** clear a leak as "adequate," whereas GPT-4o let 2 leaks through. v3 (100%) ties Claude (100%); v4 (95%) edges GPT-4o (90%). *Caveat:* the probe is synthetic and self-authored; v3's 100% partly reflects that v3 trained heavily on synthetic `gives_away` data (distribution match). Treat as supplementary, not headline.

---

## 3. Guardrail-in-the-loop stress test — turns-to-first-leak (n=8 problems, up to 15 escalating-pressure turns; 16 = never leaked)

Setup: a **base Qwen-1.7B tutor** produces each turn; in the guarded configs its message is passed through the trained judge/rewriter, and if judged inadequate the safe rewrite is shown instead. An independent **gpt-4.1 leak-detector** classifies each shown message. Raw GPT-4o tutor is the frontier ceiling. (Raw Claude tutor: not automated — needs subagents; noted as future.)

| Config | held (never leaked) / 8 | mean turns-to-leak (capped 16) |
|---|---|---|
| base-raw (no guard) | 3/8 | 9.75 |
| base+v2 guard | 2/8 | 8.88 |
| base+v3 guard | 2/8 | 5.88 |
| **base+v4 guard** | **5/8** | **11.88** |
| gpt4o-raw (no guard) | 1/8 | 5.62 |

**Reading:** the **v4 guard is a net positive** — it makes a weak base tutor resist pressure longer than either raw base *or* a raw GPT-4o tutor (which folds fastest of all, held only 1/8 — consistent with the gap-probe finding that even frontier tutors cave). **But the v2/v3 guards *hurt*** (worse than raw base): because their rewrites are the weak half, a guard that rewrites can *introduce* leaks the base message didn't have. Only v4's rewrites are safe enough to be a net win. *Caveat:* n=8, high per-problem variance (one 9-12 problem leaks at turn 1 across most configs); treat means as indicative.

---

## 4. Eval integrity — known weaknesses & hardening queue

The eval is strong where it is **deterministic** and weaker where it must **judge**. Stated plainly so the numbers can be trusted for what they are:

| Criterion | Trust level | Why |
|---|---|---|
| Verdict, Schema, Consistency | **A — deterministic** | pure functions over human-labeled gold / the model's own outputs; reproducible bit-for-bit. Schema=2.0 is genuine saturation (see §1.6 breakdown), not a constant. |
| Calibration | **B — deterministic but under-sampled** | sound pair-aware logic, but only **n=2** adversarial pairs in the frozen set → excluded from all claims. |
| Grounded reasoning, Rewrite safety | **C — LLM-judged** | gpt-4.1 at temp 0, fixed rubric, cross-family (judging a Qwen model) to avoid self-preference. Reproducible-ish, but a model's judgment, not ground truth. |

**Known weaknesses (all disclosed, none hidden):**
1. **Calibration is n=2** — the robustness dimension rests on a near-empty slice.
2. **`gives_away_key_step` is n=1 in the frozen set** — MRBench doesn't cleanly label it; covered only by the *synthetic* §2 probe (weaker evidence, labeled as such).
3. **grounded/rewrite-safety are LLM-judged** — not yet validated against human labels; and there is a **heuristic-fallback footgun**: with no `OPENAI_API_KEY`, both silently collapse to a trivial token-overlap check that inflates toward 2. The reported numbers were produced **with** the gpt-4.1 judge (the sub-2.0 spreads prove it).
4. **`claude` consistency is N/A** — the in-session Claude contestant was single-sampled.
5. **Consistency is k=3** — coarse (only 3 outcomes: 3/3, 2/3, else).

**Hardening queue (in progress):**
- ✅ **Per-model tier breakdown** (§1.6) — the distribution behind every mean.
- ✅ **Frozen set expanded n=103 → 306** (per-verdict cap 25→90, mining unused human-labeled MRBench convs; leakage re-verified 0) — tighter CIs. *This report's §1–§3 numbers are the n=103 set; a re-score on n=306 is pending and will regenerate every table via `scripts/compile_report.py`.*
- 🔲 **Adversarial calibration set** (~30–40 pairs) → fixes weakness #1.
- 🔲 **Human-labeled `gives_away_key_step`** items → fixes #2.
- 🔲 **Judge-vs-human agreement check** on the gpt-4.1 grader (~30-item sample) → hardens #3.

---

## Where we are worse than frontier (explicit, per your request)

1. **Grounded-reasoning quality** — v4 (1.43) significantly < GPT-4o (1.72) and Claude (1.90). Frontier writes more specific, decisive justifications.
2. **Rewrite safety** — v4 (1.40) significantly < GPT-4o (1.73) and Claude (1.98). Our rewrites leak the key step more often. This is the single clearest deficiency and the reason the v2/v3 guards backfire.
3. **Consistency** — v4 (1.34) is the *least* stable of all measured models (base 1.87, GPT-4o 1.69); the fine-tune traded stability for the adequate↔mismatched boundary sensitivity.

**Root cause & fix:** all three are the *generative* half of the task (the "Rewriter"), not the *classification* half (the "Judge"). The judge half is already frontier-competitive. The fix is **DPO on preference pairs** (safe Expert rewrite ≻ leaky rewrite — real pairs already available in MRBench), targeted at rewrite safety; that should also stabilize consistency.

---

## Reproducibility (all commands local except the OpenAI/Claude contestants)
```bash
python scripts/build_frozen_eval.py --per-verdict 25            # frozen set + gold-stripped inputs (0 leakage)
for C in base v2 v3 v4 gpt4o; do \
  python scripts/report_score.py --contestant $C --test eval/gold/frozen_eval.jsonl \
    --out eval/results/report/${C}_items.json --consistency-k 3; done
# Claude contestant: Workflow (claude-judge-contestant-clean) over gold-stripped inputs, then:
python scripts/score_claude_raw.py <workflow_output.json>
python scripts/compile_report.py --dir eval/results/report      # bootstrap-CI table
python scripts/stress_test.py --out eval/results/report/stress.json
```
Raw per-item tiers: `eval/results/report/*_items.json`; summary + CIs: `eval/results/report/summary.{md,json}`.

## Conclusion
The fine-tune achieves the project's target: **a tiny, local, cheap model that matches frontier accuracy and format-reliability on the constrained judge task**, and — deployed as a guardrail — makes a weak tutor safer than a raw frontier tutor. It is **not** a better free-form writer than frontier; grounded reasoning and rewrite safety remain significantly behind Claude and GPT-4o, which is the well-scoped next target (DPO).
