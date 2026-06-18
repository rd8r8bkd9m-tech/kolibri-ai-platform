#!/usr/bin/env python3
"""Fine-tune TinyLlama-1.1B with LoRA using PEFT + TRL.

Supports both the base HuggingFace model and direct GGUF input via llama.cpp.
After training, exports the merged model to GGUF format (Q4_K_M) for inference.

Requires: torch, transformers, peft, trl, datasets, accelerate
Install: pip install -r requirements.txt

CPU-only mode: works but slow (~1-2 hours for 100 samples on 6 cores).
GPU mode: set CUDA_VISIBLE_DEVICES if available.

Usage:
  python3 finetune.py --model TinyLlama/TinyLlama-1.1B-Chat-v1.0
  python3 finetune.py --model TinyLlama/TinyLlama-1.1B-Chat-v1.0 --epochs 5 --lora-r 32
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import torch
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer, SFTConfig

# Default model for Kolibri
DEFAULT_MODEL = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
DEFAULT_OUTPUT_DIR = "output/tinyllama-lora"
DEFAULT_MERGED_DIR = "output/tinyllama-merged"
DEFAULT_GGUF_DIR = "output/tinyllama-gguf"


def load_chat_dataset(path: str) -> list:
    """Load JSONL dataset with messages field."""
    data = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def format_chat(example: dict, tokenizer) -> dict:
    """Format messages into model input using TinyLlama chat template."""
    text = tokenizer.apply_chat_template(
        example["messages"],
        tokenize=False,
        add_generation_prompt=False,
    )
    return {"text": text}


def get_device_config(cpu: bool = False) -> tuple:
    """Determine device and dtype based on available hardware."""
    if cpu or not torch.cuda.is_available():
        return "cpu", torch.float32
    gpu_mem = torch.cuda.get_device_properties(0).total_mem / 1e9
    if gpu_mem < 6:
        return "cuda", torch.float16
    return "cuda", torch.float16


def get_lora_target_modules(model_name: str) -> list:
    """Get appropriate LoRA target modules for the model architecture."""
    name_lower = model_name.lower()
    if "tinyllama" in name_lower or "llama" in name_lower:
        return ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    elif "qwen" in name_lower:
        return ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    else:
        return ["q_proj", "k_proj", "v_proj", "o_proj"]


def main():
    parser = argparse.ArgumentParser(description="Fine-tune TinyLlama-1.1B with LoRA")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        help="Base model name or path")
    parser.add_argument("--train-data", type=str, default="data/train_chat.jsonl",
                        help="Training data path (JSONL with messages field)")
    parser.add_argument("--val-data", type=str, default="data/val_chat.jsonl",
                        help="Validation data path")
    parser.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR,
                        help="Output directory for LoRA adapter")
    parser.add_argument("--merged-dir", type=str, default=DEFAULT_MERGED_DIR,
                        help="Output directory for merged model")
    parser.add_argument("--gguf-dir", type=str, default=DEFAULT_GGUF_DIR,
                        help="Output directory for GGUF export")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=2, help="Per-device batch size")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    parser.add_argument("--lora-r", type=int, default=16, help="LoRA rank")
    parser.add_argument("--lora-alpha", type=int, default=32, help="LoRA alpha")
    parser.add_argument("--lora-dropout", type=float, default=0.05, help="LoRA dropout")
    parser.add_argument("--max-seq-len", type=int, default=1024,
                        help="Max sequence length (TinyLlama supports up to 2048)")
    parser.add_argument("--cpu", action="store_true", help="Force CPU-only training")
    parser.add_argument("--gradient-accumulation", type=int, default=4,
                        help="Gradient accumulation steps")
    parser.add_argument("--warmup-ratio", type=float, default=0.1, help="Warmup ratio")
    parser.add_argument("--export-gguf", action="store_true", help="Export to GGUF after training")
    parser.add_argument("--gguf-quantization", type=str, default="Q4_K_M",
                        help="GGUF quantization type")
    parser.add_argument("--llama-cpp-path", type=str, default=None,
                        help="Path to llama.cpp directory (for GGUF conversion)")
    parser.add_argument("--redis-host", type=str, default=None,
                        help="Redis host for progress reporting")
    parser.add_argument("--redis-port", type=int, default=6379, help="Redis port")
    parser.add_argument("--job-id", type=str, default=None,
                        help="Job ID for Redis progress tracking")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    device, dtype = get_device_config(args.cpu)
    print(f"Device: {device}, dtype: {dtype}")

    # Redis progress reporting
    redis_client = None
    if args.redis_host:
        try:
            import redis as redis_lib
            redis_client = redis_lib.Redis(
                host=args.redis_host, port=args.redis_port, decode_responses=True
            )
            redis_client.ping()
            print(f"Connected to Redis at {args.redis_host}:{args.redis_port}")
        except Exception as e:
            print(f"Warning: Redis connection failed: {e}")
            redis_client = None

    def report_progress(status: str, progress: float = 0, detail: str = ""):
        """Report training progress to Redis if available."""
        if redis_client and args.job_id:
            try:
                redis_client.hset(
                    f"kolibri:training:{args.job_id}",
                    mapping={
                        "status": status,
                        "progress": str(progress),
                        "detail": detail,
                        "updated_at": str(time.time()),
                    },
                )
            except Exception:
                pass

    report_progress("loading_model")

    print(f"Loading tokenizer from {args.model}...")
    tokenizer = AutoTokenizer.from_pretrained(
        args.model,
        trust_remote_code=True,
        padding_side="right",
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print(f"Loading model from {args.model}...")
    model_kwargs = {
        "trust_remote_code": True,
        "torch_dtype": dtype,
    }
    if device == "cuda":
        model_kwargs["device_map"] = "auto"

    model = AutoModelForCausalLM.from_pretrained(args.model, **model_kwargs)
    if device == "cpu":
        model = model.to("cpu")

    # Enable gradient checkpointing for memory efficiency
    model.gradient_checkpointing_enable()
    model.config.use_cache = False

    target_modules = get_lora_target_modules(args.model)
    print(f"LoRA target modules: {target_modules}")

    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=target_modules,
        bias="none",
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    report_progress("loading_data")

    print(f"Loading training data from {args.train_data}...")
    if not Path(args.train_data).exists():
        print(f"Error: Training data not found at {args.train_data}")
        print("Run extract_conversations.py or generate_data.py first.")
        return 1

    train_dataset = load_dataset("json", data_files=args.train_data, split="train")

    val_dataset = None
    if Path(args.val_data).exists():
        val_dataset = load_dataset("json", data_files=args.val_data, split="train")

    train_dataset = train_dataset.map(
        lambda x: format_chat(x, tokenizer),
        remove_columns=train_dataset.column_names,
    )
    if val_dataset is not None:
        val_dataset = val_dataset.map(
            lambda x: format_chat(x, tokenizer),
            remove_columns=val_dataset.column_names,
        )

    report_progress("training")

    training_args = SFTConfig(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=args.warmup_ratio,
        weight_decay=0.01,
        logging_steps=10,
        save_strategy="epoch",
        eval_strategy="epoch" if val_dataset else "no",
        max_seq_length=args.max_seq_len,
        dataset_text_field="text",
        packing=False,
        report_to="none",
        fp16=(device == "cuda"),
        bf16=False,
        dataloader_num_workers=0 if device == "cpu" else 2,
        remove_unused_columns=False,
        seed=42,
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        processing_class=tokenizer,
    )

    print("Starting training...")
    start_time = time.time()
    trainer.train()
    elapsed = time.time() - start_time
    print(f"Training completed in {elapsed:.0f}s")

    # Save adapter
    adapter_dir = output_dir / "adapter"
    adapter_dir.mkdir(exist_ok=True)
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    print(f"LoRA adapter saved to {adapter_dir}")

    # Evaluate
    if val_dataset:
        metrics = trainer.evaluate()
        print(f"Evaluation metrics: {metrics}")

    report_progress("merging")

    # Merge adapter with base model
    merged_dir = Path(args.merged_dir)
    merged_dir.mkdir(parents=True, exist_ok=True)

    print("Merging adapter with base model...")
    from peft import PeftModel

    base_model = AutoModelForCausalLM.from_pretrained(
        args.model,
        trust_remote_code=True,
        torch_dtype=torch.float16,
        device_map="cpu",
    )
    merged_model = PeftModel.from_pretrained(base_model, str(adapter_dir))
    merged_model = merged_model.merge_and_unload()

    merged_model.save_pretrained(str(merged_dir))
    tokenizer.save_pretrained(str(merged_dir))
    print(f"Merged model saved to {merged_dir}")

    # GGUF export
    if args.export_gguf:
        report_progress("exporting_gguf")
        gguf_dir = Path(args.gguf_dir)
        gguf_dir.mkdir(parents=True, exist_ok=True)

        llama_cpp = args.llama_cpp_path
        if not llama_cpp:
            # Try common locations
            candidates = [
                Path.home() / "llama.cpp",
                Path("/opt/llama.cpp"),
                Path("/usr/local/bin"),
            ]
            for c in candidates:
                if (c / "convert_hf_to_gguf.py").exists():
                    llama_cpp = str(c)
                    break

        if llama_cpp:
            print(f"Converting to GGUF using llama.cpp at {llama_cpp}...")
            import subprocess

            convert_script = Path(llama_cpp) / "convert_hf_to_gguf.py"
            if convert_script.exists():
                gguf_path = gguf_dir / "model-f16.gguf"
                subprocess.run(
                    [sys.executable, str(convert_script), str(merged_dir),
                     "--outfile", str(gguf_path), "--outtype", "f16"],
                    check=True,
                )
                print(f"F16 GGUF saved to {gguf_path}")

                # Quantize
                quantize_bin = Path(llama_cpp) / "llama-quantize"
                if not quantize_bin.exists():
                    quantize_bin = Path(llama_cpp) / "quantize"
                if quantize_bin.exists():
                    quant_path = gguf_dir / f"model-{args.gguf_quantization}.gguf"
                    subprocess.run(
                        [str(quantize_bin), str(gguf_path), str(quant_path),
                         args.gguf_quantization],
                        check=True,
                    )
                    print(f"Quantized GGUF saved to {quant_path}")
                else:
                    print("Warning: llama-quantize not found, skipping quantization")
            else:
                print(f"Warning: convert_hf_to_gguf.py not found at {convert_script}")
        else:
            print("Warning: llama.cpp not found. Set --llama-cpp-path to enable GGUF export")

    report_progress("completed", 1.0)
    print("\n=== Training pipeline complete! ===")
    print(f"  Adapter:   {adapter_dir}")
    print(f"  Merged:    {merged_dir}")
    if args.export_gguf:
        print(f"  GGUF:      {gguf_dir}")
    print(f"  Time:      {elapsed:.0f}s")
    return 0


if __name__ == "__main__":
    exit(main())
