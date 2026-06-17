# Kolibri Training — Qwen2.5-1.5B LoRA Pipeline

Distillation pipeline for fine-tuning Qwen2.5-1.5B with LoRA on synthetic QA data.

## Quick Start

```bash
# Generate training data (no dependencies needed)
python3 generate_data.py -n 200

# Or run full pipeline (installs deps first)
./run_pipeline.sh install
./run_pipeline.sh all
```

## Pipeline Steps

| Step | Script | Dependencies | Description |
|------|--------|-------------|-------------|
| 1 | `generate_data.py` | stdlib only | Generate synthetic QA dataset (JSONL) |
| 2 | `prepare_dataset.py` | stdlib only | Convert to chat format for training |
| 3 | `finetune.py` | torch, transformers, peft, trl | LoRA fine-tuning |
| 4 | `merge_adapter.py` | torch, transformers, peft | Merge adapter with base model |

## Files

- `generate_data.py` — Synthetic QA data generator (Python, Linux, networking, math, science topics)
- `prepare_dataset.py` — Converts JSONL to chat format
- `finetune.py` — LoRA fine-tuning with PEFT/TRL
- `merge_adapter.py` — Merge LoRA adapter into base model
- `run_pipeline.sh` — Pipeline runner script

## Output

- `data/train.jsonl`, `data/val.jsonl` — Raw training/validation data
- `data/train_chat.jsonl`, `data/val_chat.jsonl` — Chat-formatted data
- `output/qwen-lora/adapter/` — LoRA adapter weights
- `output/qwen-merged/` — Merged standalone model

## Notes

- CPU-only training is supported but slow (~1-2h for 100 samples on 6 cores)
- Outbound port 443 is blocked on this server — pip install needs a proxy or local mirror
- Model download from HuggingFace requires network access
- For GGUF conversion: use llama.cpp's `convert_hf_to_gguf.py`
