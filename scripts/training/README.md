# Kolibri Training — TinyLlama-1.1B LoRA Pipeline

Fine-tuning pipeline for TinyLlama-1.1B-Chat with LoRA on conversation data.
Supports both synthetic QA data and real conversations extracted from SQLite.

## Quick Start

```bash
# Install dependencies
./run_pipeline.sh install

# Run full pipeline (synthetic data + train + merge)
./run_pipeline.sh all

# Or step by step:
./run_pipeline.sh data      # Generate synthetic data
./run_pipeline.sh extract   # Extract from Kolibri DB
./run_pipeline.sh prepare   # Convert to chat format
./run_pipeline.sh train     # Fine-tune with LoRA
./run_pipeline.sh merge     # Merge adapter with base model
```

## Pipeline Steps

| Step | Script | Description |
|------|--------|-------------|
| 1a | `generate_data.py` | Generate synthetic QA dataset (JSONL) |
| 1b | `extract_conversations.py` | Extract training data from Kolibri SQLite |
| 2 | `prepare_dataset.py` | Convert to chat format for training |
| 3 | `finetune.py` | LoRA fine-tuning with PEFT/TRL |
| 4 | `merge_adapter.py` | Merge adapter with base model |

## Additional Tools

| Script | Description |
|--------|-------------|
| `train_scheduler.py` | Load-aware training scheduler (monitors CPU/MEM, dispatches jobs via Redis) |
| `redis_config.py` | Redis setup and cluster health check |

## Scheduler Usage

```bash
# Run the scheduler (monitors load, auto-trains during low-load periods)
./run_pipeline.sh schedule

# Submit a job manually
python3 train_scheduler.py submit --epochs 5 --lora-r 32

# Check job status
python3 train_scheduler.py status --job-id job_1234567890

# List all jobs
python3 train_scheduler.py list

# Check current system load
python3 train_scheduler.py load
```

## Redis Configuration

```bash
# Check Redis connectivity and config
./run_pipeline.sh redis

# Or directly:
python3 redis_config.py check
python3 redis_config.py setup
python3 redis_config.py nodes
```

## Files

- `generate_data.py` — Synthetic QA data generator (Python, Linux, networking, AI/ML, DevOps topics)
- `extract_conversations.py` — Extract training pairs from Kolibri SQLite conversations
- `prepare_dataset.py` — Converts JSONL to chat format
- `finetune.py` — LoRA fine-tuning with PEFT/TRL (TinyLlama-1.1B optimized)
- `merge_adapter.py` — Merge LoRA adapter into base model, optional GGUF export
- `train_scheduler.py` — Load-aware training scheduler with Redis job queue
- `redis_config.py` — Redis configuration checker and setup tool
- `run_pipeline.sh` — Pipeline runner script
- `requirements.txt` — Python dependencies

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `KOLIBRI_DB` | `/opt/kolibri-ai/data/kolibri.db` | Path to Kolibri SQLite database |
| `KOLIBRI_REDIS` | `10.99.0.1` | Redis host for cluster state |
| `KOLIBRI_REDIS_PORT` | `6379` | Redis port |
| `KOLIBRI_MODEL` | `TinyLlama/TinyLlama-1.1B-Chat-v1.0` | Base model to fine-tune |

## Output

- `data/train.jsonl`, `data/val.jsonl` — Synthetic training/validation data
- `data/train_full.jsonl` — Full synthetic dataset (all topics combined)
- `data/train_conversations.jsonl` — Real conversation data from SQLite
- `data/train_chat.jsonl`, `data/val_chat.jsonl` — Chat-formatted data
- `data/train_full_chat.jsonl` — Full dataset in chat format
- `output/tinyllama-lora/adapter/` — LoRA adapter weights
- `output/tinyllama-merged/` — Merged standalone model
- `output/tinyllama-gguf/` — GGUF export (if --export-gguf used)

## Deployment

After training, copy the merged model to the 9FTS inference server:

```bash
scp -P 2222 output/tinyllama-merged/* ladik@kolibri-9fts:/opt/kolibri/models/tinyllama/
```

## Notes

- CPU-only training works but is slow (~1-2h for 100 samples on 6 cores)
- The scheduler prevents concurrent training jobs across cluster nodes via Redis locks
- Gradient checkpointing is enabled by default for memory efficiency
- TinyLlama-1.1B supports up to 2048 tokens context (default max_seq_len=1024)
