#!/bin/bash
# Unified server provisioning for Kolibri Fleet
# Usage: ./provision-server.sh --ip <ip> --name <node-id> --role <role>
#
# 8 steps: SSH → deps → WireGuard → Agent → API → register → verify → registry update

set -euo pipefail

# Defaults
CONTROL_PLANE_URL="http://10.99.0.1:9101"
HEARTBEAT_INTERVAL=30
HEARTBEAT_DIR="/root/.kolibri-heartbeat"
WG_INTERFACE="wg-kolibri"
WG_PORT=51830
BOOTSTRAP_HOST="kolibri-qjns"

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --ip) SERVER_IP="$2"; shift 2;;
    --name) NODE_ID="$2"; shift 2;;
    --role) ROLE="$2"; shift 2;;
    --ssh-user) SSH_USER="$2"; shift 2;;
    --control-plane) CONTROL_PLANE_URL="$2"; shift 2;;
    --mesh-ip) MESH_IP="$2"; shift 2;;
    --bootstrap-host) BOOTSTRAP_HOST="$2"; shift 2;;
    *) echo "Unknown option: $1"; exit 1;;
  esac
done

SERVER_IP="${SERVER_IP:?--ip required}"
NODE_ID="${NODE_ID:?--name required}"
ROLE="${ROLE:-execution}"
SSH_USER="${SSH_USER:-root}"
if [ -z "${MESH_IP:-}" ]; then
  MESH_IP=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "$BOOTSTRAP_HOST" /usr/local/sbin/kolibri-mesh-enroll allocate)
fi
MESH_HUB_KEY=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "$BOOTSTRAP_HOST" "wg show $WG_INTERFACE public-key")
MESH_HUB_PORT=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "$BOOTSTRAP_HOST" "wg show $WG_INTERFACE listen-port")
MESH_HUB_IP=$(ssh -G "$BOOTSTRAP_HOST" | awk '/^hostname /{print $2; exit}')

echo "=== Provisioning $NODE_ID ($SERVER_IP) as $ROLE ==="

# Step 1: SSH connectivity check
echo "[1/8] Checking SSH connectivity..."
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$SSH_USER@$SERVER_IP" "echo ok" 2>/dev/null; then
  echo "  SSH not available, trying via Home jump..."
  SSH_CMD="ssh -o ConnectTimeout=5 -J kolibri-home $SSH_USER@$SERVER_IP"
  SCP_CMD="scp -o ProxyJump=kolibri-home"
else
  SSH_CMD="ssh -o ConnectTimeout=5 $SSH_USER@$SERVER_IP"
  SCP_CMD="scp"
fi

# Step 2: Install dependencies
echo "[2/8] Installing dependencies..."
$SSH_CMD "apt-get update -qq && apt-get install -y -qq python3 wireguard-tools 2>/dev/null || yum install -y python3 wireguard-tools 2>/dev/null || true"

# Step 3: Configure WireGuard
echo "[3/8] Configuring WireGuard..."
WG_PRIVATE_KEY=$(wg genkey)
WG_PUBLIC_KEY=$(echo "$WG_PRIVATE_KEY" | wg pubkey)

$SSH_CMD "cat > /etc/wireguard/$WG_INTERFACE.conf << EOF
[Interface]
Address = ${MESH_IP}/32
ListenPort = $WG_PORT
PrivateKey = $WG_PRIVATE_KEY

[Peer]
# One-time bootstrap peer; dynamic membership adds every other peer.
PublicKey = $MESH_HUB_KEY
AllowedIPs = 10.99.0.0/24
Endpoint = $MESH_HUB_IP:$WG_PORT
PersistentKeepalive = 25
EOF"

$SSH_CMD "systemctl enable --now wg-quick@$WG_INTERFACE 2>/dev/null || wg-quick up $WG_INTERFACE 2>/dev/null || true"

# Register through any reachable mesh member. The membership service then
# distributes the peer to every node without a static registrar list.
echo "[3b/8] Enrolling through $BOOTSTRAP_HOST..."
ssh -o ConnectTimeout=8 -o BatchMode=yes "$BOOTSTRAP_HOST" "
  set -eu
  /usr/local/sbin/kolibri-mesh-enroll enroll '$NODE_ID' '$WG_PUBLIC_KEY' '$MESH_IP' '$SERVER_IP:$WG_PORT'
"

# Step 4: Deploy heartbeat agent
echo "[4/8] Deploying heartbeat agent..."
$SSH_CMD "mkdir -p $HEARTBEAT_DIR"
$SCP_CMD /Users/kolibri/Documents/Codex/kolibri-ai-platform/ops/heartbeat_agent.py "$SSH_USER@$SERVER_IP:$HEARTBEAT_DIR/heartbeat_agent.py" 2>/dev/null || \
  $SSH_CMD "curl -sL https://raw.githubusercontent.com/rd8r8bkd9m-tech/kolibri-ai-platform/main/ops/heartbeat_agent.py -o $HEARTBEAT_DIR/heartbeat_agent.py"
