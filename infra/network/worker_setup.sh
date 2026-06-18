#!/bin/bash
# Kolibri Worker — Setup Script
# Configures a worker node for the Kolibri Organism cluster
# Usage: sudo ./worker_setup.sh

set -euo pipefail

NODE_NAME="${KOLIBRI_NODE:-kolibri}"
NODE_ROLE="${KOLIBRI_ROLE:-worker}"
NODE_PORT="${KOLIBRI_PORT:-9001}"
GATEWAY_IP="${KOLIBRI_GATEWAY:-10.99.0.2}"
REDIS_HOST="${KOLIBRI_REDIS:-10.99.0.1}"

WORK_DIR="/opt/kolibri-ai"
LOG_DIR="/var/log/kolibri"
SERVICE_NAME="kolibri-worker"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date -Iseconds)]${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date -Iseconds)]${NC} $*"; }
err() { echo -e "${RED}[$(date -Iseconds)]${NC} $*" >&2; }

if [ "$(id -u)" -ne 0 ]; then
    err "This script must be run as root"
    exit 1
fi

log "=== Kolibri Worker Setup ==="
log "Node: ${NODE_NAME} (${NODE_ROLE})"
log "Gateway: ${GATEWAY_IP}"
log "Redis: ${REDIS_HOST}"

# ── System packages ──────────────────────────────────────────────────
log "Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv wireguard curl jq >/dev/null 2>&1

# ── Python dependencies ──────────────────────────────────────────────
log "Setting up Python environment..."
mkdir -p "${WORK_DIR}/network"
python3 -m venv "${WORK_DIR}/venv"
source "${WORK_DIR}/venv/bin/activate"
pip install --quiet fastapi uvicorn psutil httpx
deactivate

# ── Deploy worker service ────────────────────────────────────────────
log "Deploying worker service..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -f "${SCRIPT_DIR}/worker_service.py" ]; then
    cp "${SCRIPT_DIR}/worker_service.py" "${WORK_DIR}/network/worker_service.py"
else
    warn "worker_service.py not found in script dir, checking WORK_DIR..."
    if [ ! -f "${WORK_DIR}/network/worker_service.py" ]; then
        err "worker_service.py not found. Deploy it manually to ${WORK_DIR}/network/"
        exit 1
    fi
fi

# ── Log directory ────────────────────────────────────────────────────
mkdir -p "${LOG_DIR}"
chmod 755 "${LOG_DIR}"

# ── Systemd service ─────────────────────────────────────────────────
log "Creating systemd service..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=Kolibri Worker Service (${NODE_NAME})
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=${WORK_DIR}/network
Environment=KOLIBRI_NODE=${NODE_NAME}
Environment=KOLIBRI_ROLE=${NODE_ROLE}
Environment=KOLIBRI_PORT=${NODE_PORT}
Environment=KOLIBRI_GATEWAY=${GATEWAY_IP}
Environment=KOLIBRI_REDIS=${REDIS_HOST}
ExecStart=${WORK_DIR}/venv/bin/python -m uvicorn worker_service:app --host 0.0.0.0 --port ${NODE_PORT}
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl start "${SERVICE_NAME}"

# ── Log rotation ─────────────────────────────────────────────────────
log "Configuring log rotation..."
cat > "/etc/logrotate.d/${SERVICE_NAME}" << EOF
/var/log/kolibri/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 root root
}
EOF

# ── WireGuard VPN ────────────────────────────────────────────────────
log "Configuring WireGuard VPN..."
if [ ! -f /etc/wireguard/kolibri.conf ]; then
    warn "No WireGuard config found. Generate keys and create /etc/wireguard/kolibri.conf"
    warn "Example:"
    warn "  wg genkey | tee /etc/wireguard/private.key | wg pubkey > /etc/wireguard/public.key"
    warn "  Create config with peer pointing to gateway at ${GATEWAY_IP}:51830"
else
    systemctl enable wg-quick@kolibri
    systemctl start wg-quick@kolibri 2>/dev/null || warn "WireGuard already running or config needs peer setup"
fi

# ── Cron for backups ─────────────────────────────────────────────────
log "Setting up daily backup cron..."
if [ -f "${WORK_DIR}/scripts/backup.sh" ]; then
    chmod +x "${WORK_DIR}/scripts/backup.sh"
    (crontab -l 2>/dev/null; echo "0 3 * * * ${WORK_DIR}/scripts/backup.sh daily >> /var/log/kolibri/backup.log 2>&1") | sort -u | crontab -
fi

# ── Verify ───────────────────────────────────────────────────────────
log "=== Setup Complete ==="
log "Service: systemctl status ${SERVICE_NAME}"
log "Logs:    journalctl -u ${SERVICE_NAME} -f"
log "Health:  curl http://localhost:${NODE_PORT}/worker/health"
log "Metrics: curl http://localhost:${NODE_PORT}/worker/metrics"

if systemctl is-active --quiet "${SERVICE_NAME}"; then
    log "Worker service is running on port ${NODE_PORT}"
else
    err "Worker service failed to start. Check: journalctl -u ${SERVICE_NAME} -n 20"
fi
