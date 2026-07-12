#!/usr/bin/env bash
# Owner-operated, one-time worker release-authority compatibility bootstrap.
#
# Dry-run is the default. Membership comes only from the supplied replicated
# mesh manifest; Home is excluded by the Python planner. Apply stages public
# trust and audited helper sources, then converges deterministic 1/2/3/5/rest
# waves. It never installs or restarts Control Plane/backend services.

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MANIFEST=""
SIGNER_PUBLIC_KEY=""
SIGNER_IDENTITY=""
RELEASE_DIGEST=""
APPLY=false
CANARY_ONLY=false
RUN_ID="fleet-release-authority-$(date -u +%Y%m%dT%H%M%SZ)"
TARGETS_FILE=""

usage() {
  cat >&2 <<'EOF'
usage: scripts/bootstrap-fleet-worker-release-authority.sh \
  --manifest FILE \
  --release-digest sha256:HEX \
  --signer-public-key FILE \
  --signer-identity ID \
  [--run-id ID] [--canary-only] [--apply]

Default mode is a fleet-wide read-only preflight. --canary-only restricts the
selected dynamic plan to its digest-seeded first worker. --apply performs the
transactional worker-only bootstrap in progressive waves.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST=${2:?missing manifest}; shift 2 ;;
    --release-digest) RELEASE_DIGEST=${2:?missing release digest}; shift 2 ;;
    --signer-public-key) SIGNER_PUBLIC_KEY=${2:?missing signer public key}; shift 2 ;;
    --signer-identity) SIGNER_IDENTITY=${2:?missing signer identity}; shift 2 ;;
    --run-id) RUN_ID=${2:?missing run ID}; shift 2 ;;
    --canary-only) CANARY_ONLY=true; shift ;;
    --apply) APPLY=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done

[ -f "$MANIFEST" ] && [ ! -L "$MANIFEST" ] || {
  echo "worker_release_manifest_invalid" >&2
  exit 2
}
[ -f "$SIGNER_PUBLIC_KEY" ] && [ ! -L "$SIGNER_PUBLIC_KEY" ] || {
  echo "signer_public_key_invalid" >&2
  exit 2
}
case "$SIGNER_IDENTITY" in
  ""|*[!A-Za-z0-9@._:+-]*) echo "signer_identity_invalid" >&2; exit 2 ;;
esac
case "$RUN_ID" in
  ""|*[!A-Za-z0-9._-]*) echo "worker_release_run_id_invalid" >&2; exit 2 ;;
esac
[ "${#SIGNER_IDENTITY}" -le 128 ] || { echo "signer_identity_invalid" >&2; exit 2; }
[ "${#RUN_ID}" -le 96 ] || { echo "worker_release_run_id_invalid" >&2; exit 2; }

for command_name in python3 ssh scp ssh-keygen mktemp; do
  command -v "$command_name" >/dev/null || {
    echo "worker_release_local_prerequisite_missing" >&2
    exit 2
  }
done
ssh-keygen -lf "$SIGNER_PUBLIC_KEY" >/dev/null 2>&1 || {
  echo "signer_public_key_invalid" >&2
  exit 2
}

SOURCES=(
  ops/control_plane_endpoint.py
  ops/fleet_membership.py
  ops/home_release_authority_bootstrap.py
  ops/release_authority.py
  ops/release_helper.py
  ops/release_installer.py
  ops/worker_release_health.py
  ops/worker_release_authority_preflight.py
  ops/fleet_worker_release_authority_bootstrap.py
  ops/release-policy.worker.json
  ops/systemd/kolibri-release-helper.service
  ops/systemd/kolibri-release-helper.socket
)
for source in "${SOURCES[@]}"; do
  [ -f "$ROOT_DIR/$source" ] && [ ! -L "$ROOT_DIR/$source" ] || {
    echo "worker_release_source_invalid" >&2
    exit 2
  }
done

if ! SIGNER_DIGEST=$(
  PYTHONPATH="$ROOT_DIR" python3 -c \
    'import sys; from pathlib import Path; from ops.home_release_authority_bootstrap import normalize_public_signer; print(normalize_public_signer(Path(sys.argv[1]), sys.argv[2]).digest)' \
    "$SIGNER_PUBLIC_KEY" "$SIGNER_IDENTITY" 2>/dev/null
); then
  echo "signer_public_key_or_identity_invalid" >&2
  exit 2
fi

PLAN_ARGS=(
  plan
  --manifest "$MANIFEST"
  --release-digest "$RELEASE_DIGEST"
)
if [ "$CANARY_ONLY" = true ]; then
  PLAN_ARGS+=(--canary-only)
fi

PYTHONPATH="$ROOT_DIR" python3 \
  "$ROOT_DIR/ops/fleet_worker_release_authority_bootstrap.py" \
  "${PLAN_ARGS[@]}"

TARGETS_FILE=$(mktemp)
cleanup() {
  [ -z "$TARGETS_FILE" ] || rm -f -- "$TARGETS_FILE"
}
trap cleanup EXIT INT TERM
PYTHONPATH="$ROOT_DIR" python3 \
  "$ROOT_DIR/ops/fleet_worker_release_authority_bootstrap.py" \
  "${PLAN_ARGS[@]}" --format tsv >"$TARGETS_FILE"
