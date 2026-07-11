#!/usr/bin/env bash
set -euo pipefail
NODE_ID=""; CONTROL_URL=""; JOIN_TOKEN=""; SIGNING_SECRET=""; MODE="CONTROLLED_WRITE"; WORKERS="1"; CAPABILITIES="health.probe,estimate.artifacts,factory.local"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --node-id) NODE_ID="$2"; shift 2;;
    --control-url) CONTROL_URL="$2"; shift 2;;
    --join-token) JOIN_TOKEN="$2"; shift 2;;
    --signing-secret) SIGNING_SECRET="$2"; shift 2;;
    --mode) MODE="$2"; shift 2;;
    --workers) WORKERS="$2"; shift 2;;
    --capabilities) CAPABILITIES="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 1;;
  esac
done
if [[ -z "$NODE_ID" || -z "$CONTROL_URL" || -z "$JOIN_TOKEN" ]]; then
  echo "usage: install-node.sh --node-id ID --control-url URL --join-token TOKEN [--signing-secret SECRET] [--workers N] [--capabilities a,b,c]"; exit 1
fi
install -d -m 755 /opt/vista-node /var/lib/vista-node
cat >/opt/vista-node/node.env <<EOF
NODE_ID=$NODE_ID
CONTROL_URL=$CONTROL_URL
VISTA_NODE_JOIN_TOKEN=$JOIN_TOKEN
VISTA_NODE_SIGNING_SECRET=$SIGNING_SECRET
MODE=$MODE
WORKERS_TOTAL=$WORKERS
POLL_SECONDS=5
LEASE_SECONDS=120
VISTA_NODE_WORKDIR=/var/lib/vista-node/work
EOF
cap_args=()
IFS=',' read -ra caps <<< "$CAPABILITIES"
for cap in "${caps[@]}"; do
  [[ -n "$cap" ]] && cap_args+=("--capability" "$cap")
done
printf '%q ' "${cap_args[@]}" >/opt/vista-node/capability.args
cat >/etc/systemd/system/vista-node-agent.service <<'EOF'
[Unit]
Description=Vista OS Node Agent
After=network-online.target
Wants=network-online.target

[Service]
EnvironmentFile=/opt/vista-node/node.env
WorkingDirectory=/opt/vista-node
ExecStart=/bin/bash -lc '/usr/bin/python3 /opt/vista-node/node_agent.py $(cat /opt/vista-node/capability.args)'
Restart=always
RestartSec=5
User=root
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=/var/lib/vista-node /opt/vista-node

[Install]
WantedBy=multi-user.target
EOF
cp "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ops/node_agent.py" /opt/vista-node/node_agent.py
systemctl daemon-reload
systemctl enable --now vista-node-agent
systemctl status vista-node-agent --no-pager || true
