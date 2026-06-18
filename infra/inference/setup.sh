#!/usr/bin/env bash
set -euo pipefail

MODEL_DIR="${KOLIBRI_MODEL_DIR:-/opt/kolibri-ai/models}"
MODEL_FILE="TinyLlama-1.1B-Chat-v1.0.Q4_K_M.gguf"
MODEL_URL="https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
MODEL_PATH="${MODEL_DIR}/${MODEL_FILE}"

echo "[setup] Model directory: ${MODEL_DIR}"
mkdir -p "${MODEL_DIR}"

if [ -f "${MODEL_PATH}" ]; then
    echo "[setup] Model already exists at ${MODEL_PATH}"
    ls -lh "${MODEL_PATH}"
else
    echo "[setup] Downloading ${MODEL_FILE}..."
    if command -v wget &>/dev/null; then
        wget -q --show-progress -O "${MODEL_PATH}" "${MODEL_URL}"
    elif command -v curl &>/dev/null; then
        curl -L --progress-bar -o "${MODEL_PATH}" "${MODEL_URL}"
    else
        echo "[setup] Error: neither wget nor curl found. Install one and retry."
        exit 1
    fi
    echo "[setup] Download complete."
    ls -lh "${MODEL_PATH}"
fi

echo "[setup] Installing Python dependencies..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
pip install -r "${SCRIPT_DIR}/requirements.txt"

echo ""
echo "[setup] Done. Start the service with:"
echo "  cd ${SCRIPT_DIR} && python api.py"
echo ""
echo "  Or with uvicorn:"
echo "  uvicorn api:app --host 0.0.0.0 --port 8001"
