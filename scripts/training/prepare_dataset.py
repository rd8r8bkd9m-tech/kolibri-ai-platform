#!/usr/bin/env python3
"""Prepare JSONL dataset for LoRA fine-tuning with Qwen2.5.

Converts the generate_data.py output into the chat format expected by
the fine-tuning script. Requires: transformers, datasets.
"""

import json
import argparse
from pathlib import Path


def convert_to_chat_format(input_path, output_path):
    """Convert JSONL with system/user/assistant fields to chat format."""
    samples = []
    with open(input_path) as f:
        for line in f:
            item = json.loads(line)
            messages = []
            if item.get("system"):
                messages.append({"role": "system", "content": item["system"]})
            messages.append({"role": "user", "content": item["user"]})
            messages.append({"role": "assistant", "content": item["assistant"]})
            samples.append({"messages": messages})

    with open(output_path, "w") as f:
        for item in samples:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return len(samples)


def main():
    parser = argparse.ArgumentParser(description="Prepare dataset for LoRA fine-tuning")
    parser.add_argument("--input", type=str, default="data/train.jsonl", help="Input JSONL path")
    parser.add_argument("--output", type=str, default="data/train_chat.jsonl", help="Output JSONL path")
    parser.add_argument("--val-input", type=str, default="data/val.jsonl", help="Validation input path")
    parser.add_argument("--val-output", type=str, default="data/val_chat.jsonl", help="Validation output path")
    args = parser.parse_args()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    n_train = convert_to_chat_format(args.input, args.output)
    print(f"Converted {n_train} training samples -> {args.output}")

    if Path(args.val_input).exists():
        n_val = convert_to_chat_format(args.val_input, args.val_output)
        print(f"Converted {n_val} validation samples -> {args.val_output}")


if __name__ == "__main__":
    main()
