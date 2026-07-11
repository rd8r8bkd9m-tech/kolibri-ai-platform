#!/bin/bash
# Unified server provisioning for Kolibri Fleet
# Usage: ./provision-server.sh --ip <ip> --name <node-id> --role <role>
#
# 8 steps: SSH → deps → WireGuard → mesh → Agent Host → Home resolve → start → verify

set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTROL_PLANE_URL="${KOLIBRI_FACTORY_CONTROL_URL:-}"
AGENT_HEARTBEAT_INTERVAL=10
WG_INTERFACE="wg-kolibri"
WG_PORT=51830
MESH_MANIFEST="${KOLIBRI_MESH_MEMBERSHIP_MANIFEST:-}"
REGISTRAR_SSH_USER="${KOLIBRI_MESH_REGISTRAR_SSH_USER:-root}"
SSH_JUMP_HOST="${KOLIBRI_SSH_JUMP_HOST:-}"

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --ip) SERVER_IP="$2"; shift 2;;
    --name) NODE_ID="$2"; shift 2;;
    --role) ROLE="$2"; shift 2;;
    --ssh-user) SSH_USER="$2"; shift 2;;
    --control-plane) CONTROL_PLANE_URL="$2"; shift 2;;
    --heartbeat-interval) AGENT_HEARTBEAT_INTERVAL="$2"; shift 2;;
    --mesh-manifest) MESH_MANIFEST="$2"; shift 2;;
    --registrar-ssh-user) REGISTRAR_SSH_USER="$2"; shift 2;;
    --ssh-jump-host) SSH_JUMP_HOST="$2"; shift 2;;
    *) echo "Unknown option: $1"; exit 1;;
  esac
done

SERVER_IP="${SERVER_IP:?--ip required}"
NODE_ID="${NODE_ID:?--name required}"
ROLE="${ROLE:-execution}"
SSH_USER="${SSH_USER:-root}"
case "$NODE_ID" in
  *[!A-Za-z0-9._-]*) echo "--name contains unsafe characters" >&2; exit 2;;
esac
case "$ROLE" in
  *[!A-Za-z0-9_.,:-]*) echo "--role contains unsafe characters" >&2; exit 2;;
esac
case "$AGENT_HEARTBEAT_INTERVAL" in
  ''|*[!0-9]*) echo "--heartbeat-interval must be an integer" >&2; exit 2;;
esac
for required in \
  "$SOURCE_ROOT/ops/agent_host.py" \
  "$SOURCE_ROOT/ops/mimo/kolibri-response-only.md" \
  "$SOURCE_ROOT/ops/control_plane_endpoint.py" \
  "$SOURCE_ROOT/ops/runner_access.py" \
  "$SOURCE_ROOT/ops/runner-access.default.json" \
  "$SOURCE_ROOT/ops/release_authority.py" \
  "$SOURCE_ROOT/ops/release_helper.py" \
  "$SOURCE_ROOT/ops/release_installer.py" \
  "$SOURCE_ROOT/ops/systemd/kolibri-agent-host.service" \
  "$SOURCE_ROOT/ops/systemd/kolibri-release-helper.service" \
  "$SOURCE_ROOT/ops/systemd/kolibri-release-helper.socket" \
  "$SOURCE_ROOT/scripts/select-mesh-registrar.py"; do
  [ -f "$required" ] || { echo "required runtime file missing: $required" >&2; exit 2; }
done
if [ -n "$CONTROL_PLANE_URL" ] || [ -n "${KOLIBRI_FACTORY_CONTROL_URLS:-}" ]; then
  CONTROL_PLANE_URL=$(python3 "$SOURCE_ROOT/ops/control_plane_endpoint.py" \
    --print-url \
    --control-url "$CONTROL_PLANE_URL" \
    --control-urls "${KOLIBRI_FACTORY_CONTROL_URLS:-}")
