#!/bin/bash
# Qwen2.5-1.5B LoRA distillation pipeline runner
# Usage: ./run_pipeline.sh [step]
# Steps: data | prepare | train | merge | all

set -euo pipefail
cd "$(dirname "$0")"

VENV_DIR="venv"
DATA_DIR="data"
OUTPUT_DIR="output"

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
    pip install torch transformers peft trl datasets accelerate
    echo "Dependencies installed in $VENV_DIR"
}

step_data() {
    echo "=== Step 1: Generating training data ==="
    python3 generate_data.py -n 100 -o "$DATA_DIR/train.jsonl"
    echo "Data generated in $DATA_DIR/"
}

step_prepare() {
    echo "=== Step 2: Preparing dataset ==="
    activate_venv
    python3 prepare_dataset.py \
        --input "$DATA_DIR/train.jsonl" \
        --output "$DATA_DIR/train_chat.jsonl" \
        --val-input "$DATA_DIR/val.jsonl" \
        --val-output "$DATA_DIR/val_chat.jsonl"
}

step_train() {
    echo "=== Step 3: Fine-tuning with LoRA ==="
    activate_venv
    python3 finetune.py \
        --train-data "$DATA_DIR/train_chat.jsonl" \
        --val-data "$DATA_DIR/val_chat.jsonl" \
        --output-dir "$OUTPUT_DIR/qwen-lora" \
        --epochs 3 \
        --batch-size 2 \
        --lr 2e-4 \
        --lora-r 16 \
        --lora-alpha 32 \
        --cpu
}

step_merge() {
    echo "=== Step 4: Merging LoRA adapter ==="
    activate_venv
    python3 merge_adapter.py \
        --adapter-path "$OUTPUT_DIR/qwen-lora/adapter" \
        --output-dir "$OUTPUT_DIR/qwen-merged"
}

case "${1:-all}" in
    install) install_deps ;;
    data) step_data ;;
    prepare) step_prepare ;;
    train) step_train ;;
    merge) step_merge ;;
    all)
        step_data
        step_prepare
        step_train
        step_merge
        echo "=== Pipeline complete! ==="
        echo "Merged model in $OUTPUT_DIR/qwen-merged/"
        ;;
    *)
        echo "Usage: $0 {install|data|prepare|train|merge|all}"
        exit 1
        ;;
esac