$SSH_CMD "chmod +x $HEARTBEAT_DIR/heartbeat_agent.py"

# Install the same forwarding policy on every node when the source bundle is
# available locally; this keeps new servers aligned with the fleet baseline.
if [ -f "$(dirname "$0")/../ops/mesh-node-policy.sh" ]; then
  $SCP_CMD "$(dirname "$0")/../ops/mesh-node-policy.sh" "$SSH_USER@$SERVER_IP:/tmp/kolibri-mesh-node-policy"
  $SCP_CMD "$(dirname "$0")/../ops/systemd/kolibri-mesh-node-policy.service" "$SSH_USER@$SERVER_IP:/tmp/kolibri-mesh-node-policy.service"
  $SSH_CMD "install -m755 /tmp/kolibri-mesh-node-policy /usr/local/sbin/kolibri-mesh-node-policy; install -m644 /tmp/kolibri-mesh-node-policy.service /etc/systemd/system/; systemctl daemon-reload; systemctl enable --now kolibri-mesh-node-policy.service"
fi

# Every new server immediately becomes a registrar and persists the shared
# manifest locally. Discovery happens over the mesh subnet, without a list.
$SCP_CMD "$(dirname "$0")/../ops/mesh_registry.py" "$SSH_USER@$SERVER_IP:/tmp/mesh_registry.py"
$SCP_CMD "$(dirname "$0")/../ops/mesh-apply-peers" "$SSH_USER@$SERVER_IP:/tmp/mesh-apply-peers"
$SCP_CMD "$(dirname "$0")/../ops/mesh-enroll" "$SSH_USER@$SERVER_IP:/tmp/mesh-enroll"
$SCP_CMD "$(dirname "$0")/../ops/systemd/kolibri-mesh-registry.service" "$SSH_USER@$SERVER_IP:/tmp/kolibri-mesh-registry.service"
$SSH_CMD "install -d /usr/local/lib/kolibri /var/lib/kolibri-mesh /etc/wireguard/kolibri-peers.d; install -m755 /tmp/mesh_registry.py /usr/local/lib/kolibri/mesh_registry.py; install -m755 /tmp/mesh-apply-peers /usr/local/sbin/kolibri-mesh-apply-peers; install -m755 /tmp/mesh-enroll /usr/local/sbin/kolibri-mesh-enroll; install -m644 /tmp/kolibri-mesh-registry.service /etc/systemd/system/; systemctl daemon-reload; systemctl enable --now kolibri-mesh-registry.service"

# Step 5: Create systemd service
echo "[5/8] Creating systemd service..."
$SSH_CMD "cat > /etc/systemd/system/kolibri-heartbeat.service << EOF
[Unit]
Description=Kolibri Fleet Heartbeat Agent
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $HEARTBEAT_DIR/heartbeat_agent.py --node-id $NODE_ID --interval $HEARTBEAT_INTERVAL --control-plane $CONTROL_PLANE_URL
Restart=always
RestartSec=10
Environment=FACTORY_CONTROL_URL=$CONTROL_PLANE_URL

[Install]
WantedBy=multi-user.target
EOF"

# Step 6: Register with Control Plane
echo "[6/8] Registering with Control Plane..."
curl -s -X POST "$CONTROL_PLANE_URL/v1/nodes/register" \
  -H "Content-Type: application/json" \
  -d "{\"node_id\":\"$NODE_ID\",\"hostname\":\"$NODE_ID\",\"capabilities\":[\"$ROLE\",\"generic\"],\"api_port\":8001}" || true

# Step 7: Enable and start service
echo "[7/8] Starting heartbeat service..."
$SSH_CMD "systemctl daemon-reload && systemctl enable kolibri-heartbeat && systemctl restart kolibri-heartbeat"

# Step 8: Verify
echo "[8/8] Verifying..."
STATUS=$($SSH_CMD "systemctl is-active kolibri-heartbeat" 2>/dev/null || echo "failed")
if [ "$STATUS" = "active" ]; then
  echo "✅ Node $NODE_ID provisioned successfully"
  echo "   Role: $ROLE"
  echo "   Control Plane: $CONTROL_PLANE_URL"
  echo "   Heartbeat: ${HEARTBEAT_INTERVAL}s"
  echo "   WireGuard: $WG_INTERFACE"
else
  echo "❌ Failed to provision $NODE_ID"
  exit 1
fi
