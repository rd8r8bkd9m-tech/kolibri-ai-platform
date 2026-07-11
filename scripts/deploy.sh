#!/usr/bin/env bash
# Kolibri deployment compatibility entrypoint.
#
# Legacy host-targeted copies and service restarts are intentionally disabled.
# All releases pass through the Home Control Plane, signed manifests, owner
# approval, fenced tasks, health gates, and recorded rollback tasks.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMAND="${1:-}"

case "$COMMAND" in
  validate|plan|apply)
    ;;
  main|uiap|qjns|9fts|home|network|all|"")
    echo '{"status":"blocked","reason":"legacy_direct_deploy_disabled","next_action":"use scripts/deploy.sh validate|plan|apply with a signed release manifest"}' >&2
    exit 2
    ;;
  *)
    echo "usage: $0 {validate|plan|apply} [release-controller options]" >&2
    exit 2
    ;;
esac

exec "${KOLIBRI_PYTHON:-python3}" "$ROOT/ops/release_controller.py" "$@"
