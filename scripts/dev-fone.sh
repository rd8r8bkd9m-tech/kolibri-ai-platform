#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/var" "$ROOT/var/artifacts"

export VISTA_ENV="${VISTA_ENV:-local}"
export VISTA_DB_PATH="${VISTA_DB_PATH:-$ROOT/var/vista.db}"
export VISTA_ARTIFACT_ROOT="${VISTA_ARTIFACT_ROOT:-$ROOT/var/artifacts}"
export VISTA_SESSION_SECRET="${VISTA_SESSION_SECRET:-vista-local-session-secret-change-in-production}"
export VISTA_OWNER_ACCESS_TOKEN="${VISTA_OWNER_ACCESS_TOKEN:-vista-local-owner}"
export VISTA_ALLOWED_ORIGINS="${VISTA_ALLOWED_ORIGINS:-http://127.0.0.1:5173,http://localhost:5173}"
export VISTA_JSON_LOGS="${VISTA_JSON_LOGS:-0}"
export VISTA_API_PORT="${VISTA_API_PORT:-8000}"
export VISTA_WEB_PORT="${VISTA_WEB_PORT:-5173}"

python3 -m pip install -q -r backend/requirements.txt
(
  cd frontend
  npm ci --ignore-scripts --no-audit --no-fund
)

cleanup() {
  if [[ -n "${API_PID:-}" ]]; then
    kill "$API_PID" >/dev/null 2>&1 || true
    wait "$API_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

PYTHONPATH="$ROOT" python3 -m uvicorn backend.app.main:app \
  --host 127.0.0.1 --port "$VISTA_API_PORT" &
API_PID=$!

for _ in {1..80}; do
  if curl -fsS "http://127.0.0.1:$VISTA_API_PORT/api/ready" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done
curl -fsS "http://127.0.0.1:$VISTA_API_PORT/api/ready" >/dev/null

echo "Vista API: http://127.0.0.1:$VISTA_API_PORT"
echo "Vista UI:  http://127.0.0.1:$VISTA_WEB_PORT"
cd frontend
VITE_API_URL="http://127.0.0.1:$VISTA_API_PORT" npm run dev -- --host 127.0.0.1 --port "$VISTA_WEB_PORT"
