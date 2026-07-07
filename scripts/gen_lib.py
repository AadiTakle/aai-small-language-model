"""Data-generation pipeline: seed topics, teacher prompts, junk generator, quality gate.

This is the canonical (portable) description of how training data is produced:

- REAL data (v1): a two-stage teacher distillation. Stage 1 fabricates a realistic
  short tutoring exchange whose final tutor message exemplifies a *target* verdict;
  Stage 2 is an INDEPENDENT judge that labels that message (verdict + grounded
  reasoning + a safe Socratic rewrite). The Stage-2 label is trusted as gold.
  The prompt templates below (STAGE1_TEMPLATE / STAGE2_JUDGE_TEMPLATE) are the exact
  instructions handed to the teacher. In this repo the teacher is driven by Cursor
  `Task` subagents (frontier model, no API key); the same templates port directly to
  an API call (`ANTHROPIC_BASE_URL` / OpenAI-compatible) — see docs/day2_run_report.md.

- JUNK data (smoke): `make_junk_examples()` produces deterministic, schema-valid but
  formulaic examples with NO LLM, so the generate->train->eval loop can be proven
  end-to-end cheaply (the smoke test only checks plumbing, not quality).

Raw example schema (one dict per training tuple):
    {id, band, problem, correct_solution, final_answer, key_step,
     conversation_history[list[str]], candidate_message,
     verdict, reasoning, rewritten_message (null iff adequate), slice}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from socratic_tutor.schema import VERDICTS, validate_output

# --------------------------------------------------------------------------- #
# Seed topics (ground truth). Spread across K-12 bands. Extend freely.
# --------------------------------------------------------------------------- #
TOPICS: list[dict] = [
    {"id": "k2-add", "band": "K-2",
     "problem": "Sam has 8 apples. His friend gives him 5 more. How many apples now?",
     "correct_solution": "8 + 5 = 13.", "final_answer": "13",
     "key_step": "Recognize this is addition: 8 + 5."},
    {"id": "k2-sub", "band": "K-2",
     "problem": "There are 12 birds on a wire. 7 fly away. How many are left?",
     "correct_solution": "12 - 7 = 5.", "final_answer": "5",
     "key_step": "Recognize this is subtraction: 12 - 7."},
    {"id": "k2-ten", "band": "K-2",
     "problem": "What is 9 + 6?",
     "correct_solution": "Make a ten: 9 + 1 = 10, then + 5 = 15.", "final_answer": "15",
     "key_step": "Bridge through ten: 9 + 1 = 10, then add the remaining 5."},
    {"id": "35-mult", "band": "3-5",
     "problem": "What is 7 x 6?",
     "correct_solution": "7 x 6 = 42.", "final_answer": "42",
     "key_step": "Use a known fact: 7 x 5 = 35, then add one more 7."},
    {"id": "35-area", "band": "3-5",
     "problem": "A rectangle is 6 cm long and 4 cm wide. What is its area?",
     "correct_solution": "Area = 6 x 4 = 24 square cm.", "final_answer": "24",
     "key_step": "Area of a rectangle = length x width."},
    {"id": "35-perim", "band": "3-5",
     "problem": "What is the perimeter of a square with side 5?",
     "correct_solution": "Perimeter = 4 x 5 = 20.", "final_answer": "20",
     "key_step": "A square has 4 equal sides; perimeter = 4 x side."},
    {"id": "35-unit", "band": "3-5",
     "problem": "A store sells pencils at 3 for $1.20. How much is 1 pencil?",
     "correct_solution": "1.20 / 3 = 0.40.", "final_answer": "0.40",
     "key_step": "Divide total price by the number of pencils."},
    {"id": "68-frac", "band": "6-8",
     "problem": "What is 3/4 + 1/8?",
     "correct_solution": "3/4 = 6/8, so 6/8 + 1/8 = 7/8.", "final_answer": "7/8",
     "key_step": "Convert 3/4 to 6/8 using a common denominator of 8."},
    {"id": "68-pct", "band": "6-8",
     "problem": "A shirt costs $20 and is 25% off. What is the sale price?",
     "correct_solution": "25% of 20 = 5; 20 - 5 = 15.", "final_answer": "15",
     "key_step": "Find 25% of 20 (=5), then subtract from 20."},
    {"id": "68-ratio", "band": "6-8",
     "problem": "A recipe uses 2 cups flour per 3 cookies. How much flour for 12 cookies?",
     "correct_solution": "12 / 3 = 4 batches; 4 x 2 = 8 cups.", "final_answer": "8",
     "key_step": "Find the scale factor (12/3 = 4), then scale the flour."},
    {"id": "912-lin", "band": "9-12",
     "problem": "Solve for x: 2x + 3 = 11.",
     "correct_solution": "2x = 8, so x = 4.", "final_answer": "4",
     "key_step": "Subtract 3 from both sides to isolate the 2x term."},
    {"id": "912-quad", "band": "9-12",
     "problem": "Solve x^2 - 5x + 6 = 0.",
     "correct_solution": "(x-2)(x-3)=0, so x = 2 or x = 3.", "final_answer": "2 or 3",
     "key_step": "Factor into (x-2)(x-3); find two numbers multiplying to 6 and adding to 5."},
    {"id": "912-slope", "band": "9-12",
     "problem": "What is the slope of the line through (1, 2) and (4, 11)?",
     "correct_solution": "(11-2)/(4-1) = 9/3 = 3.", "final_answer": "3",
     "key_step": "Slope = rise over run = (y2-y1)/(x2-x1)."},
]

# --------------------------------------------------------------------------- #
# Two-stage teacher prompt templates (the reproducible pipeline spec)
# --------------------------------------------------------------------------- #
STAGE1_TEMPLATE = """You are simulating a K-12 math tutoring chat to create ONE training example.

