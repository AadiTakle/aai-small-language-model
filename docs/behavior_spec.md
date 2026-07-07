# Behavior Spec — Socratic Tutor Adequacy Judge & Rewriter

## Domain anchor

Math word/problem tutoring (single subject for v1 data/eval density; domain-generality as a stretch goal).

## The Spec

> Given a math problem, the conversation history so far, the correct solution (provided as ground truth, never shown to the student), and a candidate tutor message, the model always returns a single valid JSON object that (1) classifies the candidate message's adequacy against a fixed taxonomy of tutoring failure modes, grounding the classification in a specific cited detail from the problem/solution/history — never a bare label — and (2) whenever the verdict is not `adequate`, always includes a `rewritten_message` that is a calibrated Socratic hint: it never states the final answer, never hands over the single key step/insight that makes the problem trivial, and is grounded in the student's most recent attempt rather than generic encouragement.

This is a stranger-gradable pass/fail test: given any (problem, history, solution, candidate message) tuple, a rater can check the output is valid JSON matching the schema, the verdict matches the taxonomy definitions below, the reasoning cites a real detail (not generic), and — if present — the rewritten message contains neither the final answer nor the key step.

## Taxonomy (verdict values)

| Verdict | Definition |
| :--- | :--- |
| `adequate` | The message scaffolds productively: it neither states the answer nor the key step, and is calibrated to the student's current attempt. |
| `gives_final_answer` | The message states the actual final answer/result, explicitly or paraphrased closely enough to be equivalent. |
| `gives_away_key_step` | The message does not state the final answer, but hands over the single insight/technique that makes the rest of the problem trivial (removes the need for the student to find that step themselves). |
| `mismatched_calibration` | The message is a genuine hint, but is pitched at the wrong level for where the student currently is (either re-explaining something they've already demonstrated understanding of, or assuming a leap they haven't made yet). |
| `vague_unhelpful` | The message is generic encouragement or a non-answer ("keep trying!", "think about it more") that gives no actionable scaffolding tied to the actual problem or the student's specific attempt. |

## Output Schema

```json
{
  "verdict": "adequate | gives_final_answer | gives_away_key_step | mismatched_calibration | vague_unhelpful",
  "reasoning": "string — cites a specific detail from the problem, solution, or conversation history that grounds this verdict",
  "rewritten_message": "string | null — required (non-null) whenever verdict != adequate; null when verdict == adequate"
}
```

### Input format

```json
{
  "problem": "string — the math problem being worked on",
  "correct_solution": "string — ground-truth solution path, internal only, never shown to the student",
  "conversation_history": ["string", "..."],
  "candidate_message": "string — the tutor message being evaluated"
}
```

## Eval Criteria (base-vs-tuned)

1. **Verdict accuracy** - exact match against held-out labeled taxonomy on clean cases.
2. **Grounded reasoning** - reasoning references a real, checkable detail (not generic filler); can be checked by an LLM-judge against the specific problem/solution/history.
3. **Rewrite safety** - for any non-`adequate` verdict, the `rewritten_message` must not leak the final answer or the key step (adversarial check: does the rewrite still let a student solve the problem without further work?).
4. **Schema/format compliance** - always valid JSON matching the schema exactly, no prose outside the object, `rewritten_message` null iff verdict is `adequate`.
5. **Ambiguous-calibration robustness** - a held-out adversarial set of borderline `mismatched_calibration` vs. `adequate` cases, to check the model isn't just pattern-matching surface phrases (e.g. "the answer is" as a trigger phrase) rather than reasoning about actual content.

## Explicit non-goals (v1)

* Not claiming domain-generality beyond math for v1 data/eval (stretch: test transfer to a second domain, e.g. code debugging towards the end).
* Not judging tutor *tone*/encouragement quality independent of the taxonomy above. A message can be blunt but still `adequate` if it correctly withholds the answer/key step and is calibrated.
* Not handling multi-turn planning ("what should the tutor say three turns from now"). Judgment and rewrite are always for the single candidate message given the history so far.

## Project Governance — this spec is the master reference

Per [`project_spec.md`](project_spec.md), this Behavior Spec is simultaneously the **data-generation rubric**, the **evaluation criterion**, and the **brainlift POV** — everything downstream serves it. It is the single source of truth: if an implementation and this spec disagree, the spec wins, or the spec is deliberately updated *first* and the change propagated downstream.

**Locked — change only by editing this spec first, then propagating:**
- The 5-verdict taxonomy and its definitions.
- The output schema `{verdict, reasoning, rewritten_message}` (with `rewritten_message` null iff `adequate`) and the input schema.
- The 5 eval criteria.

**Traceability — every component maps back here:**

| Spec element | Implemented in |
| :--- | :--- |
| Taxonomy + output/input schema | `socratic_tutor/schema.py` (`VERDICTS`, `validate_output`, `validate_input`); `socratic_tutor/prompts.py` (`SYSTEM_PROMPT`) |
| Eval criteria 1–5 | `scripts/eval_harness.py`; `scripts/eval_rubric.py` (0–2 tiers + Appendix A rollup) |
| Data-gen rubric (all sources must conform) | `scripts/gen_lib.py` (synthetic); `scripts/ingest_mrbench.py`, `scripts/ingest_mathdial.py` (real data mapped to this taxonomy); `passes_quality_gate` |
| Brainlift POV | `docs/brainlift-socratic-tutor.md` |

**Locked implementation decisions (derived from, and consistent with, this spec — not changes to it):**
- Output is a single JSON object with **thinking disabled** (`enable_thinking=False`) to serve strict schema compliance (criterion 4).
- The eval scores each criterion on a **0/1/2 tier** and rolls the 5 criteria up into the `project_spec` Appendix A dimensions (Spec adherence, Task quality, Robustness) plus a **Consistency** dimension (k-sample stability). Tiering is a measurement refinement of the same criteria, not a new contract.
- Grounded-reasoning and rewrite-safety are scored by an independent OpenAI judge (gpt-4.1); the other criteria are deterministic.

**Conformance audit (2026-07-07):** the taxonomy, output/input schema, and criteria in code match this spec exactly — no drift. All additions (tier scoring, the Consistency dimension, thinking-off, real-data label mapping) are refinements consistent with the spec and `project_spec` Appendix A.
