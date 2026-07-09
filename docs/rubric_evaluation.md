# Rubric evaluation — is the taxonomy too vague / too strict?

**Verdict: the rubric conflates two axes of very different reliability. The *safety* axis is objective and appropriately strict; the *quality* axis (`adequate` vs `mismatched` vs `vague`) is too vague and is where nearly all the error lives.**

## Evidence
- **`mismatched_calibration` is the problem child.** Model recall on the corrected gold is **14%** (46/81 mismatched items were called `adequate`); it churned both directions in the reconcile (`mismatched→adequate` 48, `adequate→mismatched` 8+); and two independent frontier judges disagree on the `adequate/mismatched/vague` boundary ~**18-45%** of the time.
- **The leak boundary is strict but reliable.** Claude and GPT-5.5 judges agree **100%** on binary leak-vs-safe (on the earlier set); `gives_final` recall is 86%. The strictness ("revealing the pivotal relationship = `gives_away_key_step`") is *objective* and matches human calibration — keep it.
- **`adequate` is a catch-all** the model over-predicts (35% precision) — because the criteria for "adequate" vs "mismatched/vague" aren't crisp enough to separate.

## Diagnosis: two axes hiding in one 5-way label
1. **SAFETY** — does the message leak the answer/key step? (`gives_final_answer`, `gives_away_key_step` vs the rest.) **Objective, high inter-judge agreement (85-100%), reliably learnable.**
2. **QUALITY** — given it doesn't leak, is the hint good? (`adequate` = builds on the student's work + targets their actual error; `mismatched_calibration` = on-topic but misreads the error / re-explains known material; `vague_unhelpful` = not actionable/generic.) **Subjective, low agreement, requires modeling the student's exact knowledge state — this is the fuzzy zone.**

## Is it too vague or too strict?
- **Too vague:** the QUALITY axis. `mismatched_calibration` in particular has no crisp test separating it from `adequate` (both are non-leaking, on-topic hints) or from `vague` (both are "not great"). The current definition ("pitched at the wrong level") is a judgment call even careful humans/frontier models split on.
- **Appropriately strict:** the SAFETY axis. Don't loosen it — a strict, reliable leak definition is the whole product.

## Recommended changes
1. **Add an explicit decision tree** to the behavior spec + judge/training prompts (fold in the reconcile's `REVIEWER_CRITERIA`):
   1. Does it state the answer? → `gives_final_answer`.
   2. Does it reveal the pivotal step/relationship/operation-choice (incl. isomorphic examples)? → `gives_away_key_step`.
   3. Does it engage the student's *specific* latest work? If no → `vague_unhelpful`.
   4. Does it correctly target the student's *actual* error? If no (misdiagnoses / re-explains known) → `mismatched_calibration`.
   5. Student already reached the correct answer and it confirms → `adequate` (the confirmation rule — currently under-specified in the spec).
   6. Else → `adequate`.
2. **Report two scores, not one.** Lead with the **binary safety accuracy** (objective, ~85-100%, the thing that matters) and report the QUALITY 5-way separately with an acknowledged ambiguity ceiling. This is more honest than a single 5-way number dragged down by a fuzzy distinction.
3. **Consider whether QUALITY needs 3 levels or 2.** If `mismatched` vs `vague` can't be made reliable, a spec revision to `adequate` / `inadequate-nonleak` (dropping the mismatched/vague split) would raise accuracy at the cost of pedagogical granularity. *This is a spec change — propose to the owner, don't do unilaterally.* Keep the 5-way if the granularity is genuinely wanted, but only after adding the decision tree.
4. **Fix the tier rubric mechanics:**
   - **Schema** is saturated at 2.0 for tuned models → report it as pass/fail table-stakes, exclude from "beats frontier" claims.
   - **Calibration** rested on n=2 → build a real ~30-40-pair adversarial set (task #11) before it's cited.
   - **Grounded / rewrite-safety** LLM-judged → validated (κ 0.69 vs GPT-5.5, 98% self-consistent); keep, and prefer a non-Claude grader for cross-family fairness.

## Bottom line
The taxonomy isn't broken — it's *underspecified on the quality axis*. The single highest-leverage rubric fix is the **decision tree + confirmation rule** (crisper criteria for the model *and* the judge), which directly attacks the 14% `mismatched` recall. Loosening the safety definition would be a mistake; sharpening the quality definitions is the win.
