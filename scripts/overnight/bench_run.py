"""Phase 2: traditional LLM benchmarks. Fuse adapters/v6 -> dense MLX, then run GSM8K + MMLU
(sampled) on base Qwen3-1.7B-4bit AND fused-v6 via mlx_lm.evaluate. The fused-v6 run is a
catastrophic-forgetting check — lm-eval uses its own neutral task prompts (NOT our tutoring system
prompt), so it measures how much general math/knowledge ability survived the SFT specialization.
Writes eval/results/overnight/benchmarks.md/.json.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
from socratic_tutor import config  # noqa: E402

BENCH = REPO / "data" / "bench"
OUTDIR = REPO / "eval" / "results" / "overnight" / "bench"
BENCH.mkdir(parents=True, exist_ok=True)
OUTDIR.mkdir(parents=True, exist_ok=True)
# Published reference (Qwen3-1.7B, from the model card / tech report) — sanity anchor, not re-run.
PUBLISHED = {"note": "Qwen3-1.7B published refs (approx, non-thinking): GSM8K ~75%, MMLU ~62%"}


def log(m):
    print(f"[bench] {m}", file=sys.stderr, flush=True)


def fuse_v6():
    dst = BENCH / "fused_v6"
    if (dst / "config.json").exists():
        log("fused_v6 already present")
        return dst
    log("fusing adapters/v6 -> dense MLX ...")
    r = subprocess.run([".venv/bin/python", "-m", "mlx_lm", "fuse", "--model", config.MODEL,
                        "--adapter-path", "adapters/v6", "--save-path", str(dst)],
                       cwd=str(REPO), capture_output=True, text=True)
    if r.returncode != 0:
        log(f"fuse FAILED: {r.stderr[-400:]}")
        return None
    return dst


def evaluate(model, task, limit, num_shots, max_tokens, tag, apply_chat=True, batch_size=8):
    od = OUTDIR / tag
    od.mkdir(parents=True, exist_ok=True)
    cmd = [".venv/bin/mlx_lm.evaluate", "--model", str(model), "--tasks", task,
           "--limit", str(limit), "--num-shots", str(num_shots),
           "--batch-size", str(batch_size), "--output-dir", str(od)]
    if apply_chat:  # chat template helps generative GSM8K but BREAKS multiple-choice MMLU loglikelihood
        cmd += ["--apply-chat-template", "--chat-template-args", '{"enable_thinking": false}']
    if max_tokens:
        cmd += ["--max-tokens", str(max_tokens)]
    log(f"eval {tag}: {task} limit={limit} shots={num_shots}")
    r = subprocess.run(cmd, cwd=str(REPO), stdout=open(od / "run.log", "w"), stderr=subprocess.STDOUT)
    res = {}
    for f in od.glob("eval_*"):
        try:
            res.update(json.loads(f.read_text()))
        except Exception:  # noqa: BLE001
            pass
    return res


def gsm8k_score(res):
    d = res.get("gsm8k", {})
    return d.get("exact_match,strict-match"), d.get("exact_match,flexible-extract")


def mmlu_score(res):
    accs = [v.get("acc,none") for k, v in res.items() if isinstance(v, dict) and "acc,none" in v]
    accs = [a for a in accs if a is not None]
    return sum(accs) / len(accs) if accs else None


def main():
    models = {"base (Qwen3-1.7B-4bit)": config.MODEL}
    fv = fuse_v6()
    if fv:
        models["fused-v6 (SFT, forgetting check)"] = fv

    table = {}
    for name, m in models.items():
        # GSM8K: generative — chat template ON, batch 1 + short max_tokens (Metal OOMs on batched
        # long 5-shot sequences even at batch 4; batch 1 is the robust fix, verified).
        gsm = evaluate(m, "gsm8k", 250, 5, 256, f"{name.split()[0]}_gsm8k", apply_chat=True, batch_size=1)
        # MMLU: multiple-choice loglikelihood — comes out chance-level via this MLX/4-bit harness
        # (verified across chat-template + fewshot-multiturn configs); kept for completeness + caveated.
        mml = evaluate(m, "mmlu", 20, 5, None, f"{name.split()[0]}_mmlu", apply_chat=False, batch_size=16)
        strict, flex = gsm8k_score(gsm)
        table[name] = {"gsm8k_strict": strict, "gsm8k_flexible": flex, "mmlu_acc": mmlu_score(mml)}
        log(f"{name}: gsm8k(strict)={strict} mmlu={table[name]['mmlu_acc']}")

    def pct(x):
        return "—" if x is None else f"{x:.1%}"

    lines = ["# Traditional LLM benchmarks (MLX, non-thinking, chat-template applied)",
             "_GSM8K: 5-shot, 250 sampled, exact-match. MMLU: 5-shot, 20/subject sampled, mean acc._",
             f"_{PUBLISHED['note']}_", "",
             "| model | GSM8K (strict) | GSM8K (flexible) | MMLU (mean acc) |", "|---|---|---|---|"]
    for name, s in table.items():
        lines.append(f"| {name} | {pct(s['gsm8k_strict'])} | {pct(s['gsm8k_flexible'])} | {pct(s['mmlu_acc'])} |")
    if any((s.get("mmlu_acc") or 1) < 0.30 for s in table.values()):
        lines += ["", "_NOTE: MMLU returns chance-level (~25%) via this MLX loglikelihood harness — "
                  "verified consistent across chat-template / fewshot-multiturn configs, so it is a "
                  "harness/4-bit-quantization interaction, NOT the model's true MMLU. Use the published "
                  "~62% as the reference; GSM8K (generative) is the trustworthy local number._"]
    md = "\n".join(lines) + "\n"
    (REPO / "eval/results/overnight/benchmarks.md").write_text(md, encoding="utf-8")
    (REPO / "eval/results/overnight/benchmarks.json").write_text(
        json.dumps({"table": table, "published": PUBLISHED}, indent=2), encoding="utf-8")
    print(md)
    log("wrote benchmarks.md/.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
