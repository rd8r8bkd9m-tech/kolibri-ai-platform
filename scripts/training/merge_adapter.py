#!/usr/bin/env python3
"""Merge LoRA adapter with TinyLlama-1.1B base model.

Creates a standalone model that can be converted to GGUF for Ollama.
Requires: torch, transformers, peft

Usage:
  python3 merge_adapter.py
  python3 merge_adapter.py --adapter-path output/tinyllama-lora/adapter --output-dir output/tinyllama-merged
"""

import argparse
import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel


DEFAULT_BASE = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
DEFAULT_ADAPTER = "output/tinyllama-lora/adapter"
DEFAULT_OUTPUT = "output/tinyllama-merged"


def main():
    parser = argparse.ArgumentParser(description="Merge LoRA adapter with base model")
    parser.add_argument("--base-model", type=str, default=DEFAULT_BASE,
                        help="Base model name or path")
    parser.add_argument("--adapter-path", type=str, default=DEFAULT_ADAPTER,
                        help="LoRA adapter path")
    parser.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT,
                        help="Merged model output path")
    parser.add_argument("--export-gguf", action="store_true",
                        help="Also export to GGUF format")
    parser.add_argument("--gguf-quantization", type=str, default="Q4_K_M",
                        help="GGUF quantization type")
    parser.add_argument("--llama-cpp-path", type=str, default=None,
                        help="Path to llama.cpp directory")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    adapter_path = Path(args.adapter_path)
    if not adapter_path.exists():
        print(f"Error: Adapter not found at {adapter_path}")
        print("Run finetune.py first to create the adapter.")
        return 1

    print(f"Loading base model: {args.base_model}")
    base_model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        trust_remote_code=True,
        torch_dtype=torch.float16,
        device_map="cpu",
    )

    tokenizer = AutoTokenizer.from_pretrained(
        str(adapter_path),
        trust_remote_code=True,
    )

    print(f"Loading LoRA adapter from: {adapter_path}")
    model = PeftModel.from_pretrained(base_model, str(adapter_path))

    print("Merging adapter weights into base model...")
    model = model.merge_and_unload()

    print(f"Saving merged model to: {output_dir}")
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    size_bytes = sum(f.stat().st_size for f in output_dir.rglob("*") if f.is_file())
    print(f"Merged model saved. Size: {size_bytes / 1e9:.2f} GB")

    if args.export_gguf:
        import subprocess

        llama_cpp = args.llama_cpp_path
        if not llama_cpp:
            candidates = [
                Path.home() / "llama.cpp",
                Path("/opt/llama.cpp"),
                Path("/usr/local/bin"),
            ]
            for c in candidates:
                if (c / "convert_hf_to_gguf.py").exists():
                    llama_cpp = str(c)
                    break

        if not llama_cpp:
            print("Warning: llama.cpp not found. Set --llama-cpp-path")
            return 0

        gguf_dir = Path(args.output_dir).parent / "tinyllama-gguf"
        gguf_dir.mkdir(parents=True, exist_ok=True)

        convert_script = Path(llama_cpp) / "convert_hf_to_gguf.py"
        if convert_script.exists():
            gguf_path = gguf_dir / "model-f16.gguf"
            print(f"Converting to GGUF: {gguf_path}")
            subprocess.run(
                [sys.executable, str(convert_script), str(output_dir),
                 "--outfile", str(gguf_path), "--outtype", "f16"],
                check=True,
            )
            print(f"F16 GGUF saved to {gguf_path}")

            quantize_bin = Path(llama_cpp) / "llama-quantize"
            if not quantize_bin.exists():
                quantize_bin = Path(llama_cpp) / "quantize"
            if quantize_bin.exists():
                quant_path = gguf_dir / f"model-{args.gguf_quantization}.gguf"
                print(f"Quantizing to {args.gguf_quantization}...")
                subprocess.run(
                    [str(quantize_bin), str(gguf_path), str(quant_path),
                     args.gguf_quantization],
                    check=True,
                )
                print(f"Quantized GGUF: {quant_path}")
            else:
                print("Warning: llama-quantize not found, skipping quantization")
        else:
            print(f"Warning: convert_hf_to_gguf.py not found at {convert_script}")

    print("\nDone! To deploy to 9FTS inference server:")
    print(f"  scp {output_dir}/* kolibri-9fts:/opt/kolibri/models/tinyllama/")
    return 0


if __name__ == "__main__":
    exit(main() or 0)
