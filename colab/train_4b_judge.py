"""Colab (A100): QLoRA-SFT Qwen3-4B on our v9 recall-first JUDGE data — the scale-thesis test.

Question: does ~2.4x scale (4B vs our tuned 1.7B, which hits 90.4% leak-recall as `v9`) beat the 1.7B
on the constrained safety behavior? Trains an identical-recipe judge on the bigger base, then we eval
it locally on OUR metrics (leak-recall/safety/5-way). Also benchmarks GSM8K+MMLU on 4B-base /
4B-tuned / 1.7B-base — clean, full-sample, no Metal OOM — to backfill the dev-log's traditional numbers.

──────────────────────────────────────────────────────────────────────────────
USAGE (Colab, set Runtime → A100):
  1. Upload data/colab_4b/train.jsonl and valid.jsonl to /content/ (Files pane).
  2. HF token: add it in Colab Secrets (🔑 icon) as HF_TOKEN, OR you'll be prompted.
  3. Edit HF_REPO below to <your-hf-username>/socratic-judge-4b.
  4. Run all (or paste this whole file into one cell and run).
  → Pushes the merged 4B model to HF_REPO. Tell me the repo name; I pull it back, convert to MLX,
    and eval on our frozen set. If any cell errors, paste the traceback to me and I'll patch this.
──────────────────────────────────────────────────────────────────────────────
"""
import os
import subprocess
import sys

# ---- config (EDIT HF_REPO) --------------------------------------------------
HF_REPO = "atakle/socratic-judge-4b"
BASE_4B = "Qwen/Qwen3-4B"
BASE_1P7B = "Qwen/Qwen3-1.7B"
TRAIN, VALID = "/content/train.jsonl", "/content/valid.jsonl"
EPOCHS, LR = 3, 1e-4  # matches our 1.7B recipe

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "transformers", "peft", "trl",
                "bitsandbytes", "accelerate", "datasets", "lm-eval"], check=True)

import torch  # noqa: E402
from huggingface_hub import login  # noqa: E402

try:
    from google.colab import userdata
    login(userdata.get("HF_TOKEN"))
except Exception:  # noqa: BLE001
    login(os.environ.get("HF_TOKEN") or input("HF token: "))

from datasets import load_dataset  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig  # noqa: E402
from peft import LoraConfig, PeftModel  # noqa: E402
from trl import SFTConfig, SFTTrainer  # noqa: E402

# ---- 1. QLoRA-SFT the 4B on our judge data ----------------------------------
tok = AutoTokenizer.from_pretrained(BASE_4B)
bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                         bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
model = AutoModelForCausalLM.from_pretrained(BASE_4B, quantization_config=bnb, device_map="auto")
ds = load_dataset("json", data_files={"train": TRAIN, "valid": VALID})
peft_cfg = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                      "gate_proj", "up_proj", "down_proj"])
sft_cfg = SFTConfig(output_dir="/content/out", num_train_epochs=EPOCHS, learning_rate=LR,
                    per_device_train_batch_size=4, gradient_accumulation_steps=4,
                    warmup_ratio=0.05, lr_scheduler_type="cosine", bf16=True, logging_steps=20,
                    save_strategy="no", max_length=1024, dataset_text_field="text", report_to="none")
# NOTE: if your trl is older, SFTConfig may want `max_seq_length=` instead of `max_length=`, and
# SFTTrainer may want `tokenizer=` instead of `processing_class=`. Swap if you hit a TypeError.
trainer = SFTTrainer(model=model, args=sft_cfg, train_dataset=ds["train"],
                     eval_dataset=ds["valid"], peft_config=peft_cfg, processing_class=tok)
trainer.train()
trainer.save_model("/content/adapter")

# ---- 2. merge adapter into a fresh bf16 base (clean full model) + push -------
del model, trainer
torch.cuda.empty_cache()
# PEFT's LoRA dispatch calls is_torchao_available(), which RAISES on an old torchao (Colab ships
# 0.10; PEFT wants >=0.16) even though we train via bitsandbytes, not torchao. Remove it before merge.
subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "torchao"], check=False)
base = AutoModelForCausalLM.from_pretrained(BASE_4B, dtype=torch.bfloat16, device_map="auto")
merged = PeftModel.from_pretrained(base, "/content/adapter").merge_and_unload()
merged.save_pretrained("/content/merged")
tok.save_pretrained("/content/merged")
merged.push_to_hub(HF_REPO)
tok.push_to_hub(HF_REPO)
print(f"\n✅ PUSHED merged 4B judge → {HF_REPO}\n")

# ---- 3. clean traditional benchmarks (A100, full sample) --------------------
def bench(model_id, tag):
    for task, extra in [("gsm8k", ["--apply_chat_template"]), ("mmlu", [])]:
        subprocess.run(["lm_eval", "--model", "hf",
                        "--model_args", f"pretrained={model_id},dtype=bfloat16",
                        "--tasks", task, "--num_fewshot", "5", "--batch_size", "auto",
                        "--limit", "250" if task == "gsm8k" else "20",
                        "--output_path", f"/content/bench/{tag}_{task}"] + extra, check=False)

bench(BASE_4B, "4b_base")
bench(HF_REPO, "4b_tuned")     # tuned judge on GSM8K = the 4B forgetting check
bench(BASE_1P7B, "1p7b_base")  # clean full-sample 1.7B base (fixes our local n=30 / MMLU issues)
print("\n✅ DONE. Benchmarks in /content/bench/*. Merged judge pushed to", HF_REPO)
print("   Tell me the repo name — I'll pull it, convert to MLX, and eval on our frozen set.")