Problem: {problem}
Correct solution (do not reveal to the student): {correct_solution}
Grade band: {band}

Write a SHORT realistic exchange (1-3 student turns, each prefixed "Student: ") ending
right before a tutor reply, then write a single candidate TUTOR message that is a clear
example of this category: "{target_verdict}".

Category meanings:
- adequate: scaffolds with a question/hint; never states the answer or the one key step.
- gives_final_answer: states the final answer {final_answer} (explicitly or paraphrased).
- gives_away_key_step: hands over the key step ("{key_step}") so the rest is trivial.
- mismatched_calibration: a real hint pitched at the wrong level for what the student showed.
- vague_unhelpful: generic encouragement with no actionable, problem-specific scaffolding.

Return ONLY JSON: {{"conversation_history": ["Student: ..."], "candidate_message": "..."}}"""

STAGE2_JUDGE_TEMPLATE = """You are a strict grader for a Socratic math tutor, using a fixed taxonomy.

Problem: {problem}
Correct solution (ground truth, never shown to the student): {correct_solution}
Final answer: {final_answer}
Key step: {key_step}
Conversation so far:
{history}
Candidate tutor message to grade: {candidate_message}

Classify the candidate message into exactly one verdict from:
{verdicts}
Definitions:
- adequate: neither states the answer nor the key step; calibrated to the student's attempt.
- gives_final_answer: states the final answer, explicitly or as a close paraphrase.
- gives_away_key_step: reveals the single insight/operation that trivializes the rest.
- mismatched_calibration: a genuine hint at the wrong level (too basic or too advanced).
- vague_unhelpful: generic, no actionable problem-specific scaffolding.

Then, if the verdict is NOT "adequate", write a rewritten_message: a calibrated Socratic
hint grounded in the student's most recent message that NEVER states the final answer and
NEVER hands over the key step. If the verdict IS "adequate", set rewritten_message to null.

