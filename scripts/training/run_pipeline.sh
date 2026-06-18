#!/bin/bash
# TinyLlama-1.1B LoRA fine-tuning pipeline for Kolibri AI
# Usage: ./run_pipeline.sh [step]
# Steps: install | data | extract | prepare | train | merge | schedule | redis | all

set -euo pipefail
cd "$(dirname "$0")"

VENV_DIR="venv"
DATA_DIR="data"
OUTPUT_DIR="output"
DB_PATH="${KOLIBRI_DB:-/opt/kolibri-ai/data/kolibri.db}"
REDIS_HOST="${KOLIBRI_REDIS:-10.99.0.1}"
REDIS_PORT="${KOLIBRI_REDIS_PORT:-6379}"
MODEL="${KOLIBRI_MODEL:-TinyLlama/TinyLlama-1.1B-Chat-v1.0}"

activate_venv() {
    if [ -d "$VENV_DIR" ]; then
        source "$VENV_DIR/bin/activate"
    fi
}

install_deps() {
    echo "=== Installing dependencies ==="
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip
    pip install -r requirements.txt
    echo "Dependencies installed in $VENV_DIR"
}

step_data() {
    echo "=== Step 1: Generating synthetic training data ==="
    python3 generate_data.py -n 200 -o "$DATA_DIR/train.jsonl"
    echo "Data generated in $DATA_DIR/"
}

step_extract() {
    echo "=== Step 1b: Extracting conversations from SQLite ==="
    if [ -f "$DB_PATH" ]; then
        python3 extract_conversations.py \
            --db "$DB_PATH" \
            --output-dir "$DATA_DIR" \
            --min-turns 2 \
            --val-split 0.1
    else
        echo "Database not found at $DB_PATH, skipping extraction"
        echo "Run step_data instead for synthetic data"
    fi
}

step_prepare() {
    echo "=== Step 2: Preparing dataset ==="
    activate_venv

    # Prefer conversation data if available, fall back to synthetic
    local train_input="$DATA_DIR/train.jsonl"
    local val_input="$DATA_DIR/val.jsonl"

    if [ -f "$DATA_DIR/train_conversations.jsonl" ]; then
        echo "Using real conversation data"
        train_input="$DATA_DIR/train_conversations.jsonl"
        val_input="$DATA_DIR/val_conversations.jsonl"
    fi

    python3 prepare_dataset.py \
        --input "$train_input" \
        --output "$DATA_DIR/train_chat.jsonl" \
        --val-input "$val_input" \
        --val-output "$DATA_DIR/val_chat.jsonl"
}

step_train() {
    echo "=== Step 3: Fine-tuning TinyLlama-1.1B with LoRA ==="
    activate_venv
    python3 finetune.py \
        --model "$MODEL" \
        --train-data "$DATA_DIR/train_chat.jsonl" \
        --val-data "$DATA_DIR/val_chat.jsonl" \
        --output-dir "$OUTPUT_DIR/tinyllama-lora" \
        --merged-dir "$OUTPUT_DIR/tinyllama-merged" \
        --epochs 3 \
        --batch-size 2 \
        --lr 2e-4 \
        --lora-r 16 \
        --lora-alpha 32 \
        --max-seq-len 1024 \
        --gradient-accumulation 4 \
        --cpu
}

step_merge() {
    echo "=== Step 4: Merging LoRA adapter ==="
    activate_venv
    python3 merge_adapter.py \
        --base-model "$MODEL" \
        --adapter-path "$OUTPUT_DIR/tinyllama-lora/adapter" \
        --output-dir "$OUTPUT_DIR/tinyllama-merged"
}

step_schedule() {
    echo "=== Training Scheduler ==="
    activate_venv
    echo "Starting training scheduler (Ctrl+C to stop)..."
    echo "  Redis: $REDIS_HOST:$REDIS_PORT"
    echo "  Max CPU: 50%, Max MEM: 70%"
    python3 train_scheduler.py \
        --redis-host "$REDIS_HOST" \
        --redis-port "$REDIS_PORT" \
        --max-cpu 50 \
        --max-mem 70 \
        run
}

step_redis() {
    echo "=== Redis Configuration Check ==="
    activate_venv
    python3 redis_config.py --host "$REDIS_HOST" --port "$REDIS_PORT" check
    echo ""
    python3 redis_config.py --host "$REDIS_HOST" --port "$REDIS_PORT" setup
    echo ""
    python3 redis_config.py --host "$REDIS_HOST" --port "$REDIS_PORT" nodes
}

case "${1:-all}" in
    install) install_deps ;;
    data) step_data ;;
    extract) step_extract ;;
    prepare) step_prepare ;;
    train) step_train ;;
    merge) step_merge ;;
    schedule) step_schedule ;;
    redis) step_redis ;;
    all)
        step_data
        step_extract || true
        step_prepare
        step_train
        step_merge
        echo ""
        echo "=== Pipeline complete! ==="
        echo "  Merged model: $OUTPUT_DIR/tinyllama-merged/"
        echo "  Next: convert to GGUF and copy to 9FTS server"
        echo "  Deploy: scp $OUTPUT_DIR/tinyllama-merged/* kolibri-9fts:/opt/kolibri/models/tinyllama/"
        ;;
    *)
        echo "Usage: $0 {install|data|extract|prepare|train|merge|schedule|redis|all}"
        echo ""
        echo "Steps:"
        echo "  install  - Install Python dependencies in venv"
        echo "  data     - Generate synthetic QA training data"
        echo "  extract  - Extract conversations from Kolibri SQLite DB"
        echo "  prepare  - Convert data to chat format for training"
        echo "  train    - Fine-tune TinyLlama-1.1B with LoRA"
        echo "  merge    - Merge LoRA adapter with base model"
        echo "  schedule - Run training scheduler (monitors load, dispatches jobs)"
        echo "  redis    - Check and configure Redis for cluster state"
        echo "  all      - Run full pipeline (data -> prepare -> train -> merge)"
        exit 1
        ;;
esac