[ -s "$TARGETS_FILE" ] || { echo "worker_release_plan_empty" >&2; exit 2; }

SSH_OPTIONS=(
  -o BatchMode=yes
  -o ConnectTimeout=8
  -o ConnectionAttempts=1
  -o ServerAliveInterval=5
  -o ServerAliveCountMax=2
)
SCP_OPTIONS=(-O "${SSH_OPTIONS[@]}")

preflight_target() {
  local wave=$1 node=$2 ip=$3
  ssh "${SSH_OPTIONS[@]}" "root@$ip" \
    'test "$(id -u)" = 0 && id kolibri-agent >/dev/null 2>&1 && test -x /usr/bin/python3 && test -x /usr/bin/systemctl && test -x /usr/bin/ssh-keygen && test -x /usr/sbin/runuser' \
    </dev/null || {
      echo "worker_release_remote_prerequisite_missing:$node" >&2
      return 1
    }
  ssh "${SSH_OPTIONS[@]}" "root@$ip" \
    /usr/bin/python3 - "$node" "$ip" "$SIGNER_DIGEST" \
    <"$ROOT_DIR/ops/worker_release_authority_preflight.py" \
    >/dev/null || {
      echo "worker_release_remote_preflight_failed:$node" >&2
      return 1
    }
  printf '{"mode":"read-only","node":"%s","status":"preflight_ok","wave":"%s"}\n' \
    "$node" "$wave"
}

while IFS=$'\t' read -r wave node ip; do
  preflight_target "$wave" "$node" "$ip"
done <"$TARGETS_FILE"

if [ "$APPLY" != true ]; then
  printf '{"mode":"dry-run","status":"planned","worker_mutations":0}\n'
  exit 0
fi

apply_target() {
  local wave=$1 node=$2 ip=$3
  local remote="/tmp/kolibri-worker-release-authority-$RUN_ID-$node"
  local staged=false
  cleanup_remote() {
    if [ "$staged" = true ]; then
      ssh "${SSH_OPTIONS[@]}" "root@$ip" \
        "/bin/rm -rf -- '$remote'" </dev/null >/dev/null 2>&1 || true
    fi
  }
  trap cleanup_remote RETURN

  ssh "${SSH_OPTIONS[@]}" "root@$ip" \
    "/usr/bin/install -d -o root -g root -m 0700 '$remote/ops/systemd'" \
    </dev/null
  staged=true
  scp -q "${SCP_OPTIONS[@]}" \
    "$ROOT_DIR/ops/control_plane_endpoint.py" \
    "$ROOT_DIR/ops/fleet_membership.py" \
    "$ROOT_DIR/ops/home_release_authority_bootstrap.py" \
    "$ROOT_DIR/ops/release_authority.py" \
    "$ROOT_DIR/ops/release_helper.py" \
    "$ROOT_DIR/ops/release_installer.py" \
    "$ROOT_DIR/ops/worker_release_health.py" \
    "$ROOT_DIR/ops/fleet_worker_release_authority_bootstrap.py" \
    "$ROOT_DIR/ops/release-policy.worker.json" \
    "root@$ip:$remote/ops/"
  scp -q "${SCP_OPTIONS[@]}" \
    "$ROOT_DIR/ops/systemd/kolibri-release-helper.service" \
    "$ROOT_DIR/ops/systemd/kolibri-release-helper.socket" \
    "root@$ip:$remote/ops/systemd/"
  scp -q "${SCP_OPTIONS[@]}" \
    "$MANIFEST" "root@$ip:$remote/peers.json"
  scp -q "${SCP_OPTIONS[@]}" \
    "$SIGNER_PUBLIC_KEY" "root@$ip:$remote/signer.pub"

  ssh "${SSH_OPTIONS[@]}" "root@$ip" \
    "/usr/bin/chown -R root:root '$remote' && /usr/bin/chmod 0700 '$remote' && PYTHONPATH='$remote' /usr/bin/python3 -B '$remote/ops/fleet_worker_release_authority_bootstrap.py' target --source-root '$remote' --manifest '$remote/peers.json' --target-node '$node' --signer-public-key '$remote/signer.pub' --signer-identity '$SIGNER_IDENTITY' --run-id '$RUN_ID' --apply" \
    </dev/null
  cleanup_remote
  trap - RETURN
  printf '{"node":"%s","status":"applied_or_converged","wave":"%s"}\n' \
    "$node" "$wave"
}

current_wave=""
while IFS=$'\t' read -r wave node ip; do
  if [ "$wave" != "$current_wave" ]; then
    current_wave=$wave
    printf '{"status":"wave_started","wave":"%s"}\n' "$wave"
  fi
  apply_target "$wave" "$node" "$ip"
done <"$TARGETS_FILE"

printf '{"backend_restarts":0,"control_plane_restarts":0,"status":"applied"}\n'
