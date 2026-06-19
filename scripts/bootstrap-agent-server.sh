#!/bin/bash
# Prepare a fresh VPS for Kolibri agent work.
# Default mode is dry-run. Pass --apply only after the server is purchased,
# classified, and approved for project use.

set -euo pipefail

APPLY=false
SERVER=""
USER_NAME="root"
AGENT_ROOT="/opt/kolibri-ai/agent-worktrees"
PROJECT_ROOT="/opt/kolibri-ai"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=true; shift ;;
    --server) SERVER="${2:?server host required}"; shift 2 ;;
    --user) USER_NAME="${2:?user required}"; shift 2 ;;
    --agent-root) AGENT_ROOT="${2:?path required}"; shift 2 ;;
    --project-root) PROJECT_ROOT="${2:?path required}"; shift 2 ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [ -z "$SERVER" ]; then
  echo "Usage: $0 --server <host-or-ip> [--user root] [--apply]" >&2
  exit 2
fi

SSH_TARGET="${USER_NAME}@${SERVER}"

remote_script=$(cat <<'REMOTE'
set -euo pipefail

echo "=== Host ==="
hostnamectl 2>/dev/null || hostname

echo "=== Resources ==="
free -h 2>/dev/null || true
df -h / 2>/dev/null || true
nproc 2>/dev/null || true

echo "=== Toolchain ==="
command -v git || true
command -v python3 || true
command -v node || true
command -v npm || true
command -v mimo || command -v /root/.mimocode/bin/mimo || command -v /usr/local/bin/mimo || true

echo "=== Kolibri paths ==="
ls -ld "$PROJECT_ROOT" 2>/dev/null || true
ls -ld "$AGENT_ROOT" 2>/dev/null || true

if [ "$APPLY" = "true" ]; then
  mkdir -p "$PROJECT_ROOT" "$AGENT_ROOT" "$PROJECT_ROOT/logs"
  chmod 755 "$PROJECT_ROOT" "$AGENT_ROOT" "$PROJECT_ROOT/logs"
  if command -v ufw >/dev/null 2>&1; then
    ufw allow from 10.99.0.0/24 to any port 4096 proto tcp || true
  fi
  echo "Applied Kolibri agent directories and VPN-scoped Mimo firewall rule when ufw exists."
else
  echo "Dry-run only. Re-run with --apply to create directories/firewall rule."
fi
REMOTE
)

echo "Target: $SSH_TARGET"
echo "Mode: $([ "$APPLY" = true ] && echo apply || echo dry-run)"

ssh -o ConnectTimeout=10 "$SSH_TARGET" \
  "APPLY='$APPLY' PROJECT_ROOT='$PROJECT_ROOT' AGENT_ROOT='$AGENT_ROOT' bash -s" \
  <<< "$remote_script"
