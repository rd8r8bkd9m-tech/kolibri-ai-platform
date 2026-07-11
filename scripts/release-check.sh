#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${VISTA_RELEASE_PORT:=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')}"
: "${VISTA_RELEASE_SESSION_SECRET:=vista-release-session-$(python3 -c 'import secrets; print(secrets.token_hex(24))')}"
: "${VISTA_RELEASE_OWNER_TOKEN:=vista-release-owner-$(python3 -c 'import secrets; print(secrets.token_hex(24))')}"
: "${VISTA_RELEASE_NODE_TOKEN:=vista-release-node-$(python3 -c 'import secrets; print(secrets.token_hex(24))')}"
: "${VISTA_RELEASE_SIGNING_SECRET:=vista-release-signing-$(python3 -c 'import secrets; print(secrets.token_hex(24))')}"
RELEASE_DIR="$ROOT/var/release-check"
RELEASE_DB="$RELEASE_DIR/vista.db"
RELEASE_ARTIFACTS="$RELEASE_DIR/artifacts"
rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR" "$RELEASE_ARTIFACTS"

./scripts/validate-fone.sh

cleanup() {
  if [[ -n "${API_PID:-}" ]]; then
    kill "$API_PID" >/dev/null 2>&1 || true
    for _ in {1..20}; do
      kill -0 "$API_PID" >/dev/null 2>&1 || break
      sleep 0.1
    done
    kill -9 "$API_PID" >/dev/null 2>&1 || true
    wait "$API_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

VISTA_ENV=production \
VISTA_DB_PATH="$RELEASE_DB" \
VISTA_ARTIFACT_ROOT="$RELEASE_ARTIFACTS" \
VISTA_SESSION_SECRET="$VISTA_RELEASE_SESSION_SECRET" \
VISTA_OWNER_ACCESS_TOKEN="$VISTA_RELEASE_OWNER_TOKEN" \
VISTA_NODE_JOIN_TOKEN="$VISTA_RELEASE_NODE_TOKEN" \
VISTA_NODE_SIGNING_SECRET="$VISTA_RELEASE_SIGNING_SECRET" \
VISTA_ALLOWED_ORIGINS="http://127.0.0.1:5173,http://127.0.0.1:8080" \
VISTA_JSON_LOGS=0 \
PYTHONPATH="$ROOT" python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port "$VISTA_RELEASE_PORT" >"$RELEASE_DIR/api.log" 2>&1 &
API_PID=$!

for _ in {1..80}; do
  if curl -fsS "http://127.0.0.1:$VISTA_RELEASE_PORT/api/ready" >/dev/null 2>&1; then break; fi
  sleep 0.25
done
curl -fsS "http://127.0.0.1:$VISTA_RELEASE_PORT/api/ready" > "$RELEASE_DIR/readiness.json"

python3 tools/http_product_smoke.py \
  --base-url "http://127.0.0.1:$VISTA_RELEASE_PORT" \
  --report "$RELEASE_DIR/http-product-smoke.json"

VISTA_OWNER_ACCESS_TOKEN="$VISTA_RELEASE_OWNER_TOKEN" \
VISTA_NODE_JOIN_TOKEN="$VISTA_RELEASE_NODE_TOKEN" \
VISTA_NODE_SIGNING_SECRET="$VISTA_RELEASE_SIGNING_SECRET" \
./scripts/run-factory-canary.sh \
  --control-url "http://127.0.0.1:$VISTA_RELEASE_PORT" \
  --report "$RELEASE_DIR/FACTORY_CANARY_REPORT.md"

python3 tools/backup_restore_check.py \
  --database "$RELEASE_DB" \
  --artifacts "$RELEASE_ARTIFACTS" \
  --output "$RELEASE_DIR/backup" \
  --report "$RELEASE_DIR/backup-restore-check.json"

python3 tools/release_readiness_check.py \
  --base-url "http://127.0.0.1:$VISTA_RELEASE_PORT" \
  --owner-token "$VISTA_RELEASE_OWNER_TOKEN" \
  --output "$RELEASE_DIR/release-readiness.json" \
  --summary "$RELEASE_DIR/release-summary.json"

echo "ok: Vista release check passed; evidence=$RELEASE_DIR"
