# Day 2 Autonomous Run Report

Executed unattended overnight in Cursor from the plan `~/.claude/plans/ticklish-floating-pretzel.md`.
Goal: build the eval harness + data-gen pipeline, prove the full generate→train→eval loop
(Day 2 checkpoint), then roll into a real v1 dataset with first base-vs-tuned numbers.

**Headline: Day 2 checkpoint met AND the midweek base-vs-tuned gate cleared.** The tuned
model beats the base on spec adherence + robustness on two independent held-out sets.

## Git structure (all stacked, left unmerged for review)

```
main
 └─ dev
     └─ feat/eval-harness   b043704  shared lib + eval harness + base smoke
         └─ feat/data-gen   034d67a  two-stage teacher pipeline + dataset builder
             └─ feat/smoke-test  ea4cafe  50-junk end-to-end loop  ← PR #1 into dev
                 └─ feat/v1-dataset  0c3af6b  200-ex dataset + first real numbers
```

- **PR #1** (Day 2 checkpoint, `feat/smoke-test` → `dev`), open/unmerged:
  https://github.com/AadiTakle/aai-small-language-model/pull/1
- Nothing merged. Each phase committed on its own branch.

## Results

### Base model (no training) — the reliability gap
On the 10-item seed gold: **schema compliance 60%**, verdict accuracy 50%, calibration 50%.
The base model fails to emit valid schema-compliant JSON 40% of the time — the core gap.

### 50-junk smoke (plumbing only — quality NOT meaningful)
Loop ran end to end (~75s): generate → build (40/5/5) → QLoRA 80 iters (loss 3.9→0.01) →
base-vs-tuned table. Schema 60→100, calibration 50→100; grounded-reasoning collapsed
90→10 because junk reasoning cites no specifics (expected garbage-in/garbage-out, and a
useful confirmation the harness detects reasoning quality).

### v1 real dataset — first meaningful numbers
200 examples (5 teacher subagents), 97% gate pass, trained `adapters/v1` (155/19/20 split,
val loss 3.77→0.46, ~156 iters ≈ 4 epochs).

**v1 held-out gold (n=20):**

| Metric | base | tuned | Δ |
|---|---|---|---|
| Verdict accuracy | 55.0% | 90.0% | +35.0 |
| Grounded reasoning | 75.0% | 100.0% | +25.0 |
| Rewrite safety | 78.6% | 93.3% | +14.7 |
| Schema compliance | 75.0% | 100.0% | +25.0 |
| Calibration robustness | 50.0% | 100.0% | +50.0 |

**Seed gold (n=10, hand-written, never trained on):**

| Metric | base | tuned | Δ |
|---|---|---|---|
| Verdict accuracy | 50.0% | 80.0% | +30.0 |
| Grounded reasoning | 90.0% | 100.0% | +10.0 |
| Rewrite safety | 83.3% | 75.0% | −8.3 |
| Schema compliance | 60.0% | 100.0% | +40.0 |
| Calibration robustness | 50.0% | 100.0% | +50.0 |

Per the project rubric, a tuned model that beats base on **spec adherence** and
**robustness** is a win — achieved on both sets. Schema compliance hits 100% (gap closed)
and calibration robustness 50→100 on the adversarial slice.

## Data quality gate
The gate dropped **6/200** rows for "rewrite leaks final answer" (4 in 9-12 where the
answer coincides with an operand, 2 adversarial). Some are likely conservative false
positives (e.g. answer "3" appearing as a coordinate); acceptable to drop for v1.
Dataset: balanced 50/band, verdicts adequate=52 / mismatched=52 / others=32, 0 dup ids.

## Known issues / data-iteration candidates (for Day 4)
1. **Rewrite-safety dipped 83.3→75 on the seed set** (but rose 78.6→93.3 on the larger v1
   set) — likely small-sample noise on 6 non-adequate seed items; worth an error-analysis
   pass on the tuned rewrites.
2. **Grounded-reasoning + rewrite-safety criteria are heuristic** (deterministic token/number
   overlap). An injectable LLM-judge hook exists (`eval_harness.set_judge`) but is unused in
   unattended mode (no API key). Wiring a judge pass would sharpen criteria 2 & 3.
3. **Gate over-flags final-answer leaks** when the answer is a common small integer; consider
   a smarter check (answer in a leak-y context vs. incidental).

## Environment / adaptations
- **Teacher = Cursor `Task` subagents** (frontier model, no API key), since we ran in Cursor
  not Claude Code. The checked-in Stage-1/Stage-2 templates in `scripts/gen_lib.py` port
  directly to an API call (`ANTHROPIC_BASE_URL`/OpenAI-compatible) — future work.
- **Training runs fully locally** via `mlx_lm lora` on this Mac (no cloud GPU). `enable_thinking=False`
  + text-pre-rendered JSONL keeps train/inference token streams matched (no `<think>` leak).
- **Gap-probe findings incorporated** (not raw-mined — the ~450 workflow transcripts were
  lower-ROI than fresh generation): the real failure is `gives_away_key_step` (not
  `gives_final_answer`), isomorphic worked-examples and leak-as-correction are key vectors,
  and the Judge+Rewrite architecture held only 3/8 topics zero-shot — strong litmus-test
  evidence that this behavior needs training, not prompting.

## How to review / merge in the morning
```bash
# review the stack top-to-bottom
git log --oneline --graph main..feat/v1-dataset
git diff dev...feat/smoke-test       # the Day 2 checkpoint PR contents
git diff feat/smoke-test...feat/v1-dataset   # the v1 continuation

# re-run anything (all local, no API key needed)
.venv/bin/python scripts/eval_harness.py --test eval/gold/v1_test.jsonl --adapter-path adapters/v1 --out /tmp/recheck
.venv/bin/python scripts/run_v1.py           # full v1 rebuild+train+eval
.venv/bin/python scripts/dataset_stats.py data/raw/v1.jsonl

# merge the stack (fast-forward, bottom-up) once satisfied:
git checkout dev && git merge --ff-only feat/eval-harness feat/data-gen feat/smoke-test feat/v1-dataset
# (or merge PR #1 in the GitHub UI, then merge the v1 branch on top)
```
`adapters/` is gitignored — regenerate with `scripts/run_v1.py`.

## Suggested next steps
- **Day 4 data iteration**: error-analysis on the tuned model's remaining misses; add targeted
  examples for the weakest cell (rewrite safety on non-adequate).
- **Stretch**: wire an LLM-judge into criteria 2/3; build an adversarial robustness eval;
  DPO on on-spec vs off-spec rewrite pairs.
