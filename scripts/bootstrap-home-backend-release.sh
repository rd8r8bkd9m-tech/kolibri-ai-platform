#!/usr/bin/env bash
# Owner-operated, one-time Home backend release drop-in bootstrap.
#
# Default mode is a read-only remote plan.  --apply is the only mutation gate.
# Home is resolved from the replicated membership manifest; no host address is
# embedded here.

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MANIFEST=""
RUN_ID="home-backend-release-$(date -u +%Y%m%dT%H%M%SZ)"
APPLY=false
REMOTE_STAGE=""
REMOTE_TARGET=""
STAGED=false

usage() {
  cat >&2 <<'EOF'
usage: scripts/bootstrap-home-backend-release.sh \
  --manifest FILE [--run-id ID] [--apply]

Default mode performs a read-only Home identity, current-release, existing
venv import, systemd metadata and destination preflight.  --apply installs
only the backend release drop-in and restarts only kolibri-backend.service.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest)
      MANIFEST=${2:?missing manifest path}
      shift 2
      ;;
    --run-id)
      RUN_ID=${2:?missing run ID}
      shift 2
      ;;
    --apply)
      APPLY=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

[ -f "$MANIFEST" ] && [ ! -L "$MANIFEST" ] || {
  echo "backend_bootstrap_manifest_invalid" >&2
  exit 2
}
case "$RUN_ID" in
  ""|*[!A-Za-z0-9._-]*) echo "backend_bootstrap_run_id_invalid" >&2; exit 2 ;;
esac

for command_name in python3 ssh scp; do
  command -v "$command_name" >/dev/null || {
    echo "backend_bootstrap_local_prerequisite_missing" >&2
    exit 2
  }
done

HELPER="$ROOT_DIR/ops/home_backend_release_bootstrap.py"
DROPIN="$ROOT_DIR/ops/systemd/kolibri-backend-home-release.conf"
CONTROL_RESOLVER="$ROOT_DIR/ops/control_plane_endpoint.py"
for source in "$HELPER" "$DROPIN" "$CONTROL_RESOLVER"; do
  [ -f "$source" ] && [ ! -L "$source" ] || {
    echo "backend_bootstrap_source_invalid" >&2
    exit 2
  }
done

# Validate the repository copy before any remote contact. No environment or
# source content is emitted.
PYTHONPATH="$ROOT_DIR" python3 - "$HELPER" "$DROPIN" <<'PY'
import importlib.util
import sys
from pathlib import Path

helper_path = Path(sys.argv[1])
dropin_path = Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("kolibri_home_backend_bootstrap", helper_path)
if spec is None or spec.loader is None:
    raise SystemExit("backend_bootstrap_source_invalid")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
if module._validate_source(dropin_path) != module.CANONICAL_DROPIN:
    raise SystemExit("backend_dropin_source_contract_mismatch")
PY

HOME_URL=$(
  PYTHONPATH="$ROOT_DIR" python3 "$CONTROL_RESOLVER" \
    --print-url --manifest "$MANIFEST"
)
HOME_HOST=$(
  python3 -c \
    'import ipaddress,sys,urllib.parse; host=urllib.parse.urlsplit(sys.argv[1]).hostname or ""; value=ipaddress.ip_address(host); assert value.version == 4 and value.is_private and not value.is_loopback; print(value)' \
    "$HOME_URL"
)
REMOTE_TARGET="root@$HOME_HOST"

SSH_OPTIONS=(
  -o BatchMode=yes
  -o ConnectTimeout=8
  -o ConnectionAttempts=1
  -o ServerAliveInterval=5
  -o ServerAliveCountMax=2
)

# Prove that the manifest-selected address belongs to this host. Raw interface
# output is consumed by the local verifier and never printed.
if ! ssh "${SSH_OPTIONS[@]}" "$REMOTE_TARGET" \
  /usr/sbin/ip -4 -o addr show 2>/dev/null |
  python3 -c \
    'import ipaddress,sys; expected=str(ipaddress.ip_address(sys.argv[1])); values={field.split("/",1)[0] for line in sys.stdin for field in line.split() if "/" in field}; raise SystemExit(0 if expected in values else 1)' \
    "$HOME_HOST"; then
  echo "backend_bootstrap_target_not_home" >&2
  exit 1
fi

ssh "${SSH_OPTIONS[@]}" "$REMOTE_TARGET" \
  'test "$(id -u)" = 0 && test -x /usr/bin/python3 && test -x /usr/bin/systemctl && test -x /usr/bin/curl' \
  </dev/null || {
    echo "backend_bootstrap_remote_prerequisite_missing" >&2
    exit 1
  }

if [ "$APPLY" != true ]; then
  # Streaming the helper over stdin leaves no file on Home. The helper emits
  # one sanitized JSON envelope and never emits command output or environment.
  ssh "${SSH_OPTIONS[@]}" "$REMOTE_TARGET" \
    /usr/bin/python3 - <"$HELPER"
  exit $?
fi

REMOTE_STAGE="/tmp/kolibri-home-backend-release-$RUN_ID"
cleanup() {
  if [ "$STAGED" = true ]; then
    ssh "${SSH_OPTIONS[@]}" "$REMOTE_TARGET" \
      "/bin/rm -rf -- '$REMOTE_STAGE'" </dev/null >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

ssh "${SSH_OPTIONS[@]}" "$REMOTE_TARGET" \
  "/usr/bin/install -d -o root -g root -m 0700 '$REMOTE_STAGE'" </dev/null
STAGED=true
scp -q "${SSH_OPTIONS[@]}" \
  "$HELPER" "$REMOTE_TARGET:$REMOTE_STAGE/home_backend_release_bootstrap.py"
scp -q "${SSH_OPTIONS[@]}" \
  "$DROPIN" "$REMOTE_TARGET:$REMOTE_STAGE/10-release.conf"

ssh "${SSH_OPTIONS[@]}" "$REMOTE_TARGET" \
  "/usr/bin/chown root:root '$REMOTE_STAGE/home_backend_release_bootstrap.py' '$REMOTE_STAGE/10-release.conf' && /usr/bin/chmod 0700 '$REMOTE_STAGE/home_backend_release_bootstrap.py' && /usr/bin/chmod 0600 '$REMOTE_STAGE/10-release.conf' && /usr/bin/python3 '$REMOTE_STAGE/home_backend_release_bootstrap.py' --source-dropin '$REMOTE_STAGE/10-release.conf' --run-id '$RUN_ID' --apply" \
  </dev/null
