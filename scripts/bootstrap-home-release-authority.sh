#!/usr/bin/env bash
# Owner-operated, one-time Home release authority bootstrap.
#
# This wrapper is read-only unless --apply is explicit.  It discovers Home
# from the replicated mesh manifest, stages only public trust/runtime files,
# and delegates the transactional host mutation to the audited Python helper.

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MANIFEST=""
SIGNER_PUBLIC_KEY=""
SIGNER_IDENTITY=""
SSH_USER=root
APPLY=false
RUN_ID="release-authority-$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_STAGE=""
REMOTE_TARGET=""
STAGED=false

usage() {
  cat >&2 <<'EOF'
usage: scripts/bootstrap-home-release-authority.sh \
  --manifest FILE \
  --signer-public-key FILE \
  --signer-identity ID \
  [--ssh-user USER] [--run-id ID] [--apply]

Default mode is a read-only dry-run.  --apply performs the one-time,
transactional bootstrap on the unique Home member resolved from FILE.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest)
      MANIFEST=${2:?missing manifest path}
      shift 2
      ;;
    --signer-public-key)
      SIGNER_PUBLIC_KEY=${2:?missing public key path}
      shift 2
      ;;
    --signer-identity)
      SIGNER_IDENTITY=${2:?missing signer identity}
      shift 2
      ;;
    --ssh-user)
      SSH_USER=${2:?missing SSH user}
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
  echo "release_authority_manifest_invalid" >&2
  exit 2
}
[ -f "$SIGNER_PUBLIC_KEY" ] && [ ! -L "$SIGNER_PUBLIC_KEY" ] || {
  echo "signer_public_key_invalid" >&2
  exit 2
}
case "$SIGNER_IDENTITY" in
  ""|*[!A-Za-z0-9@._:+-]*) echo "signer_identity_invalid" >&2; exit 2 ;;
esac
case "$SSH_USER" in
  ""|*[!A-Za-z0-9._-]*) echo "ssh_user_invalid" >&2; exit 2 ;;
esac
case "$RUN_ID" in
  ""|*[!A-Za-z0-9._-]*) echo "release_authority_run_id_invalid" >&2; exit 2 ;;
esac

for command_name in python3 ssh scp ssh-keygen; do
  command -v "$command_name" >/dev/null || {
    echo "release_authority_local_prerequisite_missing" >&2
    exit 2
  }
done

[ "${#SIGNER_IDENTITY}" -le 128 ] || {
  echo "signer_identity_invalid" >&2
  exit 2
}
[ "${#RUN_ID}" -le 96 ] || {
  echo "release_authority_run_id_invalid" >&2
  exit 2
}
ssh-keygen -lf "$SIGNER_PUBLIC_KEY" >/dev/null 2>&1 || {
  echo "signer_public_key_invalid" >&2
  exit 2
}

for source in \
  ops/control_plane_endpoint.py \
  ops/fleet_membership.py \
  ops/home_control_plane_canary.py \
  ops/home_control_plane_launcher.py \
  ops/home_release_authority_bootstrap.py \
  ops/home_release_authority_preflight.py \
  ops/release_authority.py \
  ops/release_helper.py \
  ops/release_installer.py \
  ops/release-policy.home.json \
  ops/systemd/kolibri-release-helper.service \
  ops/systemd/kolibri-release-helper.socket \
  ops/systemd/kolibri-factory-control-immutable-release.conf; do
  [ -f "$ROOT_DIR/$source" ] && [ ! -L "$ROOT_DIR/$source" ] || {
    echo "release_authority_source_invalid" >&2
    exit 2
  }
done

# Validate and fingerprint public material without ever writing the key body to
# stdout/stderr.  The digest is safe evidence; the allowed-signers row is not.
if ! SIGNER_DIGEST=$(
  PYTHONPATH="$ROOT_DIR" python3 -c \
    'import sys; from pathlib import Path; from ops.home_release_authority_bootstrap import normalize_public_signer; print(normalize_public_signer(Path(sys.argv[1]), sys.argv[2]).digest)' \
    "$SIGNER_PUBLIC_KEY" "$SIGNER_IDENTITY" 2>/dev/null
); then
  echo "signer_public_key_or_identity_invalid" >&2
  exit 2
fi

HOME_URL=$(
  PYTHONPATH="$ROOT_DIR" python3 "$ROOT_DIR/ops/control_plane_endpoint.py" \
    --print-url --manifest "$MANIFEST"
)
HOME_HOST=$(
  python3 -c \
    'import ipaddress,sys,urllib.parse; host=urllib.parse.urlsplit(sys.argv[1]).hostname or ""; value=ipaddress.ip_address(host); assert value.version == 4 and value.is_private and not value.is_loopback; print(value)' \
    "$HOME_URL"
)
REMOTE_TARGET="$SSH_USER@$HOME_HOST"

