#!/usr/bin/env bash
# One-time, reversible convergence of the canonical Home Control Plane binary.
# Normal releases remain API-only after this bootstrap boundary is installed.

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MANIFEST=""
EXPECTED=21
APPLY=false
RUN_ID="home-control-$(date -u +%Y%m%dT%H%M%SZ)"

usage() {
  echo "usage: $0 --manifest FILE [--expect 21] [--apply]" >&2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST=${2:?missing manifest}; shift 2 ;;
    --expect) EXPECTED=${2:?missing expected count}; shift 2 ;;
    --apply) APPLY=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done

[ -f "$MANIFEST" ] || { echo "manifest is required" >&2; exit 2; }
case "$EXPECTED" in ''|*[!0-9]*) echo "invalid expected count" >&2; exit 2 ;; esac
command -v jq >/dev/null
command -v ssh >/dev/null
command -v scp >/dev/null

FILES=(
  ops/factory_control.py
  ops/fleet_membership.py
  ops/release_authority.py
  ops/telegram_superfactory.py
)
for file in "${FILES[@]}"; do
  [ -f "$ROOT_DIR/$file" ] || { echo "missing source: $file" >&2; exit 2; }
done

HOME_IP=$(jq -er --argjson expected "$EXPECTED" '
  select(.peers | type == "object") |
  select([.peers[] | .node_id] | length == $expected) |
  [.peers[] | select(.node_id == "home") | .mesh_ip] |
  select(length == 1) | .[0]
' "$MANIFEST") || { echo "canonical Home manifest validation failed" >&2; exit 2; }

ssh -o BatchMode=yes -o ConnectTimeout=8 "root@$HOME_IP" true </dev/null
ACTIVE=$(curl -fsS --max-time 10 "http://$HOME_IP:9101/v1/tasks?limit=1000" | jq '[
  ((.tasks // .items // .)[]) |
  select((.state // .status) == "leased" or
         (.state // .status) == "running" or
         (.state // .status) == "waiting_review" or
         (.state // .status) == "review")
] | length')
[ "$ACTIVE" -eq 0 ] || { echo "control plane has active fenced tasks" >&2; exit 3; }

printf 'run_id=%s\thome=%s\texpected=%s\tapply=%s\tactive_tasks=%s\n' \
  "$RUN_ID" "$HOME_IP" "$EXPECTED" "$APPLY" "$ACTIVE"
if [ "$APPLY" != true ]; then
  echo "dry_run_complete"
  exit 0
fi

REMOTE_STAGE="/tmp/kolibri-$RUN_ID"
ssh "root@$HOME_IP" "install -d -m700 '$REMOTE_STAGE'" </dev/null
scp -q \
  "$ROOT_DIR/ops/factory_control.py" \
  "$ROOT_DIR/ops/fleet_membership.py" \
  "$ROOT_DIR/ops/release_authority.py" \
  "$ROOT_DIR/ops/telegram_superfactory.py" \
  "root@$HOME_IP:$REMOTE_STAGE/"

ssh "root@$HOME_IP" /bin/bash -s -- "$RUN_ID" "$REMOTE_STAGE" "$EXPECTED" <<'REMOTE'
set -euo pipefail
run_id=$1
stage=$2
expected=$3
backup="/var/backups/kolibri/$run_id"
install -d -m700 "$backup" /usr/local/lib/kolibri

targets=(
  /usr/local/bin/kolibri-factory-control
  /usr/local/lib/kolibri/fleet_membership.py
  /usr/local/lib/kolibri/release_authority.py
  /usr/local/lib/kolibri/telegram_superfactory.py
)
for path in "${targets[@]}"; do
  if [ -e "$path" ]; then
    install -d -m700 "$backup$(dirname "$path")"
    cp -a "$path" "$backup$path"
    sha256sum "$path" >>"$backup/checksums.before"
  else
    printf '%s\n' "$path" >>"$backup/absent.before"
  fi
done

rollback() {
  set +e
  for path in "${targets[@]}"; do
    if [ -e "$backup$path" ]; then
      cp -a "$backup$path" "$path"
    elif grep -Fxq "$path" "$backup/absent.before" 2>/dev/null; then
      rm -f "$path"
    fi
  done
  systemctl restart kolibri-factory-control.service
  rm -rf "$stage"
  printf 'rolled_back\n' >"$backup/status"
}
trap rollback ERR INT TERM

PYTHONPATH="$stage" /usr/bin/python3 -m py_compile \
  "$stage/factory_control.py" \
  "$stage/fleet_membership.py" \
  "$stage/release_authority.py" \
  "$stage/telegram_superfactory.py"

install -m755 "$stage/factory_control.py" /usr/local/bin/kolibri-factory-control
install -m644 "$stage/fleet_membership.py" /usr/local/lib/kolibri/fleet_membership.py
install -m644 "$stage/release_authority.py" /usr/local/lib/kolibri/release_authority.py
install -m644 "$stage/telegram_superfactory.py" /usr/local/lib/kolibri/telegram_superfactory.py
systemctl restart kolibri-factory-control.service

for _attempt in $(seq 1 30); do
  curl -fsS --max-time 3 http://127.0.0.1:9101/health >/dev/null && break
  sleep 1
done
curl -fsS --max-time 5 http://127.0.0.1:9101/health >/dev/null

nodes=$(curl -fsS --max-time 10 "http://127.0.0.1:9101/v1/nodes?scope=active&limit=250")
jq -e --argjson expected "$expected" '
  (.nodes | length) == $expected and
  .membership.authority == "replicated_mesh_manifest" and
  .membership.canonical_total == $expected
' <<<"$nodes" >/dev/null

trap - ERR INT TERM
rm -rf "$stage"
printf 'applied\n' >"$backup/status"
printf 'home_control_plane_bootstrap=passed\n'
REMOTE

curl -fsS --max-time 10 "http://$HOME_IP:9101/v1/nodes?scope=active&limit=250" | jq -e \
  --argjson expected "$EXPECTED" '(.nodes | length) == $expected' >/dev/null
echo "bootstrap_complete run_id=$RUN_ID"