fi
MESH_MANIFEST="${MESH_MANIFEST:?--mesh-manifest or KOLIBRI_MESH_MEMBERSHIP_MANIFEST is required}"
REGISTRAR_JSON=$(python3 "$SOURCE_ROOT/scripts/select-mesh-registrar.py" --manifest "$MESH_MANIFEST")
REGISTRAR_NODE=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["node_id"])' "$REGISTRAR_JSON")
REGISTRAR_HOST=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["ssh_host"])' "$REGISTRAR_JSON")

echo "=== Provisioning $NODE_ID ($SERVER_IP) as $ROLE ==="

# Step 1: SSH connectivity check
echo "[1/8] Checking SSH connectivity..."
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$SSH_USER@$SERVER_IP" "echo ok" 2>/dev/null; then
  [ -n "$SSH_JUMP_HOST" ] || { echo "direct SSH unavailable and KOLIBRI_SSH_JUMP_HOST is unset" >&2; exit 1; }
  echo "  SSH not available, trying configured jump host..."
  SSH_CMD="ssh -o ConnectTimeout=5 -J $SSH_JUMP_HOST $SSH_USER@$SERVER_IP"
  SCP_CMD="scp -o ProxyJump=$SSH_JUMP_HOST"
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

# Step 4: Install mesh runtime and the exact Agent Host/resolver source pair.
echo "[4/8] Installing mesh and Agent Host runtime..."
$SCP_CMD "$SOURCE_ROOT/ops/agent_host.py" "$SSH_USER@$SERVER_IP:/tmp/kolibri-agent-host"
$SCP_CMD "$SOURCE_ROOT/ops/mimo/kolibri-response-only.md" "$SSH_USER@$SERVER_IP:/tmp/kolibri-response-only.md"
$SCP_CMD "$SOURCE_ROOT/ops/control_plane_endpoint.py" "$SSH_USER@$SERVER_IP:/tmp/control_plane_endpoint.py"
$SCP_CMD "$SOURCE_ROOT/ops/runner_access.py" "$SSH_USER@$SERVER_IP:/tmp/runner_access.py"
$SCP_CMD "$SOURCE_ROOT/ops/runner-access.default.json" "$SSH_USER@$SERVER_IP:/tmp/runner-access.json"
$SCP_CMD "$SOURCE_ROOT/ops/release_authority.py" "$SSH_USER@$SERVER_IP:/tmp/release_authority.py"
$SCP_CMD "$SOURCE_ROOT/ops/release_helper.py" "$SSH_USER@$SERVER_IP:/tmp/release_helper.py"
$SCP_CMD "$SOURCE_ROOT/ops/release_installer.py" "$SSH_USER@$SERVER_IP:/tmp/release_installer.py"
$SCP_CMD "$SOURCE_ROOT/ops/systemd/kolibri-agent-host.service" "$SSH_USER@$SERVER_IP:/tmp/kolibri-agent-host.service"
$SCP_CMD "$SOURCE_ROOT/ops/systemd/kolibri-release-helper.service" "$SSH_USER@$SERVER_IP:/tmp/kolibri-release-helper.service"
$SCP_CMD "$SOURCE_ROOT/ops/systemd/kolibri-release-helper.socket" "$SSH_USER@$SERVER_IP:/tmp/kolibri-release-helper.socket"

# Install the same forwarding policy on every node when the source bundle is
# available locally; this keeps new servers aligned with the fleet baseline.
if [ -f "$SOURCE_ROOT/ops/mesh-node-policy.sh" ]; then
  $SCP_CMD "$SOURCE_ROOT/ops/mesh-node-policy.sh" "$SSH_USER@$SERVER_IP:/tmp/kolibri-mesh-node-policy"
  $SCP_CMD "$SOURCE_ROOT/ops/systemd/kolibri-mesh-node-policy.service" "$SSH_USER@$SERVER_IP:/tmp/kolibri-mesh-node-policy.service"
  $SSH_CMD "install -m755 /tmp/kolibri-mesh-node-policy /usr/local/sbin/kolibri-mesh-node-policy; install -m644 /tmp/kolibri-mesh-node-policy.service /etc/systemd/system/; systemctl daemon-reload; systemctl enable --now kolibri-mesh-node-policy.service"
