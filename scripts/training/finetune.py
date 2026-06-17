#!/usr/bin/env python3
"""Fine-tune Qwen2.5-1.5B with LoRA using PEFT + TRL.

Requires: torch, transformers, peft, trl, datasets, accelerate
Install: pip install torch transformers peft trl datasets accelerate

CPU-only mode: works but very slow (~1-2 hours for 100 samples on 6 cores).
GPU mode: set CUDA_VISIBLE_DEVICES if available.
"""

import argparse
import json
from pathlib import Path

import torch
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer, SFTConfig


def load_chat_dataset(path):
    """Load JSONL dataset with messages field."""
    data = []
    with open(path) as f:
        for line in f:
            data.append(json.loads(line))
    return data


def format_chat(example, tokenizer):
    """Format messages into model input using chat template."""
    text = tokenizer.apply_chat_template(
        example["messages"],
        tokenize=False,
        add_generation_prompt=False,
    )
    return {"text": text}


def main():
    parser = argparse.ArgumentParser(description="Fine-tune Qwen2.5-1.5B with LoRA")
    parser.add_argument("--model", type=str, default="Qwen/Qwen2.5-1.5B", help="Base model name")
    parser.add_argument("--train-data", type=str, default="data/train_chat.jsonl", help="Training data path")
    parser.add_argument("--val-data", type=str, default="data/val_chat.jsonl", help="Validation data path")
    parser.add_argument("--output-dir", type=str, default="output/qwen-lora", help="Output directory")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=2, help="Per-device batch size")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    parser.add_argument("--lora-r", type=int, default=16, help="LoRA rank")
    parser.add_argument("--lora-alpha", type=int, default=32, help="LoRA alpha")
    parser.add_argument("--max-seq-len", type=int, default=512, help="Max sequence length")
    parser.add_argument("--cpu", action="store_true", help="Force CPU-only training")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    device = "cpu" if args.cpu or not torch.cuda.is_available() else "cuda"
    print(f"Device: {device}")

    print(f"Loading tokenizer from {args.model}...")
    tokenizer = AutoTokenizer.from_pretrained(
        args.model,
        trust_remote_code=True,
        padding_side="right",
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print(f"Loading model from {args.model}...")
    model_kwargs = {"trust_remote_code": True, "torch_dtype": torch.float32}
    if device == "cpu":
        model_kwargs["torch_dtype"] = torch.float32
    else:
        model_kwargs["device_map"] = "auto"

    model = AutoModelForCausalLM.from_pretrained(args.model, **model_kwargs)
    if device == "cpu":
        model = model.to("cpu")

    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        bias="none",
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    print(f"Loading training data from {args.train_data}...")
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

    training_args = SFTConfig(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        weight_decay=0.01,
        logging_steps=10,
        save_strategy="epoch",
        eval_strategy="epoch" if val_dataset else "no",
        max_seq_length=args.max_seq_len,
        dataset_text_field="text",
        packing=False,
        report_to="none",
        fp16=(device != "cpu"),
        bf16=False,
        dataloader_num_workers=0 if device == "cpu" else 2,
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        processing_class=tokenizer,
    )

    print("Starting training...")
    trainer.train()

    adapter_dir = output_dir / "adapter"
    adapter_dir.mkdir(exist_ok=True)
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    print(f"LoRA adapter saved to {adapter_dir}")

    metrics = trainer.evaluate()
    print(f"Evaluation metrics: {metrics}")


if __name__ == "__main__":
    main()
