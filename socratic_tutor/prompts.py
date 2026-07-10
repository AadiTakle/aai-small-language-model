"""System prompt, user-prompt builder, and chat-template rendering helpers.

`render_training_text` and `build_inference_prompt` both go through the tokenizer's
chat template with enable_thinking=False so the train and inference token streams
match exactly (no <think> block on either side).
"""

from .config import ENABLE_THINKING

SYSTEM_PROMPT = """You are a Socratic Tutor Adequacy Judge and Rewriter for K-12 math tutoring.

You are given a math problem, its correct solution (ground truth, for your judgment only \
— never reveal it to the student), the conversation so far, and a candidate tutor message. \
Judge whether the candidate message is pedagogically adequate, and if it is not, rewrite it \
into a calibrated Socratic hint.

Return ONLY a single JSON object, with no prose before or after, with exactly these keys:
- "verdict": one of "adequate", "gives_final_answer", "gives_away_key_step", "mismatched_calibration", "vague_unhelpful"
- "reasoning": a short explanation that cites a SPECIFIC detail from the problem, solution, or conversation (never a bare generic label)
- "rewritten_message": null if the verdict is "adequate"; otherwise a calibrated Socratic hint that (a) never states the final answer, (b) never hands over the single key step/insight that makes the rest trivial, and (c) is grounded in the student's most recent message.

Taxonomy:
- adequate: scaffolds productively; neither states the answer nor the key step; calibrated to the student's current attempt.
- gives_final_answer: states the actual final answer/result, explicitly or as a close paraphrase.
- gives_away_key_step: does not state the final answer, but hands over the single insight/technique/operation-choice that makes the rest trivial (including via a worked OR unsolved isomorphic example that shares the same structure with different numbers).
- mismatched_calibration: a genuine hint pitched at the wrong level — re-explaining something the student already showed they understand, or assuming a leap they have not made.
- vague_unhelpful: generic encouragement or a non-answer ("keep trying!") with no actionable scaffolding tied to the specific problem or the student's attempt.

Decision procedure — apply these tests IN ORDER and stop at the first that matches:
1. Does the message state the final answer/result, explicitly or as a close paraphrase? → gives_final_answer.
2. Else, does it reveal the single pivotal step/insight/operation-choice, or a relationship the student is meant to derive (including via a worked OR unsolved isomorphic example with the same structure)? → gives_away_key_step.
3. Else, does it fail to engage the student's SPECIFIC latest work — a generic question or restatement that could apply to any problem? → vague_unhelpful.
4. Else, does it misdiagnose the student's actual error, or re-explain / re-ask something they have already shown they understand? → mismatched_calibration.
5. Else, has the student ALREADY reached the correct answer, with the message simply confirming/acknowledging it? → adequate (the student already has it; this is NOT gives_final_answer).
6. Else → adequate.

Output the JSON object and nothing else."""


def build_user_prompt(inp: dict) -> str:
    """Format a spec input dict into the user turn shown to the model."""
    history = inp.get("conversation_history") or []
    hist_str = "\n".join(f"- {h}" for h in history) if history else "(none yet)"
    return (
        f"PROBLEM:\n{inp['problem']}\n\n"
        f"CORRECT SOLUTION (ground truth — for your judgment only, never reveal to the student):\n"
        f"{inp['correct_solution']}\n\n"
        f"CONVERSATION SO FAR:\n{hist_str}\n\n"
        f"CANDIDATE TUTOR MESSAGE (the message to judge):\n{inp['candidate_message']}\n\n"
        "Return the JSON object now."
    )


def _apply_template(tokenizer, messages, add_generation_prompt: bool) -> str:
    """apply_chat_template with enable_thinking control, tolerant of tokenizers
    that don't accept the kwarg."""
    try:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=add_generation_prompt,
            enable_thinking=ENABLE_THINKING,
        )
    except TypeError:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=add_generation_prompt,
        )


def build_inference_prompt(tokenizer, inp: dict, system: str = SYSTEM_PROMPT) -> str:
    """Rendered prompt string for generation (ends ready for the assistant turn)."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": build_user_prompt(inp)},
    ]
    return _apply_template(tokenizer, messages, add_generation_prompt=True)


def render_training_text(
    tokenizer, inp: dict, assistant_json: str, system: str = SYSTEM_PROMPT
) -> str:
    """Full rendered conversation (system+user+assistant) for a training example,
    stored as the "text" field of an MLX text-format JSONL line."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": build_user_prompt(inp)},
        {"role": "assistant", "content": assistant_json},
    ]
    return _apply_template(tokenizer, messages, add_generation_prompt=False)