reasoning must cite a SPECIFIC detail from the problem/solution/conversation (not generic).
Return ONLY JSON: {{"verdict": "...", "reasoning": "...", "rewritten_message": null_or_string}}"""


def stage1_prompt(topic: dict, target_verdict: str) -> str:
    return STAGE1_TEMPLATE.format(target_verdict=target_verdict, **topic)


def stage2_prompt(topic: dict, conversation_history: list[str], candidate_message: str) -> str:
    return STAGE2_JUDGE_TEMPLATE.format(
        history="\n".join(conversation_history) or "(none yet)",
        candidate_message=candidate_message,
        verdicts=", ".join(VERDICTS),
        **topic,
    )


# --------------------------------------------------------------------------- #
# Quality gate (used to filter both junk and real generations)
# --------------------------------------------------------------------------- #
def passes_quality_gate(row: dict) -> tuple[bool, list[str]]:
    errs: list[str] = []
    for k in ("problem", "correct_solution", "candidate_message", "verdict", "reasoning"):
        if not isinstance(row.get(k), str) or not row[k].strip():
            errs.append(f"missing/empty {k}")
    hist = row.get("conversation_history")
    if not isinstance(hist, list) or not all(isinstance(h, str) for h in hist):
        errs.append("conversation_history must be list[str]")
    # Reuse the output-schema validator on the label triple.
    ok, out_errs = validate_output({
        "verdict": row.get("verdict"),
        "reasoning": row.get("reasoning", ""),
        "rewritten_message": row.get("rewritten_message"),
    })
    if not ok:
        errs.extend(out_errs)
    # Rewrite must not leak the literal final answer.
    rw = row.get("rewritten_message")
    fa = str(row.get("final_answer", "")).strip().lower()
    if isinstance(rw, str) and fa and fa in rw.lower():
        errs.append("rewrite leaks final answer")
    return (len(errs) == 0), errs


def assistant_json(row: dict) -> str:
    """The gold assistant target string for a raw row."""
    return json.dumps(
        {"verdict": row["verdict"], "reasoning": row["reasoning"],
         "rewritten_message": row.get("rewritten_message")},
        ensure_ascii=False,
    )


# --------------------------------------------------------------------------- #
# Junk generator (smoke test only — deterministic, no LLM)
# --------------------------------------------------------------------------- #
def _junk_for(topic: dict, verdict: str) -> dict:
    p, fa, ks = topic["problem"], topic["final_answer"], topic["key_step"]
    history = ["Student: I'm working on this one.", "Student: I'm not totally sure what to do."]
    if verdict == "gives_final_answer":
        msg = f"The answer is {fa}."
        reasoning = f"States the final answer {fa} outright."
        rw = "What is one thing you could try as a first step here?"
    elif verdict == "gives_away_key_step":
        msg = f"Here's the trick you need: {ks}"
        reasoning = "Hands over the key step so the rest is trivial."
        rw = "What do you notice about the numbers in this problem?"
    elif verdict == "mismatched_calibration":
        msg = "Let me re-explain what numbers are from the very beginning."
        reasoning = "Re-explains basics far below the student's demonstrated level."
        rw = "You're close - what did your most recent step give you?"
    elif verdict == "vague_unhelpful":
        msg = "Keep trying, you can totally do it!"
        reasoning = "Generic encouragement with no actionable, problem-specific step."
        rw = "Which specific part of the problem feels stuck right now?"
    else:  # adequate
        msg = "What operation do you think this problem is asking for, and what makes you say that?"
        reasoning = "Asks a guiding question without revealing the answer or key step."
        rw = None
    return {
        "id": f"junk-{topic['id']}-{verdict}", "band": topic["band"],
        "problem": p, "correct_solution": topic["correct_solution"],
        "final_answer": fa, "key_step": ks,
        "conversation_history": history, "candidate_message": msg,
        "verdict": verdict, "reasoning": reasoning, "rewritten_message": rw,
        "slice": "core",
    }


def make_junk_examples(n: int) -> list[dict]:
    """Deterministic, schema-valid junk examples cycling topics x verdicts."""
    rows: list[dict] = []
    i = 0
    while len(rows) < n:
        topic = TOPICS[i % len(TOPICS)]
        verdict = VERDICTS[i % len(VERDICTS)]
        row = _junk_for(topic, verdict)
        row["id"] = f"{row['id']}-{i}"
        ok, _ = passes_quality_gate(row)
        if ok:
            rows.append(row)
        i += 1
        if i > n * len(VERDICTS) * len(TOPICS):  # safety
            break
    return rows[:n]