SSH_OPTIONS=(
  -o BatchMode=yes
  -o ConnectTimeout=8
  -o ConnectionAttempts=1
  -o ServerAliveInterval=5
  -o ServerAliveCountMax=2
)

# Read-only remote identity proof: the manifest-selected address must actually
# be assigned to this host.  Raw interface output is consumed locally and is
# never echoed.
if ! ssh "${SSH_OPTIONS[@]}" "$REMOTE_TARGET" \
  /usr/sbin/ip -4 -o addr show 2>/dev/null |
  python3 -c \
    'import ipaddress,sys; expected=str(ipaddress.ip_address(sys.argv[1])); values={field.split("/",1)[0] for line in sys.stdin for field in line.split() if "/" in field}; raise SystemExit(0 if expected in values else 1)' \
    "$HOME_HOST"; then
  echo "release_authority_target_not_home" >&2
  exit 1
fi

ssh "${SSH_OPTIONS[@]}" "$REMOTE_TARGET" \
  'test "$(id -u)" = 0 && id kolibri-agent >/dev/null 2>&1 && test -x /usr/bin/python3 && test -x /usr/bin/systemctl && test -x /usr/bin/ssh-keygen && test -x /usr/sbin/runuser' \
  </dev/null || {
    echo "release_authority_remote_prerequisite_missing" >&2
    exit 1
  }

# Stream the read-only preflight over SSH.  No file is staged on Home in
# default mode, and only the public trust digest crosses argv.
ssh "${SSH_OPTIONS[@]}" "$REMOTE_TARGET" \
  /usr/bin/python3 - "$SIGNER_DIGEST" \
  <"$ROOT_DIR/ops/home_release_authority_preflight.py" \
  >/dev/null || {
    echo "release_authority_remote_preflight_failed" >&2
    exit 1
  }

if [ "$APPLY" != true ]; then
  printf '{"backend_release_dropin":"not_installed_by_this_bootstrap","mode":"dry-run","schema_version":"kolibri.home-release-authority-bootstrap.v1","signer_identity":"%s","signer_public_key_digest":"%s","status":"planned","target_node":"home"}\n' \
    "$SIGNER_IDENTITY" "$SIGNER_DIGEST"
  exit 0
fi

REMOTE_STAGE="/tmp/kolibri-release-authority-$RUN_ID"
cleanup() {
  if [ "$STAGED" = true ]; then
    ssh "${SSH_OPTIONS[@]}" "$REMOTE_TARGET" \
      "/bin/rm -rf -- '$REMOTE_STAGE'" </dev/null >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

ssh "${SSH_OPTIONS[@]}" "$REMOTE_TARGET" \
  "/usr/bin/install -d -o root -g root -m 0700 '$REMOTE_STAGE/ops/systemd'" \
  </dev/null
STAGED=true

scp -q "${SSH_OPTIONS[@]}" \
  "$ROOT_DIR/ops/home_release_authority_bootstrap.py" \
  "$ROOT_DIR/ops/control_plane_endpoint.py" \
  "$ROOT_DIR/ops/fleet_membership.py" \
  "$ROOT_DIR/ops/home_control_plane_canary.py" \
  "$ROOT_DIR/ops/home_control_plane_launcher.py" \
  "$ROOT_DIR/ops/release_authority.py" \
  "$ROOT_DIR/ops/release_helper.py" \
  "$ROOT_DIR/ops/release_installer.py" \
  "$ROOT_DIR/ops/release-policy.home.json" \
  "$REMOTE_TARGET:$REMOTE_STAGE/ops/"
scp -q "${SSH_OPTIONS[@]}" \
  "$ROOT_DIR/ops/systemd/kolibri-release-helper.service" \
  "$ROOT_DIR/ops/systemd/kolibri-release-helper.socket" \
  "$ROOT_DIR/ops/systemd/kolibri-factory-control-immutable-release.conf" \
  "$REMOTE_TARGET:$REMOTE_STAGE/ops/systemd/"
scp -q "${SSH_OPTIONS[@]}" \
  "$MANIFEST" "$REMOTE_TARGET:$REMOTE_STAGE/peers.json"
scp -q "${SSH_OPTIONS[@]}" \
  "$SIGNER_PUBLIC_KEY" "$REMOTE_TARGET:$REMOTE_STAGE/signer.pub"

ssh "${SSH_OPTIONS[@]}" "$REMOTE_TARGET" \
  "/usr/bin/chown -R root:root '$REMOTE_STAGE' && /usr/bin/chmod 0700 '$REMOTE_STAGE' && PYTHONPATH='$REMOTE_STAGE' /usr/bin/python3 '$REMOTE_STAGE/ops/home_release_authority_bootstrap.py' --source-root '$REMOTE_STAGE' --manifest '$REMOTE_STAGE/peers.json' --signer-public-key '$REMOTE_STAGE/signer.pub' --signer-identity '$SIGNER_IDENTITY' --run-id '$RUN_ID' --apply" \
  </dev/null
