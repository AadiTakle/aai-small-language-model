# Rubric decision-tree ablation — NEGATIVE (don't adopt in the model prompt)

## Change tested
Implemented `docs/rubric_evaluation.md`'s top recommendation: an **ordered decision tree** + **explicit confirmation rule** added to `SYSTEM_PROMPT` (stop-at-first-match: answer→gives_final; pivotal step→gives_away; doesn't engage student work→vague; misdiagnoses error→mismatched; already-correct+confirmed→adequate; else adequate). Branch `feat/rubric-decision-tree`.

## Test (isolates the prompt)
Retrained `adapters/v6-rubric` on the **same v5 data** — only the prompt changed — then scored **each model with its own trained prompt** (v6-rubric = new, v5 = old, via git file-swap) on the corrected gold (n=299), `--no-judge` (deterministic verdict/schema; no TrueFoundry spend).

## Result
| model | verdict acc [95% CI] | verdict tier | `mismatched` recall | binary safety | `adequate` precision |
|---|---|---|---|---|---|
| v5 (original) | 52.5 [46,58] | 1.321 | 14% (10/74) | 80% | 44% |
| v6-rubric (decision tree) | 53.5 [48,59] | 1.251 | **5% (4/74)** | **73%** | 56% |

- **Overall accuracy: a wash** (CIs overlap).
- **Hurt the target + the safety metric:** `mismatched` recall 14%→5%; binary safety 80%→73%.
- **Helped one thing:** `adequate` precision 44%→56% (predicts `adequate` less indiscriminately — 151→93 times).

## Interpretation
1. **A 6-step ordered procedure is harder for a 1.7B model to execute reliably** than the flat taxonomy — the instruction-following cost exceeds the clarity benefit at this capacity. (Frontier judges wouldn't have this problem.)
2. We held the **training labels constant**; the decision tree may only pay off if the training data is **relabeled under it** too (prompt/label consistency). Untested here.

## Recommendation
- **Do NOT adopt the decision tree in the model's `SYSTEM_PROMPT`.** Keep `feat/rubric-decision-tree` unmerged as an experiment record.
- It may still help: (a) the **frontier judge/jury grading prompt** (capacity isn't the constraint there); (b) **human-facing spec documentation**.
- **Keep the confirmation rule** in the behavior spec regardless (it's a correct clarification, and cheap).
- If revisiting: try a **simpler** 2-line clarification rather than a 6-step tree, and/or relabel training under the new rubric before judging the effect.
