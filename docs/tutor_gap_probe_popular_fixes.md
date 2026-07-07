# K-12 Math Tutor Gap Probe — Testing Popular Fixes

## Background research

Before designing new conditions, I looked at how real systems and the research literature approach this exact problem:

- **Khan Academy's Khanmigo** uses a Socratic system prompt as its primary defense ("never gives you the answer"), but backs it with a *separate* "math agent" that verifies calculations behind the scenes, and explicitly tracks "instances of giving the answer away" as a monitored guardrail metric — i.e., production systems don't rely on the system prompt alone. ([Khan Academy Blog](https://blog.khanacademy.org/how-khan-academy-is-building-a-better-ai-tutor-our-most-recent-learnings/), [Edutopia](https://www.edutopia.org/article/ai-tutors-work-guardrails/))
- **Self-Refine** (Madaan et al.): a single LLM drafts an output, then iteratively critiques and revises its own draft using only prompting, no fine-tuning — reported ~20% average gains across reasoning/dialogue tasks. ([selfrefine.info](https://selfrefine.info/), [learnprompting.org](https://learnprompting.org/docs/advanced/self_criticism/introduction))
- **Constitutional AI** and related critique-chain patterns: a model (often a *separate* pass or model) critiques and revises output against a written set of principles. Literature explicitly warns that **self-critique by the same model that generated the output is a known weak point** — "if the same type of model used to generate responses is also used to evaluate safety, both can be compromised in the same way" — and that independent critic models outperform vanilla self-rewriting. ([HiddenLayer research](https://www.hiddenlayer.com/research/same-model-different-hat))

This directly maps onto the project's own planned architecture (a separate Judge → Rewrite step), so the most relevant test is prompting a frontier model to run *that exact pattern* zero-shot and seeing whether it already works well enough to make fine-tuning unnecessary.

## Conditions tested (all on the same 8 topics / 6 pressure tactics from the prior pilot, layered on top of the best engineered prompt so far)

| # | Condition | Technique |
|---|---|---|
| 1 | Naive prompt (original pilot) | Plain tutor persona, no technique |
| 2 | Engineered prompt | Explicit leak definition + self-check + 2 few-shot examples |
| 3 | Self-Refine | Draft → same-model self-critique-and-revise pass |
| 4 | Judge+Rewrite | Draft → **independent** reviewer classifies against full taxonomy → forces a rewrite if non-adequate (mirrors the project's own planned architecture) |
| 5 | Surgical patch + sandwich | Bans *any* new problem instance (solved or not) for worked-example requests; repeats the core rule immediately before every reply |

## Results

| Condition | Topics fully holding boundary | Violation rate (of 56 judged turns) | Avg. turn of first violation |
|---|---|---|---|
| 1. Naive | 0/8 | 53.6% | 2.1 |
| 2. Engineered | 0/8 | 35.7% | 3.4 |
| 3. Self-Refine | 0/8 | 32.1% | 3.5 |
| 4. **Judge+Rewrite** | **3/8** | **25.0%** | 3.6 (on the 5 that broke) |
| 5. Surgical patch | 1/8 | 32.1% | 3.6 (on the 7 that broke) |

**Judge+Rewrite — mirroring the project's own planned architecture — is the best off-the-shelf fix found, and it's still not close to reliable.** It's the only condition where any topic held the full boundary (3 of 8), and it roughly halved the violation rate versus the plain engineered prompt. But **5 of 8 topics (62.5%) still leaked the key step even with a frontier model running the target architecture zero-shot.**

## Why Judge+Rewrite still fails: detection vs. rewrite-generation are separately hard

Decomposing the 14 remaining violations in the Judge+Rewrite condition against its own internal judge calls:

- **4/14 (29%) were pure detection misses** — the internal reviewer rated the draft "adequate" and the external (research) judge still caught a leak.
- **10/14 (71%) were correct detection followed by a failed fix** — the internal reviewer correctly flagged the draft as violating the rule, produced a rewrite, and the rewrite *still* leaked the key step per the external judge.

This is a clean, important result: the harder problem isn't spotting a bad tutor message, it's writing a good one. **This directly validates the project's own Eval Criterion 3 (rewrite safety) as a separate, harder target from verdict accuracy** — a model can correctly diagnose "this is bad" far more often than it can reliably generate a fix.

## Every patch either fails to close its target leak, or opens a new one

- **Self-Refine has a severe, distinct failure mode: it leaks its own reasoning.** In 39 of 56 turns (70%), the tutor's "final" message included visible self-critique text — e.g. one reply began *"The phrase 'add those to the pile' tells the student the operation (addition)... this is the key step — it removes any need for the student to decide..."* — literally naming the forbidden operation while explaining why it's forbidden, then appending a "fixed" reply afterward. The refine prompt explicitly said "output ONLY the final reply," and the model didn't reliably comply. **This means naive single-field self-refine is not just insufficient — it actively creates a new leak channel (the critique itself) that a taxonomy-only score doesn't even fully capture, since some contaminated turns were still scored "adequate" by the external judge despite visibly exposing the tutor's internal deliberation to the student.** In production this would also just be broken UX regardless of taxonomy compliance.
- **The surgical patch (banning all new-problem-instances) closed the isomorphic-example leak but opened a new one: verification-by-elimination.** With operation-naming and worked examples both explicitly banned, one tutor found a third channel — asking the student to check a wrong answer by reversing the operation (*"if 6 birds were left, and you added back the 7 that flew away, does that match how many we started with?"*). The judge flagged this as `gives_final_answer`: the arithmetic only "fails to match" for the wrong answer, so the check itself functions as a proof by elimination — the student can back out the right answer from the fact that the check failed, without the tutor ever naming a number or an operation.
- **The isomorphic-worked-example leak survived being targeted twice** (once in the "engineered" condition's few-shot example, once implicitly again here) — even the self-refine and judge-rewrite conditions, both explicitly built on the engineered persona that names this exact failure mode, still produced isomorphic-example leaks in multiple topics.

This is the shape of whack-a-mole, not resolution: patching a specific channel either doesn't fully close it, or the model routes around the patch into an equally leaky channel that wasn't named. That's consistent with the underlying capability — representing a genuinely safe scaffold under all six pressure tactics simultaneously — simply not existing reliably in the base model, rather than being one clever prompt away.

## Bottom line for the project's litmus test

Across five conditions — spanning the project's own naive baseline, the best hand-engineered prompt, and the two most-cited literature/production techniques for exactly this problem (Self-Refine and independent critique-and-rewrite) — **the best achievable result was 3/8 topics fully resistant, with 62.5% of topics still leaking under the identical target architecture the project intends to fine-tune.** No combination of prompting-only techniques found in the research or production literature closes the gap. This is strong, multi-angle evidence that the chosen behavior passes the "a well-prompted base model can't already do reliably" litmus test — and specifically that the hardest sub-problem to solve is not classification (the Judge half) but generation of a genuinely safe rewrite (the Rewriter half), which should shape both data density and eval weighting for v1.
