#!/usr/bin/env bash
# Deploy or roll back the Home Russian wallboard without pushing to main.
# Usage:
#   scripts/deploy-home-wallboard.sh deploy [ssh-target] [remote-root]
#   scripts/deploy-home-wallboard.sh rollback <backup-dir> [ssh-target] [remote-root]

set -euo pipefail

ACTION="${1:-deploy}"
TARGET="${2:-kolibri-main}"
REMOTE_ROOT="${3:-/opt/kolibri-ai}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="${REMOTE_ROOT}/backups/home-wallboard-${STAMP}"

run_remote() {
  ssh -o ConnectTimeout=10 "$TARGET" "$1"
}

copy_file() {
  scp -o ConnectTimeout=10 "$1" "$TARGET:$2"
}

deploy() {
  echo "Deploying Home Russian wallboard to ${TARGET}:${REMOTE_ROOT}"
  run_remote "mkdir -p '${BACKUP_DIR}' '${REMOTE_ROOT}/backend' '${REMOTE_ROOT}/frontend/src'"
  run_remote "cp -a '${REMOTE_ROOT}/backend/factory_status.py' '${BACKUP_DIR}/factory_status.py' 2>/dev/null || true"
  run_remote "cp -a '${REMOTE_ROOT}/frontend/src/App.jsx' '${BACKUP_DIR}/App.jsx' 2>/dev/null || true"
  run_remote "cp -a '${REMOTE_ROOT}/frontend/src/App.css' '${BACKUP_DIR}/App.css' 2>/dev/null || true"

  copy_file "backend/factory_status.py" "${REMOTE_ROOT}/backend/factory_status.py"
  copy_file "frontend/src/App.jsx" "${REMOTE_ROOT}/frontend/src/App.jsx"
  copy_file "frontend/src/App.css" "${REMOTE_ROOT}/frontend/src/App.css"

  run_remote "cd '${REMOTE_ROOT}/frontend' && npm run build"
  run_remote "systemctl restart kolibri-ai && sleep 2 && systemctl is-active --quiet kolibri-ai"
  run_remote "curl -fsS http://127.0.0.1:8000/api/factory/status >/dev/null"

  echo "Deploy complete."
  echo "Rollback command:"
  echo "  scripts/deploy-home-wallboard.sh rollback '${BACKUP_DIR}' '${TARGET}' '${REMOTE_ROOT}'"
}

rollback() {
  local backup="${2:?backup dir required for rollback}"
  TARGET="${3:-$TARGET}"
  REMOTE_ROOT="${4:-$REMOTE_ROOT}"
  echo "Rolling back Home wallboard on ${TARGET}:${REMOTE_ROOT} from ${backup}"
  run_remote "test -d '${backup}'"
  run_remote "cp -a '${backup}/factory_status.py' '${REMOTE_ROOT}/backend/factory_status.py' 2>/dev/null || true"
  run_remote "cp -a '${backup}/App.jsx' '${REMOTE_ROOT}/frontend/src/App.jsx' 2>/dev/null || true"
  run_remote "cp -a '${backup}/App.css' '${REMOTE_ROOT}/frontend/src/App.css' 2>/dev/null || true"
  run_remote "cd '${REMOTE_ROOT}/frontend' && npm run build"
  run_remote "systemctl restart kolibri-ai && sleep 2 && systemctl is-active --quiet kolibri-ai"
  echo "Rollback complete."
}

case "$ACTION" in
  deploy) deploy ;;
  rollback) rollback "$@" ;;
  *)
    echo "Usage: $0 deploy [ssh-target] [remote-root]"
    echo "       $0 rollback <backup-dir> [ssh-target] [remote-root]"
    exit 2
    ;;
esac
