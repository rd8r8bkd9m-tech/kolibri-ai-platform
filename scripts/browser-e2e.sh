#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
: "${VISTA_E2E_API_PORT:=8000}"
: "${VISTA_E2E_WEB_PORT:=5173}"
E2E_DIR="$ROOT/var/e2e"
rm -rf "$E2E_DIR" "$ROOT/var/vista-e2e.db" "$ROOT/var/e2e-artifacts"
mkdir -p "$E2E_DIR" "$ROOT/var/e2e-artifacts"
cleanup(){
  for pid in "${WEB_PID:-}" "${API_PID:-}"; do
    [[ -n "$pid" ]] || continue
    kill "$pid" >/dev/null 2>&1 || true
    sleep .2
    kill -9 "$pid" >/dev/null 2>&1 || true
    wait "$pid" >/dev/null 2>&1 || true
  done
}
trap cleanup EXIT
VISTA_ENV=local VISTA_DB_PATH="$ROOT/var/vista-e2e.db" VISTA_ARTIFACT_ROOT="$ROOT/var/e2e-artifacts" VISTA_SESSION_SECRET=e2e-session VISTA_OWNER_ACCESS_TOKEN=vista-local-owner VISTA_JSON_LOGS=0 PYTHONPATH="$ROOT" \
  python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port "$VISTA_E2E_API_PORT" >"$E2E_DIR/api.log" 2>&1 &
API_PID=$!
(cd frontend && VITE_API_URL="http://127.0.0.1:$VISTA_E2E_API_PORT" npm run dev -- --host 127.0.0.1 --port "$VISTA_E2E_WEB_PORT") >"$E2E_DIR/web.log" 2>&1 &
WEB_PID=$!
for _ in {1..100}; do curl -fsS "http://127.0.0.1:$VISTA_E2E_API_PORT/api/ready" >/dev/null 2>&1 && break; sleep .2; done
for _ in {1..100}; do curl -fsS "http://127.0.0.1:$VISTA_E2E_WEB_PORT" >/dev/null 2>&1 && break; sleep .2; done
python3 tools/e2e_product.py --base-url "http://127.0.0.1:$VISTA_E2E_WEB_PORT" --output "$E2E_DIR"