fi

# Every new server immediately becomes a registrar and persists the shared
# manifest locally. Discovery happens over the mesh subnet, without a list.
$SCP_CMD "$SOURCE_ROOT/ops/mesh_registry.py" "$SSH_USER@$SERVER_IP:/tmp/mesh_registry.py"
$SCP_CMD "$SOURCE_ROOT/ops/mesh-apply-peers" "$SSH_USER@$SERVER_IP:/tmp/mesh-apply-peers"
$SCP_CMD "$SOURCE_ROOT/ops/mesh-enroll" "$SSH_USER@$SERVER_IP:/tmp/mesh-enroll"
$SCP_CMD "$SOURCE_ROOT/ops/systemd/kolibri-mesh-apply-peers.service" "$SSH_USER@$SERVER_IP:/tmp/kolibri-mesh-apply-peers.service"
$SCP_CMD "$SOURCE_ROOT/ops/systemd/kolibri-mesh-registry.service" "$SSH_USER@$SERVER_IP:/tmp/kolibri-mesh-registry.service"
$SSH_CMD "install -d /usr/local/lib/kolibri /var/lib/kolibri-mesh /etc/wireguard/kolibri-peers.d; install -m755 /tmp/mesh_registry.py /usr/local/lib/kolibri/mesh_registry.py; install -m755 /tmp/mesh-apply-peers /usr/local/sbin/kolibri-mesh-apply-peers; install -m755 /tmp/mesh-enroll /usr/local/sbin/kolibri-mesh-enroll; install -m644 /tmp/kolibri-mesh-apply-peers.service /etc/systemd/system/; install -m644 /tmp/kolibri-mesh-registry.service /etc/systemd/system/; systemctl daemon-reload; systemctl enable --now kolibri-mesh-apply-peers.service kolibri-mesh-registry.service"

