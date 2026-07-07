"""Minimal local inference check. Usage: python scripts/infer.py "your prompt here" """

import sys

from mlx_lm import generate, load

MODEL = "mlx-community/Qwen3-1.7B-4bit"


def main():
    prompt = sys.argv[1] if len(sys.argv) > 1 else "In one sentence, what is 12 minus 7?"
    model, tokenizer = load(MODEL)
    messages = [{"role": "user", "content": prompt}]
    formatted = tokenizer.apply_chat_template(messages, add_generation_prompt=True)
    response = generate(model, tokenizer, prompt=formatted, max_tokens=200, verbose=True)
    print(response)


if __name__ == "__main__":
    main()
