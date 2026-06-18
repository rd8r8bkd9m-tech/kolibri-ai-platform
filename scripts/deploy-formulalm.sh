#!/bin/bash
set -euo pipefail

# Deploy FormulaLM API to Home server (10.99.0.1)
# Usage: ./deploy-formulalm.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REMOTE="ladik@kolibri-home"
REMOTE_DIR="/opt/kolibri-ai"

echo "=== Deploying FormulaLM API to Home server ==="

echo "[1/4] Copying formulalm_api.py..."
scp "$SCRIPT_DIR/formulalm_api.py" "$REMOTE:$REMOTE_DIR/formulalm_api.py"

echo "[2/4] Copying systemd service..."
scp "$PROJECT_DIR/infra/systemd/kolibri-formulalm.service" "$REMOTE:/tmp/kolibri-formulalm.service"
ssh "$REMOTE" "sudo mv /tmp/kolibri-formulalm.service /etc/systemd/system/"

echo "[3/4] Enabling and starting service..."
ssh "$REMOTE" "sudo systemctl daemon-reload && sudo systemctl enable kolibri-formulalm && sudo systemctl restart kolibri-formulalm"

echo "[4/4] Checking status..."
sleep 2
ssh "$REMOTE" "sudo systemctl status kolibri-formulalm --no-pager -l" || true

echo ""
echo "=== Done. FormulaLM API should be at http://10.99.0.1:8004 ==="
echo "Test: curl http://10.99.0.1:8004/api/v1/health"
echo ""
echo "To enable in main backend, set in .env:"
echo "  KOLIBRI_FORMULALM_ENABLED=true"
echo "  KOLIBRI_FORMULALM_URL=http://10.99.0.1:8004"
