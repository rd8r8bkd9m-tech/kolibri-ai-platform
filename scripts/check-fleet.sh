#!/usr/bin/env bash
# Read-only Mac/Home -> dynamic mesh SSH matrix. This script never changes
# routes, peers, host keys, services, or the active VPN.

set -euo pipefail

MANIFEST_PATH="${KOLIBRI_MESH_MEMBERSHIP_MANIFEST:-}"
MANIFEST_URL="${KOLIBRI_MESH_MANIFEST_URL:-}"
HOME_TARGET="${KOLIBRI_HOME_SSH_TARGET:-home}"
SSH_USER="${KOLIBRI_FLEET_SSH_USER:-root}"
EXPECTED_SERVERS="${KOLIBRI_EXPECTED_SERVERS:-21}"
TIMEOUT="${KOLIBRI_FLEET_PROBE_TIMEOUT:-6}"
PARALLEL="${KOLIBRI_FLEET_PROBE_PARALLEL:-8}"

usage() {
  echo "usage: $0 [--manifest FILE | --manifest-url URL] [--home SSH_TARGET] [--ssh-user USER] [--expect N]" >&2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST_PATH=${2:?missing manifest path}; shift 2 ;;
    --manifest-url) MANIFEST_URL=${2:?missing manifest URL}; shift 2 ;;
    --home) HOME_TARGET=${2:?missing Home SSH target}; shift 2 ;;
    --ssh-user) SSH_USER=${2:?missing SSH user}; shift 2 ;;
    --expect) EXPECTED_SERVERS=${2:?missing expected count}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done

case "$SSH_USER" in *[!A-Za-z0-9._-]*|'') echo "invalid SSH user" >&2; exit 2 ;; esac
case "$HOME_TARGET" in *[!A-Za-z0-9@._:-]*|'') echo "invalid Home SSH target" >&2; exit 2 ;; esac
for value in "$EXPECTED_SERVERS" "$TIMEOUT" "$PARALLEL"; do
  case "$value" in *[!0-9]*|'') echo "numeric option is invalid" >&2; exit 2 ;; esac
done
[ "$EXPECTED_SERVERS" -gt 0 ] && [ "$TIMEOUT" -gt 0 ] && [ "$PARALLEL" -gt 0 ] || {
  echo "numeric options must be positive" >&2
  exit 2
}

command -v jq >/dev/null || { echo "jq is required" >&2; exit 2; }
command -v ssh >/dev/null || { echo "ssh is required" >&2; exit 2; }

WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/kolibri-fleet-check.XXXXXX")
trap 'rm -rf "$WORK_DIR"' EXIT
MANIFEST="$WORK_DIR/peers.json"

if [ -n "$MANIFEST_PATH" ] && [ -n "$MANIFEST_URL" ]; then
  echo "choose exactly one manifest source" >&2
  exit 2
elif [ -n "$MANIFEST_PATH" ]; then
  [ -f "$MANIFEST_PATH" ] || { echo "manifest file is missing" >&2; exit 2; }
  cp "$MANIFEST_PATH" "$MANIFEST"
  SOURCE="file"
elif [ -n "$MANIFEST_URL" ]; then
  case "$MANIFEST_URL" in http://*|https://*) ;; *) echo "manifest URL must use HTTP(S)" >&2; exit 2 ;; esac
  curl --fail --silent --show-error --max-time "$TIMEOUT" "$MANIFEST_URL" -o "$MANIFEST"
  SOURCE="registry"
else
  echo "set --manifest/--manifest-url (or KOLIBRI_MESH_MEMBERSHIP_MANIFEST/KOLIBRI_MESH_MANIFEST_URL)" >&2
  exit 2
fi

jq -e '
  (.peers | type == "object") and
  ([.peers[] | .node_id] | all(type == "string" and length > 0)) and
  ([.peers[] | .mesh_ip] | all(test("^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$"))) and
  (([.peers[] | .node_id] | length) == ([.peers[] | .node_id] | unique | length)) and
  (([.peers[] | .mesh_ip] | length) == ([.peers[] | .mesh_ip] | unique | length))
' "$MANIFEST" >/dev/null || { echo "manifest validation failed" >&2; exit 2; }

jq -r '.peers[] | [.node_id, .mesh_ip] | @tsv' "$MANIFEST" | sort >"$WORK_DIR/nodes.tsv"
DISCOVERED=$(wc -l <"$WORK_DIR/nodes.tsv" | tr -d ' ')
if [ "$DISCOVERED" -ne "$EXPECTED_SERVERS" ]; then
  echo "dynamic manifest contains $DISCOVERED servers; expected $EXPECTED_SERVERS" >&2
  exit 3
fi

probe_node() {
  local node_id=$1
  local mesh_ip=$2
  local safe_id=${node_id//[^A-Za-z0-9._-]/_}
  local mac=false
  local home=false

  if ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" -o ConnectionAttempts=1 \
    "$SSH_USER@$mesh_ip" true </dev/null >/dev/null 2>&1; then
    mac=true
  fi
  if [ "$node_id" = home ]; then
    # Home's self-cell proves operator reachability to Home. Requiring Home to
    # SSH back into its own mesh address falsely depends on a root loopback key.
    if ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" -o ConnectionAttempts=1 \
      "$HOME_TARGET" true </dev/null >/dev/null 2>&1; then
      home=true
    fi
  elif ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" -o ConnectionAttempts=1 \
    "$HOME_TARGET" ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" \
    -o ConnectionAttempts=1 "$SSH_USER@$mesh_ip" true \
    </dev/null >/dev/null 2>&1; then
    home=true
  fi
  jq -n \
    --arg node_id "$node_id" \
    --arg mesh_ip "$mesh_ip" \
    --argjson mac "$mac" \
    --argjson home "$home" \
    '{node_id:$node_id,mesh_ip:$mesh_ip,mac_ssh:$mac,home_ssh:$home}' \
    >"$WORK_DIR/result-$safe_id.json"
}

running=0
while IFS=$'\t' read -r node_id mesh_ip; do
  probe_node "$node_id" "$mesh_ip" &
  running=$((running + 1))
  if [ "$running" -ge "$PARALLEL" ]; then
    wait -n || true
    running=$((running - 1))
  fi
done <"$WORK_DIR/nodes.tsv"
wait

jq -s \
  --arg source "$SOURCE" \
  --argjson expected "$EXPECTED_SERVERS" '
  sort_by(.node_id) as $matrix |
  {
    schema_version:"kolibri.fleet-connectivity.v1",
    manifest_source:$source,
    expected_servers:$expected,
    discovered_servers:($matrix|length),
    mac_ssh_ok:([$matrix[]|select(.mac_ssh)]|length),
    home_ssh_ok:([$matrix[]|select(.home_ssh)]|length),
    passed:(([$matrix[]|select(.mac_ssh)]|length)==$expected and ([$matrix[]|select(.home_ssh)]|length)==$expected),
    matrix:$matrix
  }
' "$WORK_DIR"/result-*.json

MAC_OK=$(jq -s '[.[]|select(.mac_ssh)]|length' "$WORK_DIR"/result-*.json)
HOME_OK=$(jq -s '[.[]|select(.home_ssh)]|length' "$WORK_DIR"/result-*.json)
[ "$MAC_OK" -eq "$EXPECTED_SERVERS" ] && [ "$HOME_OK" -eq "$EXPECTED_SERVERS" ]