# Step 5: Install the runtime and a single-authority environment file.
echo "[5/8] Installing Agent Host service..."
RUNTIME_ENV=$(mktemp)
trap 'rm -f "$RUNTIME_ENV"' EXIT
{
  printf 'KOLIBRI_NODE_ID=%s\n' "$NODE_ID"
  printf 'KOLIBRI_AGENT_CAPABILITIES=%s,generic\n' "$ROLE"
  printf 'KOLIBRI_HEARTBEAT_INTERVAL=%s\n' "$AGENT_HEARTBEAT_INTERVAL"
  printf 'KOLIBRI_MESH_MEMBERSHIP_MANIFEST=/var/lib/kolibri-mesh/peers.json\n'
  printf 'KOLIBRI_RUNNER_ACCESS_MANIFEST=/etc/kolibri/runner-access.json\n'
  printf 'KOLIBRI_ARTIFACT_ROOT=/var/lib/kolibri-agent/artifacts\n'
  printf 'KOLIBRI_RELEASE_ROOT=/opt/kolibri-ai/releases\n'
  printf 'KOLIBRI_RELEASE_CURRENT_LINK=/opt/kolibri-ai/current\n'
  printf 'KOLIBRI_RELEASE_ALLOWED_SIGNERS=/etc/kolibri/release_allowed_signers\n'
  printf 'KOLIBRI_RELEASE_POLICY=/etc/kolibri/release-policy.json\n'
  if [ -n "$CONTROL_PLANE_URL" ]; then
    printf 'KOLIBRI_FACTORY_CONTROL_URL=%s\n' "$CONTROL_PLANE_URL"
  fi
} >"$RUNTIME_ENV"
$SCP_CMD "$RUNTIME_ENV" "$SSH_USER@$SERVER_IP:/tmp/kolibri-agent-host.env"
$SSH_CMD "getent group kolibri-agent >/dev/null || groupadd --system kolibri-agent; id -u kolibri-agent >/dev/null 2>&1 || useradd --system --gid kolibri-agent --home-dir /var/lib/kolibri-agent --shell /usr/sbin/nologin kolibri-agent; install -d -m755 /usr/local/lib/kolibri /usr/local/lib/kolibri/mimo /opt/kolibri-ai /opt/kolibri-ai/releases /etc/kolibri /var/lib/kolibri-release; install -d -m700 /var/lib/kolibri-release/artifacts; install -d -o kolibri-agent -g kolibri-agent -m700 /var/lib/kolibri-agent /var/lib/kolibri-agent/worktrees /var/lib/kolibri-agent/artifacts; install -m755 /tmp/kolibri-agent-host /usr/local/bin/kolibri-agent-host; install -m644 /tmp/kolibri-response-only.md /usr/local/lib/kolibri/mimo/kolibri-response-only.md; install -m644 /tmp/control_plane_endpoint.py /usr/local/lib/kolibri/control_plane_endpoint.py; install -m644 /tmp/runner_access.py /usr/local/lib/kolibri/runner_access.py; install -m644 /tmp/runner-access.json /etc/kolibri/runner-access.json; install -m644 /tmp/release_authority.py /usr/local/lib/kolibri/release_authority.py; install -m644 /tmp/release_helper.py /usr/local/lib/kolibri/release_helper.py; install -m644 /tmp/release_installer.py /usr/local/lib/kolibri/release_installer.py; install -m644 /tmp/kolibri-agent-host.service /etc/systemd/system/kolibri-agent-host.service; install -m644 /tmp/kolibri-release-helper.service /etc/systemd/system/kolibri-release-helper.service; install -m644 /tmp/kolibri-release-helper.socket /etc/systemd/system/kolibri-release-helper.socket; install -m640 -o root -g kolibri-agent /tmp/kolibri-agent-host.env /etc/kolibri-agent-host.env; PYTHONPATH=/usr/local/lib/kolibri /usr/bin/python3 /usr/local/lib/kolibri/runner_access.py --manifest /etc/kolibri/runner-access.json >/dev/null; systemctl daemon-reload; systemctl enable --now kolibri-release-helper.socket"

# Step 6: Fail closed until the replicated manifest names exactly one Home.
echo "[6/8] Resolving canonical Home Control Plane..."
$SSH_CMD 'for attempt in $(seq 1 30); do set -a; . /etc/kolibri-agent-host.env; set +a; if PYTHONPATH=/usr/local/lib/kolibri /usr/bin/python3 /usr/local/lib/kolibri/control_plane_endpoint.py --print-url >/dev/null 2>&1; then exit 0; fi; sleep 2; done; echo canonical_home_control_plane_unresolved >&2; exit 1'

# Step 7: Enable and start service
echo "[7/8] Starting Agent Host service..."
$SSH_CMD "systemctl enable kolibri-agent-host.service && systemctl restart kolibri-agent-host.service"

# Step 8: Verify
echo "[8/8] Verifying..."
STATUS=$($SSH_CMD "systemctl is-active kolibri-agent-host.service" 2>/dev/null || echo "failed")
if [ "$STATUS" = "active" ]; then
  echo "✅ Node $NODE_ID provisioned successfully"
  echo "   Role: $ROLE"
  echo "   Control Plane: ${CONTROL_PLANE_URL:-dynamic Home from /var/lib/kolibri-mesh/peers.json}"
  echo "   Agent heartbeat: ${AGENT_HEARTBEAT_INTERVAL}s"
  echo "   WireGuard: $WG_INTERFACE"
else
  echo "❌ Failed to provision $NODE_ID"
  exit 1
fi
