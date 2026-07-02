#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DEPLOY_HOST="${1:-plastilin}"
DEPLOY_USER="${2:-ladik}"
DEPLOY_PORT="${3:-2222}"
NOC_PORT=9191
CLIENT_PORTAL_PORT=8180

echo "=== Verifying Home NOC Control Center on ${DEPLOY_USER}@${DEPLOY_HOST} ==="
FAIL=0

ssh_cmd() {
  ssh -o ConnectTimeout=10 -p "$DEPLOY_PORT" "${DEPLOY_USER}@${DEPLOY_HOST}" "$@"
}

echo "[1/6] Service kolibri-control-center is active..."
if ssh_cmd "systemctl is-active kolibri-control-center" | grep -q "active"; then
  echo "  ✓ kolibri-control-center: active"
else
  echo "  ✗ kolibri-control-center: NOT active"
  FAIL=1
fi

echo "[2/6] NOC server listening on port ${NOC_PORT}..."
if ssh_cmd "ss -tlnp | grep -q ':${NOC_PORT} '"; then
  echo "  ✓ Port ${NOC_PORT}: listening"
else
  echo "  ✗ Port ${NOC_PORT}: NOT listening"
  FAIL=1
fi

echo "[3/6] Client portal port ${CLIENT_PORTAL_PORT} NOT served by NOC..."
if ssh_cmd "ss -tlnp | grep -q ':${CLIENT_PORTAL_PORT} '" 2>/dev/null; then
  echo "  ✗ Port ${CLIENT_PORTAL_PORT}: is listening (client portal present!)"
  FAIL=1
else
  echo "  ✓ Port ${CLIENT_PORTAL_PORT}: NOT listening (correct — client portal forbidden)"
fi

echo "[4/6] /api/snapshot returns health/counts..."
SNAPSHOT=$(ssh_cmd "curl -sf http://127.0.0.1:${NOC_PORT}/api/snapshot 2>/dev/null" || echo "{}")
if echo "$SNAPSHOT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'health' in d and 'nodes_total' in d and 'tasks_total' in d" 2>/dev/null; then
  HEALTH=$(echo "$SNAPSHOT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('health',{}).get('status','?'))")
  NODES=$(echo "$SNAPSHOT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('nodes_total',0))")
  TASKS=$(echo "$SNAPSHOT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tasks_total',0))")
  echo "  ✓ /api/snapshot: health=${HEALTH}, nodes=${NODES}, tasks=${TASKS}"
else
  echo "  ✗ /api/snapshot: invalid or missing response"
  FAIL=1
fi

echo "[5/6] Firefox kiosk target is 127.0.0.1:${NOC_PORT}..."
KIOSK_ENV=$(ssh_cmd "systemctl show kolibri-home-kiosk -p Environment 2>/dev/null" || echo "")
if echo "$KIOSK_ENV" | grep -q "127.0.0.1:${NOC_PORT}"; then
  echo "  ✓ Kiosk URL: http://127.0.0.1:${NOC_PORT}"
elif echo "$KIOSK_ENV" | grep -q "KOLIBRI_KIOSK_URL"; then
  KIOSK_URL=$(echo "$KIOSK_ENV" | grep -oP 'KOLIBRI_KIOSK_URL=\K[^\s]+')
  echo "  ✗ Kiosk URL: ${KIOSK_URL} (expected http://127.0.0.1:${NOC_PORT})"
  FAIL=1
else
  echo "  ~ Kiosk service not found or no KIOSK_URL set (manual check required)"
fi

echo "[6/6] Wallboard HTML present on disk..."
if ssh_cmd "test -f /opt/kolibri-control-center/noc_wallboard.html"; then
  echo "  ✓ noc_wallboard.html: present"
else
  echo "  ✗ noc_wallboard.html: missing"
  FAIL=1
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "=== All checks passed ✓ ==="
else
  echo "=== Some checks FAILED ✗ ==="
  exit 1
fi
