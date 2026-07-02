#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DEPLOY_HOST="${1:-plastilin}"
DEPLOY_USER="${2:-ladik}"
DEPLOY_PORT="${3:-2222}"
REMOTE_DIR="/opt/kolibri-control-center"
SYSTEMD_DIR="/etc/systemd/system"

echo "=== Deploying Home NOC Control Center to ${DEPLOY_USER}@${DEPLOY_HOST} ==="

echo "[1/5] Creating remote directory..."
ssh -o ConnectTimeout=10 -p "$DEPLOY_PORT" "${DEPLOY_USER}@${DEPLOY_HOST}" \
  "sudo mkdir -p ${REMOTE_DIR} && sudo chown ${DEPLOY_USER}:${DEPLOY_USER} ${REMOTE_DIR}"

echo "[2/5] Uploading NOC server and wallboard..."
scp -o ConnectTimeout=10 -P "$DEPLOY_PORT" \
  "${REPO_ROOT}/ops/noc_control_center_server.py" \
  "${DEPLOY_USER}@${DEPLOY_HOST}:${REMOTE_DIR}/server.py"

scp -o ConnectTimeout=10 -P "$DEPLOY_PORT" \
  "${REPO_ROOT}/ops/noc_wallboard.html" \
  "${DEPLOY_USER}@${DEPLOY_HOST}:${REMOTE_DIR}/noc_wallboard.html"

echo "[3/5] Uploading systemd units..."
scp -o ConnectTimeout=10 -P "$DEPLOY_PORT" \
  "${REPO_ROOT}/ops/systemd/kolibri-control-center.service" \
  "${DEPLOY_USER}@${DEPLOY_HOST}:${SYSTEMD_DIR}/kolibri-control-center.service"

echo "[4/5] Uploading kiosk drop-in..."
ssh -o ConnectTimeout=10 -p "$DEPLOY_PORT" "${DEPLOY_USER}@${DEPLOY_HOST}" \
  "sudo mkdir -p ${SYSTEMD_DIR}/kolibri-home-kiosk.service.d"
scp -o ConnectTimeout=10 -P "$DEPLOY_PORT" \
  "${REPO_ROOT}/ops/systemd/kolibri-home-kiosk.service.d/90-control-center-noc-url.conf" \
  "${DEPLOY_USER}@${DEPLOY_HOST}:${SYSTEMD_DIR}/kolibri-home-kiosk.service.d/90-control-center-noc-url.conf"

echo "[5/5] Restarting services..."
ssh -o ConnectTimeout=10 -p "$DEPLOY_PORT" "${DEPLOY_USER}@${DEPLOY_HOST}" \
  "sudo systemctl daemon-reload && sudo systemctl enable --now kolibri-control-center && sudo systemctl restart kolibri-home-kiosk || true"

echo "=== Home NOC deployed ✓ ==="
echo "Verify: ssh -p ${DEPLOY_PORT} ${DEPLOY_USER}@${DEPLOY_HOST} 'systemctl status kolibri-control-center'"
echo "Access: http://127.0.0.1:9191 (on plastilin)"
