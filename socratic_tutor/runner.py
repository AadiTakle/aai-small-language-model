"""Model runner: load base (or base+adapter) once, generate at a chosen temperature.

Mirrors the loading/sampler approach validated in scripts/eval_harness.py, but keeps
the model resident so we can do both a greedy scoring pass and temp>0 consistency
sampling without reloading.
"""

from .config import MAX_TOKENS, MODEL
from .prompts import build_inference_prompt


def _sampler(temp: float):
    try:
        from mlx_lm.sample_utils import make_sampler

        return make_sampler(temp=temp)
    except Exception:
        return None


class Runner:
    def __init__(self, model_id: str = MODEL, adapter_path: str | None = None,
                 max_tokens: int = MAX_TOKENS):
        from mlx_lm import load

        self.model, self.tokenizer = load(model_id, adapter_path=adapter_path)
        self.max_tokens = max_tokens

    def generate(self, inp: dict, temp: float = 0.0) -> str:
        from mlx_lm import generate

        prompt = build_inference_prompt(self.tokenizer, inp)
        kwargs = {"max_tokens": self.max_tokens, "verbose": False}
        sampler = _sampler(temp)
        if sampler is not None:
            kwargs["sampler"] = sampler
        try:
            return generate(self.model, self.tokenizer, prompt=prompt, **kwargs)
        except TypeError:
            kwargs.pop("sampler", None)
            return generate(self.model, self.tokenizer, prompt=prompt, **kwargs)
