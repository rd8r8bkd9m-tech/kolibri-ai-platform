#!/usr/bin/env bash
# Safely publish one immutable release bundle into Home's root-only store.
# Default mode is read-only. Release activation always remains an API task.

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MANIFEST=""
BUNDLE=""
SSH_USER=root
RUN_ID="release-stage-$(date -u +%Y%m%dT%H%M%SZ)"
APPLY=false
REMOTE_TARGET=""
REMOTE_STAGE=""
STAGED=false

usage() {
  cat >&2 <<'EOF'
usage: scripts/stage-home-release-bundle.sh \
  --manifest FILE --bundle FILE [--ssh-user USER] [--run-id ID] [--apply]

Default mode validates the signed bundle metadata and performs a read-only
Home destination preflight. --apply immutably publishes the bundle but never
activates a release or submits a worker task.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest)
      MANIFEST=${2:?missing manifest path}
      shift 2
      ;;
    --bundle)
      BUNDLE=${2:?missing bundle path}
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
  echo "release_stage_manifest_invalid" >&2
  exit 2
}
[ -f "$BUNDLE" ] && [ ! -L "$BUNDLE" ] || {
  echo "release_stage_bundle_invalid" >&2
  exit 2
}
case "$SSH_USER" in
  ""|*[!A-Za-z0-9._-]*) echo "release_stage_ssh_user_invalid" >&2; exit 2 ;;
esac
case "$RUN_ID" in
  ""|*[!A-Za-z0-9._-]*) echo "release_stage_run_id_invalid" >&2; exit 2 ;;
esac
[ "${#RUN_ID}" -le 96 ] || {
  echo "release_stage_run_id_invalid" >&2
  exit 2
}

for command_name in python3 ssh scp; do
  command -v "$command_name" >/dev/null || {
    echo "release_stage_local_prerequisite_missing" >&2
    exit 2
  }
done

STAGER="$ROOT_DIR/ops/home_release_artifact_stager.py"
CONTROL_RESOLVER="$ROOT_DIR/ops/control_plane_endpoint.py"
for source in "$STAGER" "$CONTROL_RESOLVER"; do
  [ -f "$source" ] && [ ! -L "$source" ] || {
    echo "release_stage_source_invalid" >&2
    exit 2
  }
done

INSPECTION=$(PYTHONPATH="$ROOT_DIR" python3 "$STAGER" inspect --bundle "$BUNDLE") || {
  echo "release_stage_bundle_inspection_failed" >&2
  exit 2
}
ARTIFACT_RELATIVE=$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["artifact_relative"])' <<<"$INSPECTION")
BUNDLE_SHA256=$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["bundle_sha256"])' <<<"$INSPECTION")
BUNDLE_SIZE=$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["size_bytes"])' <<<"$INSPECTION")

case "$ARTIFACT_RELATIVE" in
  bundles/*) ;;
  *) echo "release_stage_artifact_relative_invalid" >&2; exit 2 ;;
esac
case "$ARTIFACT_RELATIVE" in
  *[!A-Za-z0-9._/-]*) echo "release_stage_artifact_relative_invalid" >&2; exit 2 ;;
esac
case "$BUNDLE_SHA256" in
  *[!0-9a-f]*|"") echo "release_stage_digest_invalid" >&2; exit 2 ;;
esac
case "$BUNDLE_SIZE" in
  *[!0-9]*|"") echo "release_stage_size_invalid" >&2; exit 2 ;;
esac

HOME_URL=$(PYTHONPATH="$ROOT_DIR" python3 "$CONTROL_RESOLVER" --print-url --manifest "$MANIFEST")
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
# Home's SSH daemon intentionally serves the legacy SCP transport but does not
# expose the SFTP subsystem.  Force that transport explicitly so artifact
# staging behaves the same way as the audited release-authority bootstrap.
SCP_OPTIONS=(-O "${SSH_OPTIONS[@]}")

if ! ssh "${SSH_OPTIONS[@]}" "$REMOTE_TARGET" \
  /usr/sbin/ip -4 -o addr show 2>/dev/null |
  python3 -c \
    'import ipaddress,sys; expected=str(ipaddress.ip_address(sys.argv[1])); values={field.split("/",1)[0] for line in sys.stdin for field in line.split() if "/" in field}; raise SystemExit(0 if expected in values else 1)' \
    "$HOME_HOST"; then
  echo "release_stage_target_not_home" >&2
  exit 1
fi

ssh "${SSH_OPTIONS[@]}" "$REMOTE_TARGET" \
  'test "$(id -u)" = 0 && test -x /usr/bin/python3 && test -d /var/lib/kolibri-release/artifacts' \
  </dev/null || {
    echo "release_stage_remote_prerequisite_missing" >&2
    exit 1
  }

if [ "$APPLY" != true ]; then
  ssh "${SSH_OPTIONS[@]}" "$REMOTE_TARGET" \
    /usr/bin/env PYTHONPATH=/usr/local/lib/kolibri /usr/bin/python3 - stage \
    --artifact-relative "$ARTIFACT_RELATIVE" \
    --expected-sha256 "$BUNDLE_SHA256" \
    --expected-size "$BUNDLE_SIZE" \
    <"$STAGER"
  exit $?
fi

REMOTE_STAGE="/tmp/kolibri-release-stage-$RUN_ID"
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
scp -q "${SCP_OPTIONS[@]}" "$BUNDLE" "$REMOTE_TARGET:$REMOTE_STAGE/bundle.tar.gz"
scp -q "${SCP_OPTIONS[@]}" "$STAGER" "$REMOTE_TARGET:$REMOTE_STAGE/stager.py"

ssh "${SSH_OPTIONS[@]}" "$REMOTE_TARGET" \
  "/usr/bin/chown root:root '$REMOTE_STAGE/bundle.tar.gz' '$REMOTE_STAGE/stager.py' && /usr/bin/chmod 0600 '$REMOTE_STAGE/bundle.tar.gz' && /usr/bin/chmod 0700 '$REMOTE_STAGE/stager.py' && PYTHONPATH=/usr/local/lib/kolibri /usr/bin/python3 '$REMOTE_STAGE/stager.py' stage --source '$REMOTE_STAGE/bundle.tar.gz' --artifact-relative '$ARTIFACT_RELATIVE' --expected-sha256 '$BUNDLE_SHA256' --expected-size '$BUNDLE_SIZE' --apply" \
  </dev/null
