#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/var"
rm -f "$ROOT/var/vista-test.db" "$ROOT/var/vista-test.db-shm" "$ROOT/var/vista-test.db-wal"
rm -rf "$ROOT/var/test-artifacts"
export VISTA_ENV=local
export VISTA_DB_PATH="$ROOT/var/vista-test.db"
export VISTA_ARTIFACT_ROOT="$ROOT/var/test-artifacts"
export VISTA_SESSION_SECRET="vista-test-session-secret"
export VISTA_OWNER_ACCESS_TOKEN="vista-local-owner"
python3 -m compileall -q backend tools ops
for script in scripts/*.sh; do bash -n "$script"; done
python3 tools/validate_roles.py
python3 tools/validate_fone_os.py
python3 tools/validate_release_contract.py
python3 tools/security_scan.py
PYTHONPATH="$ROOT" pytest -q backend/tests tests
cd frontend
npm ci --ignore-scripts --no-audit --no-fund
npm run test:ci
npm run build
cd "$ROOT"
if command -v cargo >/dev/null 2>&1; then
  cargo test --workspace
  cargo check --manifest-path apps/vista-desktop/src-tauri/Cargo.toml
else
  echo "cargo not found; Rust/Tauri checks are mandatory in GitHub CI"
fi
echo "ok: Vista OS product validation completed"
