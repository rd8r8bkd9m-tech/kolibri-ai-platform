#!/usr/bin/env python3
"""Merge LoRA adapter with base Qwen2.5-1.5B model.

Creates a standalone model that can be converted to GGUF for Ollama.
Requires: torch, transformers, peft
"""

import argparse
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel


def main():
    parser = argparse.ArgumentParser(description="Merge LoRA adapter with base model")
    parser.add_argument("--base-model", type=str, default="Qwen/Qwen2.5-1.5B", help="Base model name")
    parser.add_argument("--adapter-path", type=str, default="output/qwen-lora/adapter", help="LoRA adapter path")
    parser.add_argument("--output-dir", type=str, default="output/qwen-merged", help="Merged model output path")
    parser.push_to_hub = False
    parser.add_argument("--push-to-hub", action="store_true", help="Push to HuggingFace Hub")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading base model: {args.base_model}")
    base_model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        trust_remote_code=True,
        torch_dtype=torch.float16,
        device_map="cpu",
    )

    tokenizer = AutoTokenizer.from_pretrained(
        args.adapter_path,
        trust_remote_code=True,
    )

    print(f"Loading LoRA adapter from: {args.adapter_path}")
    model = PeftModel.from_pretrained(base_model, args.adapter_path)

    print("Merging adapter weights into base model...")
    model = model.merge_and_unload()

    print(f"Saving merged model to: {output_dir}")
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    print(f"Merged model saved. Size: {sum(f.stat().st_size for f in output_dir.rglob('*') if f.is_file()) / 1e9:.2f} GB")
    print("To convert to GGUF: python convert_hf_to_gguf.py " + str(output_dir))
    print("To quantize: ./llama-quantize " + str(output_dir / "ggml-model-f16.gguf") + " Q4_K_M")


if __name__ == "__main__":
    main()
