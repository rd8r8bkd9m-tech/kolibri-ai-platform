#!/usr/bin/env bash
# Audit and converge the Telegram receiver/watchdog singleton from the dynamic
# mesh manifest. Dry-run is strictly read-only. --apply performs a fenced
# source -> Home handoff and retires notification producers outside Home.

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MANIFEST=""
HOME_TARGET=""
EXPECTED=21
APPLY=false
VERIFY_SECONDS=12
RUN_ID="home-singletons-$(date -u +%Y%m%dT%H%M%SZ)"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST=${2:?missing manifest}; shift 2 ;;
    --home-root) HOME_TARGET=${2:?missing Home target}; shift 2 ;;
    --expect) EXPECTED=${2:?missing expected count}; shift 2 ;;
    --verify-seconds) VERIFY_SECONDS=${2:?missing verification interval}; shift 2 ;;
    --apply) APPLY=true; shift ;;
    -h|--help)
      echo "usage: $0 --manifest FILE [--home-root TARGET] [--expect 21] [--verify-seconds 12] [--apply]" >&2
      exit 0
      ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[ -f "$MANIFEST" ] || { echo "manifest is required" >&2; exit 2; }
case "$EXPECTED" in *[!0-9]*|'') echo "expected count must be an integer" >&2; exit 2 ;; esac
case "$VERIFY_SECONDS" in *[!0-9]*|'') echo "verification interval must be an integer" >&2; exit 2 ;; esac

for file in \
  ops/factory_lease_watchdog.py \
  ops/control_plane_endpoint.py \
  ops/telegram_gateway.py \
  ops/telegram_superfactory.py \
  ops/telegram_failover_guard.py \
  ops/orchestrator_memory.py \
  ops/orchestrator_roster.py \
  ops/systemd/kolibri-factory-lease-watchdog.service \
  ops/systemd/kolibri-factory-lease-watchdog.timer \
  ops/systemd/kolibri-telegram-gateway.service; do
  [ -f "$ROOT_DIR/$file" ] || { echo "missing file: $file" >&2; exit 2; }
done

jq -e --argjson expected "$EXPECTED" '
  (.peers | type == "object") and
  ([.peers[] | .node_id] | length == $expected) and
  ([.peers[] | .node_id] | unique | length == $expected) and
  ([.peers[] | .mesh_ip] | unique | length == $expected) and
  ([.peers[] | select(.node_id == "home")] | length == 1) and
  (all(.peers[]; (.node_id | type == "string" and length > 0) and
                 (.mesh_ip | type == "string" and length > 0)))
' "$MANIFEST" >/dev/null || { echo "manifest validation failed" >&2; exit 2; }

HOME_IP=$(jq -er '[.peers[] | select(.node_id == "home") | .mesh_ip] | select(length == 1) | .[0]' "$MANIFEST")
if [ -z "$HOME_TARGET" ]; then
  HOME_TARGET="root@$HOME_IP"
fi

STAGE=$(mktemp -d "${TMPDIR:-/tmp}/kolibri-home-singletons.XXXXXX")
SECRET_STAGE="$STAGE/checkpoint"
umask 077
install -d -m700 "$SECRET_STAGE"
cleanup() {
  rm -rf "$STAGE"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

cp "$ROOT_DIR/ops/factory_lease_watchdog.py" "$STAGE/kolibri-factory-lease-watchdog"
cp "$ROOT_DIR/ops/control_plane_endpoint.py" "$STAGE/control_plane_endpoint.py"
cp "$ROOT_DIR/ops/telegram_gateway.py" "$STAGE/telegram_gateway.py"
cp "$ROOT_DIR/ops/telegram_superfactory.py" "$STAGE/telegram_superfactory.py"
cp "$ROOT_DIR/ops/telegram_failover_guard.py" "$STAGE/telegram_failover_guard.py"
cp "$ROOT_DIR/ops/orchestrator_memory.py" "$STAGE/orchestrator_memory.py"
cp "$ROOT_DIR/ops/orchestrator_roster.py" "$STAGE/orchestrator_roster.py"
cp "$ROOT_DIR/ops/systemd/kolibri-factory-lease-watchdog.service" "$STAGE/kolibri-factory-lease-watchdog.service"
cp "$ROOT_DIR/ops/systemd/kolibri-factory-lease-watchdog.timer" "$STAGE/kolibri-factory-lease-watchdog.timer"
cp "$ROOT_DIR/ops/systemd/kolibri-telegram-gateway.service" "$STAGE/kolibri-telegram-gateway.service"
jq -r '.peers[] | [.node_id,.mesh_ip] | @tsv' "$MANIFEST" | LC_ALL=C sort >"$STAGE/nodes.tsv"

SSH_CMD=()
SCP_CMD=()
PATH_KIND=""
REMOTE_TARGET=""

select_path() {
  local node=$1 ip=$2
  SSH_CMD=()
  SCP_CMD=()
  PATH_KIND=""
  REMOTE_TARGET=""
  if [ "$node" = home ]; then
    REMOTE_TARGET=$HOME_TARGET
    SSH_CMD=(ssh -o BatchMode=yes -o ConnectTimeout=8 -o ConnectionAttempts=1 "$REMOTE_TARGET")
    SCP_CMD=(scp -q -p)
    PATH_KIND=home-root
    "${SSH_CMD[@]}" true </dev/null >/dev/null 2>&1
    return
  fi
  if ssh -o BatchMode=yes -o ConnectTimeout=4 -o ConnectionAttempts=1 "root@$ip" true </dev/null >/dev/null 2>&1; then
    REMOTE_TARGET="root@$ip"
    SSH_CMD=(ssh -o BatchMode=yes -o ConnectTimeout=8 -o ConnectionAttempts=1 "$REMOTE_TARGET")
    SCP_CMD=(scp -q -p)
    PATH_KIND=direct
    return 0
  fi
  if ssh -o BatchMode=yes -o ConnectTimeout=4 -o ConnectionAttempts=1 -o ProxyJump="$HOME_TARGET" "root@$ip" true </dev/null >/dev/null 2>&1; then
    REMOTE_TARGET="root@$ip"
    SSH_CMD=(ssh -o BatchMode=yes -o ConnectTimeout=8 -o ConnectionAttempts=1 -o ProxyJump="$HOME_TARGET" "$REMOTE_TARGET")
    SCP_CMD=(scp -q -p -o ProxyJump="$HOME_TARGET")
    PATH_KIND=home-proxy
    return 0
  fi
  return 1
}

audit_node() {
  local node=$1 ip=$2
  "${SSH_CMD[@]}" /bin/bash -s -- "$node" "$ip" "$PATH_KIND" <<'REMOTE'
set -euo pipefail
node=$1
ip=$2
path_kind=$3

discover_notification_units() {
  {
    printf '%s\n' \
      kolibri-telegram-gateway.service \
      kolibri-factory-lease-watchdog.service \
      kolibri-factory-lease-watchdog.timer \
      kolibri-factory-cluster-monitor.service \
      kolibri-factory-cluster-monitor.timer
    systemctl list-unit-files --no-legend 2>/dev/null | awk '{print $1}' | while IFS= read -r unit; do
      case "$unit" in
        *kolibri*telegram*.service|*kolibri*telegram*.timer|\
        *factory*telegram*.service|*factory*telegram*.timer|\
        *gomesh*telegram*.service|*gomesh*telegram*.timer|\
        *kolibri*evidence*watch*.service|*kolibri*evidence*watch*.timer|\
        *gomesh*watch*.service|*gomesh*watch*.timer|\
        *gomesh*evidence*.service|*gomesh*evidence*.timer|\
        *gomesh*report*.service|*gomesh*report*.timer|\
        *gomesh*measurement*.service|*gomesh*measurement*.timer|\
        *gomesh*field-test*.service|*gomesh*field-test*.timer)
          printf '%s\n' "$unit"
          ;;
      esac
    done
  } | awk 'NF && !seen[$0]++'
}

gateway_enabled=$(systemctl is-enabled kolibri-telegram-gateway.service 2>/dev/null || true)
gateway_active=$(systemctl is-active kolibri-telegram-gateway.service 2>/dev/null || true)
gateway_processes=$(ps -eo args= 2>/dev/null | awk '
  /\/telegram_gateway\.py([[:space:]]|$)|\/usr\/local\/bin\/kolibri-telegram-gateway([[:space:]]|$)/ && $0 !~ /awk/ {n++}
  END {print n+0}
')
receiver_active=0
if [ "$gateway_active" = active ] || [ "$gateway_processes" -gt 0 ]; then
  receiver_active=1
fi
env_present=0
state_present=0
state_mtime=0
[ -s /etc/kolibri/telegram.env ] && env_present=1
if [ -s /var/lib/kolibri-telegram-gateway/state.json ]; then
  state_present=1
  state_mtime=$(stat -c '%Y' /var/lib/kolibri-telegram-gateway/state.json 2>/dev/null || echo 0)
fi
watchdog_enabled=$(systemctl is-enabled kolibri-factory-lease-watchdog.timer 2>/dev/null || true)
watchdog_active=$(systemctl is-active kolibri-factory-lease-watchdog.timer 2>/dev/null || true)
legacy_units=0
legacy_active=0
while IFS= read -r unit; do
  [ -n "$unit" ] || continue
  legacy_units=$((legacy_units + 1))
  [ "$(systemctl is-active "$unit" 2>/dev/null || true)" = active ] && legacy_active=$((legacy_active + 1))
done <<EOF
$(discover_notification_units)
EOF

# Only non-secret state is returned. Environment and state contents are never
# sourced, printed, grepped, or placed in argv.
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
  "$node" "$ip" "$path_kind" "${gateway_enabled:-missing}" "${gateway_active:-inactive}" \
  "$gateway_processes" "$receiver_active" "$env_present" "$state_present" "$state_mtime" \
  "${watchdog_enabled:-missing}" "${watchdog_active:-inactive}" "$legacy_units" "$legacy_active"
REMOTE
}

collect_audit() {
  local audit_file=$1 unreachable_file=$2
  : >"$audit_file"
  : >"$unreachable_file"
  while IFS=$'\t' read -r node ip; do
    [ -n "$node" ] || continue
    if ! select_path "$node" "$ip"; then
      printf '%s\t%s\n' "$node" "$ip" >>"$unreachable_file"
      continue
    fi
    if ! audit_node "$node" "$ip" >>"$audit_file"; then
      printf '%s\t%s\n' "$node" "$ip" >>"$unreachable_file"
    fi
  done <"$STAGE/nodes.tsv"
}

print_audit() {
  local audit_file=$1 unreachable_file=$2 phase=$3
  awk -F '\t' -v phase="$phase" '{
    printf "audit\t%s\t%s\t%s\t%s\tgateway=%s/%s\tprocesses=%s\treceiver=%s\tcredential=%s\tcheckpoint=%s\twatchdog=%s/%s\tlegacy=%s/%s\n",
      phase,$1,$2,$3,$4,$5,$6,$7,$8,$9,$11,$12,$13,$14
  }' "$audit_file"
  awk -F '\t' -v phase="$phase" '{printf "unreachable\t%s\t%s\t%s\n",phase,$1,$2}' "$unreachable_file"
  local reachable unreachable active
  reachable=$(awk 'END {print NR+0}' "$audit_file")
  unreachable=$(awk 'END {print NR+0}' "$unreachable_file")
  active=$(awk -F '\t' '$7 == 1 {n++} END {print n+0}' "$audit_file")
  printf 'summary\t%s\treachable=%s\tunreachable=%s\tactive_receivers=%s\n' "$phase" "$reachable" "$unreachable" "$active"
}

copy_home_runtime_bundle() {
  select_path home "$HOME_IP"
  "${SSH_CMD[@]}" "install -d -m700 '/tmp/$RUN_ID'"
  "${SCP_CMD[@]}" \
    "$STAGE"/kolibri-* \
    "$STAGE"/control_plane_endpoint.py \
    "$STAGE"/telegram_*.py \
    "$STAGE"/orchestrator_*.py \
    "$REMOTE_TARGET:/tmp/$RUN_ID/"
}

install_home_runtime() {
  select_path home "$HOME_IP"
  "${SSH_CMD[@]}" /bin/bash -s -- "$RUN_ID" <<'REMOTE'
set -euo pipefail
run_id=$1
stage=/tmp/$run_id
backup=/var/backups/kolibri/$run_id/home-runtime
install -d -m700 "$backup"

managed_paths='
/usr/local/bin/kolibri-factory-lease-watchdog
/usr/local/lib/kolibri/control_plane_endpoint.py
/usr/local/lib/kolibri/telegram_gateway.py
/usr/local/lib/kolibri/telegram_superfactory.py
/usr/local/lib/kolibri/telegram_failover_guard.py
/usr/local/lib/kolibri/orchestrator_memory.py
/usr/local/lib/kolibri/orchestrator_roster.py
/etc/systemd/system/kolibri-factory-lease-watchdog.service
/etc/systemd/system/kolibri-factory-lease-watchdog.timer
/etc/systemd/system/kolibri-factory-lease-watchdog.service.d
/etc/systemd/system/kolibri-telegram-gateway.service
/etc/systemd/system/kolibri-telegram-gateway.service.d'
printf '%s\n' "$managed_paths" | sed '/^$/d' >"$backup/managed-paths"
while IFS= read -r path; do
  [ -n "$path" ] || continue
  if [ -e "$path" ] || [ -L "$path" ]; then
    install -d -m700 "$backup$(dirname "$path")"
    cp -a "$path" "$backup$path"
  fi
done <"$backup/managed-paths"

systemctl unmask kolibri-telegram-gateway.service \
  kolibri-factory-lease-watchdog.service \
  kolibri-factory-lease-watchdog.timer 2>/dev/null || true
rm -rf /etc/systemd/system/kolibri-factory-lease-watchdog.service.d
rm -rf /etc/systemd/system/kolibri-telegram-gateway.service.d
install -d -m755 /usr/local/lib/kolibri
install -o root -g root -m755 "$stage/kolibri-factory-lease-watchdog" /usr/local/bin/kolibri-factory-lease-watchdog
install -o root -g root -m644 "$stage/control_plane_endpoint.py" /usr/local/lib/kolibri/control_plane_endpoint.py
install -o root -g root -m755 "$stage/telegram_gateway.py" /usr/local/lib/kolibri/telegram_gateway.py
install -o root -g root -m644 "$stage/telegram_superfactory.py" /usr/local/lib/kolibri/telegram_superfactory.py
install -o root -g root -m644 "$stage/telegram_failover_guard.py" /usr/local/lib/kolibri/telegram_failover_guard.py
install -o root -g root -m644 "$stage/orchestrator_memory.py" /usr/local/lib/kolibri/orchestrator_memory.py
install -o root -g root -m644 "$stage/orchestrator_roster.py" /usr/local/lib/kolibri/orchestrator_roster.py
install -o root -g root -m644 "$stage/kolibri-factory-lease-watchdog.service" /etc/systemd/system/kolibri-factory-lease-watchdog.service
install -o root -g root -m644 "$stage/kolibri-factory-lease-watchdog.timer" /etc/systemd/system/kolibri-factory-lease-watchdog.timer
install -o root -g root -m644 "$stage/kolibri-telegram-gateway.service" /etc/systemd/system/kolibri-telegram-gateway.service
python3 -m py_compile \
  /usr/local/bin/kolibri-factory-lease-watchdog \
  /usr/local/lib/kolibri/control_plane_endpoint.py \
  /usr/local/lib/kolibri/telegram_gateway.py \
  /usr/local/lib/kolibri/telegram_superfactory.py \
  /usr/local/lib/kolibri/telegram_failover_guard.py \
  /usr/local/lib/kolibri/orchestrator_memory.py \
  /usr/local/lib/kolibri/orchestrator_roster.py
systemctl daemon-reload
REMOTE
}

backup_home_checkpoint() {
  select_path home "$HOME_IP"
  "${SSH_CMD[@]}" /bin/bash -s -- "$RUN_ID" <<'REMOTE'
set -euo pipefail
run_id=$1
backup=/var/backups/kolibri/$run_id/home-checkpoint
install -d -m700 "$backup"
for path in /etc/kolibri/telegram.env /var/lib/kolibri-telegram-gateway; do
  if [ -e "$path" ] || [ -L "$path" ]; then
    install -d -m700 "$backup$(dirname "$path")"
    cp -a "$path" "$backup$path"
  fi
done
REMOTE
}

stop_source_receiver() {
  local node=$1 ip=$2
  select_path "$node" "$ip"
  "${SSH_CMD[@]}" /bin/bash -s <<'REMOTE'
set -euo pipefail
systemctl stop kolibri-telegram-gateway.service
attempt=0
while [ "$attempt" -lt 30 ]; do
  active=$(systemctl is-active kolibri-telegram-gateway.service 2>/dev/null || true)
  processes=$(ps -eo args= 2>/dev/null | awk '
    /\/telegram_gateway\.py([[:space:]]|$)|\/usr\/local\/bin\/kolibri-telegram-gateway([[:space:]]|$)/ && $0 !~ /awk/ {n++}
    END {print n+0}
  ')
  if [ "$active" != active ] && [ "$processes" -eq 0 ]; then
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 1
done
echo "source receiver did not stop cleanly" >&2
exit 1
REMOTE
}

copy_source_checkpoint() {
  local node=$1 ip=$2
  select_path "$node" "$ip"
  "${SCP_CMD[@]}" "$REMOTE_TARGET:/etc/kolibri/telegram.env" "$SECRET_STAGE/telegram.env"
  "${SCP_CMD[@]}" "$REMOTE_TARGET:/var/lib/kolibri-telegram-gateway/state.json" "$SECRET_STAGE/state.json"
  if "${SSH_CMD[@]}" test -s /var/lib/kolibri-telegram-gateway/failover.json; then
    "${SCP_CMD[@]}" "$REMOTE_TARGET:/var/lib/kolibri-telegram-gateway/failover.json" "$SECRET_STAGE/failover.json"
  fi
  chmod 600 "$SECRET_STAGE/telegram.env" "$SECRET_STAGE/state.json"
  [ -s "$SECRET_STAGE/telegram.env" ]
  [ -s "$SECRET_STAGE/state.json" ]
}

install_checkpoint_on_home() {
  select_path home "$HOME_IP"
  "${SSH_CMD[@]}" "install -d -m700 '/tmp/$RUN_ID/checkpoint'"
  "${SCP_CMD[@]}" "$SECRET_STAGE/telegram.env" "$SECRET_STAGE/state.json" "$REMOTE_TARGET:/tmp/$RUN_ID/checkpoint/"
  if [ -s "$SECRET_STAGE/failover.json" ]; then
    "${SCP_CMD[@]}" "$SECRET_STAGE/failover.json" "$REMOTE_TARGET:/tmp/$RUN_ID/checkpoint/"
  fi
  "${SSH_CMD[@]}" /bin/bash -s -- "$RUN_ID" <<'REMOTE'
set -euo pipefail
run_id=$1
stage=/tmp/$run_id/checkpoint
getent group kolibri >/dev/null
getent passwd kolibri >/dev/null
install -d -o root -g kolibri -m750 /etc/kolibri
install -o root -g kolibri -m640 "$stage/telegram.env" /etc/kolibri/telegram.env.new
mv -f /etc/kolibri/telegram.env.new /etc/kolibri/telegram.env
install -d -o kolibri -g kolibri -m700 /var/lib/kolibri-telegram-gateway
install -o kolibri -g kolibri -m600 "$stage/state.json" /var/lib/kolibri-telegram-gateway/state.json.new
mv -f /var/lib/kolibri-telegram-gateway/state.json.new /var/lib/kolibri-telegram-gateway/state.json
if [ -s "$stage/failover.json" ]; then
  install -o kolibri -g kolibri -m600 "$stage/failover.json" /var/lib/kolibri-telegram-gateway/failover.json.new
  mv -f /var/lib/kolibri-telegram-gateway/failover.json.new /var/lib/kolibri-telegram-gateway/failover.json
fi
rm -rf "$stage"
REMOTE
}

normalize_home_checkpoint() {
  select_path home "$HOME_IP"
  "${SSH_CMD[@]}" /bin/bash -s <<'REMOTE'
set -euo pipefail
[ -s /etc/kolibri/telegram.env ]
[ -s /var/lib/kolibri-telegram-gateway/state.json ]
getent group kolibri >/dev/null
getent passwd kolibri >/dev/null
chown root:kolibri /etc/kolibri/telegram.env
chmod 640 /etc/kolibri/telegram.env
chown -R kolibri:kolibri /var/lib/kolibri-telegram-gateway
chmod 700 /var/lib/kolibri-telegram-gateway
chmod 600 /var/lib/kolibri-telegram-gateway/state.json
REMOTE
}

start_and_verify_home_receiver() {
  select_path home "$HOME_IP"
  "${SSH_CMD[@]}" /bin/bash -s -- "$VERIFY_SECONDS" <<'REMOTE'
set -euo pipefail
verify_seconds=$1
systemctl unmask kolibri-telegram-gateway.service
systemctl daemon-reload
started_at=$(date +%s)
systemctl enable kolibri-telegram-gateway.service >/dev/null
systemctl restart kolibri-telegram-gateway.service
sleep "$verify_seconds"
[ "$(systemctl is-active kolibri-telegram-gateway.service 2>/dev/null || true)" = active ]
main_pid=$(systemctl show kolibri-telegram-gateway.service -p MainPID --value 2>/dev/null || echo 0)
[ "${main_pid:-0}" -gt 1 ]
if journalctl -u kolibri-telegram-gateway.service --since "@$started_at" --no-pager 2>/dev/null | grep -Eqi \
  'telegram_gateway_error|HA guard rejected|refused to start polling|Traceback|status=1/FAILURE|Start request repeated too quickly'; then
  echo "Home receiver emitted a startup error" >&2
  exit 1
fi
REMOTE
}

enable_home_watchdog() {
  select_path home "$HOME_IP"
  "${SSH_CMD[@]}" /bin/bash -s <<'REMOTE'
set -euo pipefail
systemctl unmask kolibri-factory-lease-watchdog.service kolibri-factory-lease-watchdog.timer
systemctl daemon-reload
systemctl enable --now kolibri-factory-lease-watchdog.timer >/dev/null
[ "$(systemctl is-enabled kolibri-factory-lease-watchdog.timer 2>/dev/null || true)" = enabled ]
[ "$(systemctl is-active kolibri-factory-lease-watchdog.timer 2>/dev/null || true)" = active ]
REMOTE
}

restart_source_receiver() {
  local node=$1 ip=$2
  select_path "$node" "$ip"
  "${SSH_CMD[@]}" /bin/bash -s -- "$VERIFY_SECONDS" <<'REMOTE'
set -euo pipefail
verify_seconds=$1
systemctl start kolibri-telegram-gateway.service
sleep "$verify_seconds"
[ "$(systemctl is-active kolibri-telegram-gateway.service 2>/dev/null || true)" = active ]
REMOTE
}

rollback_home() {
  select_path home "$HOME_IP"
  "${SSH_CMD[@]}" /bin/bash -s -- "$RUN_ID" <<'REMOTE'
set -euo pipefail
run_id=$1
runtime=/var/backups/kolibri/$run_id/home-runtime
checkpoint=/var/backups/kolibri/$run_id/home-checkpoint
systemctl stop kolibri-telegram-gateway.service 2>/dev/null || true

if [ -f "$runtime/managed-paths" ]; then
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    rm -rf "$path"
    if [ -e "$runtime$path" ] || [ -L "$runtime$path" ]; then
      install -d -m755 "$(dirname "$path")"
      cp -a "$runtime$path" "$path"
    fi
  done <"$runtime/managed-paths"
fi
for path in /etc/kolibri/telegram.env /var/lib/kolibri-telegram-gateway; do
  rm -rf "$path"
  if [ -e "$checkpoint$path" ] || [ -L "$checkpoint$path" ]; then
    install -d -m755 "$(dirname "$path")"
    cp -a "$checkpoint$path" "$path"
  fi
done
systemctl daemon-reload
REMOTE
}

retire_nonhome_notifications() {
  local node=$1 ip=$2
  select_path "$node" "$ip"
  "${SSH_CMD[@]}" /bin/bash -s -- "$RUN_ID" <<'REMOTE'
set -euo pipefail
run_id=$1
backup=/var/backups/kolibri/$run_id/retired-notification-units
install -d -m700 "$backup"

discover_notification_units() {
  {
    printf '%s\n' \
      kolibri-telegram-gateway.service \
      kolibri-factory-lease-watchdog.service \
      kolibri-factory-lease-watchdog.timer \
      kolibri-factory-cluster-monitor.service \
      kolibri-factory-cluster-monitor.timer
    systemctl list-unit-files --no-legend 2>/dev/null | awk '{print $1}' | while IFS= read -r unit; do
      case "$unit" in
        *kolibri*telegram*.service|*kolibri*telegram*.timer|\
        *factory*telegram*.service|*factory*telegram*.timer|\
        *gomesh*telegram*.service|*gomesh*telegram*.timer|\
        *kolibri*evidence*watch*.service|*kolibri*evidence*watch*.timer|\
        *gomesh*watch*.service|*gomesh*watch*.timer|\
        *gomesh*evidence*.service|*gomesh*evidence*.timer|\
        *gomesh*report*.service|*gomesh*report*.timer|\
        *gomesh*measurement*.service|*gomesh*measurement*.timer|\
        *gomesh*field-test*.service|*gomesh*field-test*.timer)
          printf '%s\n' "$unit"
          ;;
      esac
    done
  } | awk 'NF && !seen[$0]++'
}

while IFS= read -r unit; do
  [ -n "$unit" ] || continue
  systemctl disable --now "$unit" >/dev/null 2>&1 || true
  fragment=$(systemctl show "$unit" -p FragmentPath --value 2>/dev/null || true)
  if [ -n "$fragment" ] && [ "$fragment" = "/etc/systemd/system/$unit" ] && [ ! -L "$fragment" ]; then
    cp -a "$fragment" "$backup/$unit"
    rm -f "$fragment"
  fi
  rm -f "/etc/systemd/system/$unit"
  ln -s /dev/null "/etc/systemd/system/$unit"
done <<EOF
$(discover_notification_units)
EOF
systemctl daemon-reload

while IFS= read -r unit; do
  [ -n "$unit" ] || continue
  enabled=$(systemctl is-enabled "$unit" 2>/dev/null || true)
  active=$(systemctl is-active "$unit" 2>/dev/null || true)
  case "$enabled" in masked|masked-runtime) ;; *) echo "$unit is not masked" >&2; exit 1 ;; esac
  [ "$active" != active ] || { echo "$unit is still active" >&2; exit 1; }
done <<EOF
$(discover_notification_units)
EOF
REMOTE
}

INITIAL_AUDIT="$STAGE/audit-initial.tsv"
INITIAL_UNREACHABLE="$STAGE/unreachable-initial.tsv"
collect_audit "$INITIAL_AUDIT" "$INITIAL_UNREACHABLE"
print_audit "$INITIAL_AUDIT" "$INITIAL_UNREACHABLE" initial

unreachable_count=$(awk 'END {print NR+0}' "$INITIAL_UNREACHABLE")
active_receivers=$(awk -F '\t' '$7 == 1 {n++} END {print n+0}' "$INITIAL_AUDIT")

if [ "$APPLY" != true ]; then
  [ "$unreachable_count" -eq 0 ] || exit 1
  [ "$active_receivers" -le 1 ] || { echo "singleton_violation active_receivers=$active_receivers" >&2; exit 1; }
  exit 0
fi

# A node that was not audited could already be polling. Starting Home in that
# state would risk two Telegram consumers, so apply fails closed before the
# first remote mutation while preserving a truthful unreachable record.
if [ "$unreachable_count" -ne 0 ]; then
  echo "apply_blocked reason=incomplete_inventory unreachable=$unreachable_count" >&2
  exit 1
fi
if [ "$active_receivers" -gt 1 ]; then
  echo "apply_blocked reason=multiple_active_receivers count=$active_receivers" >&2
  exit 1
fi

SOURCE_NODE=""
if [ "$active_receivers" -eq 1 ]; then
  SOURCE_NODE=$(awk -F '\t' '$7 == 1 {print $1; exit}' "$INITIAL_AUDIT")
else
  SOURCE_NODE=$(awk -F '\t' '$1 == "home" && $8 == 1 && $9 == 1 {print $1; exit}' "$INITIAL_AUDIT")
  if [ -z "$SOURCE_NODE" ]; then
    ready_count=$(awk -F '\t' '$8 == 1 && $9 == 1 {n++} END {print n+0}' "$INITIAL_AUDIT")
    if [ "$ready_count" -eq 1 ]; then
      SOURCE_NODE=$(awk -F '\t' '$8 == 1 && $9 == 1 {print $1; exit}' "$INITIAL_AUDIT")
    fi
  fi
fi

if [ -z "$SOURCE_NODE" ]; then
  echo "apply_blocked reason=no_unambiguous_credential_checkpoint_source" >&2
  exit 1
fi
SOURCE_ROW=$(awk -F '\t' -v node="$SOURCE_NODE" '$1 == node {print; exit}' "$INITIAL_AUDIT")
SOURCE_IP=$(printf '%s\n' "$SOURCE_ROW" | awk -F '\t' '{print $2}')
SOURCE_ACTIVE=$(printf '%s\n' "$SOURCE_ROW" | awk -F '\t' '{print $7}')
SOURCE_ENV=$(printf '%s\n' "$SOURCE_ROW" | awk -F '\t' '{print $8}')
SOURCE_STATE=$(printf '%s\n' "$SOURCE_ROW" | awk -F '\t' '{print $9}')
SOURCE_SERVICE=$(printf '%s\n' "$SOURCE_ROW" | awk -F '\t' '{print $5}')
if [ "$SOURCE_ENV" -ne 1 ] || [ "$SOURCE_STATE" -ne 1 ]; then
  echo "apply_blocked reason=source_checkpoint_incomplete source=$SOURCE_NODE" >&2
  exit 1
fi
if [ "$SOURCE_ACTIVE" -eq 1 ] && [ "$SOURCE_SERVICE" != active ]; then
  echo "apply_blocked reason=unmanaged_active_receiver source=$SOURCE_NODE" >&2
  exit 1
fi

printf 'handoff\tsource=%s\ttarget=home\twas_active=%s\n' "$SOURCE_NODE" "$SOURCE_ACTIVE"
copy_home_runtime_bundle
install_home_runtime
backup_home_checkpoint

handoff_ok=false
if [ "$SOURCE_NODE" != home ]; then
  if [ "$SOURCE_ACTIVE" -eq 1 ]; then
    if ! stop_source_receiver "$SOURCE_NODE" "$SOURCE_IP"; then
      rollback_home || true
      echo "handoff_failed reason=source_stop_failed source=$SOURCE_NODE" >&2
      exit 1
    fi
  fi
  if ! copy_source_checkpoint "$SOURCE_NODE" "$SOURCE_IP" || ! install_checkpoint_on_home; then
    rollback_home || true
    if [ "$SOURCE_ACTIVE" -eq 1 ]; then restart_source_receiver "$SOURCE_NODE" "$SOURCE_IP" || true; fi
    echo "handoff_failed reason=checkpoint_transfer_failed source=$SOURCE_NODE" >&2
    exit 1
  fi
else
  normalize_home_checkpoint
fi

if start_and_verify_home_receiver; then
  VERIFY_AUDIT="$STAGE/audit-handoff.tsv"
  VERIFY_UNREACHABLE="$STAGE/unreachable-handoff.tsv"
  collect_audit "$VERIFY_AUDIT" "$VERIFY_UNREACHABLE"
  verify_unreachable=$(awk 'END {print NR+0}' "$VERIFY_UNREACHABLE")
  verify_active=$(awk -F '\t' '$7 == 1 {n++} END {print n+0}' "$VERIFY_AUDIT")
  verify_home=$(awk -F '\t' '$1 == "home" && $7 == 1 {n++} END {print n+0}' "$VERIFY_AUDIT")
  if [ "$verify_unreachable" -eq 0 ] && [ "$verify_active" -eq 1 ] && [ "$verify_home" -eq 1 ]; then
    handoff_ok=true
  fi
fi

if [ "$handoff_ok" != true ]; then
  rollback_home || true
  if [ "$SOURCE_NODE" = home ] && [ "$SOURCE_ACTIVE" -eq 1 ]; then
    restart_source_receiver home "$HOME_IP" || true
  elif [ "$SOURCE_ACTIVE" -eq 1 ]; then
    restart_source_receiver "$SOURCE_NODE" "$SOURCE_IP" || true
  fi
  echo "handoff_failed reason=home_receiver_verification_failed source=$SOURCE_NODE" >&2
  exit 1
fi

# Retire the former source first. If this fence cannot be made durable, restore
# the previous receiver rather than leaving two reboot-enabled consumers.
if [ "$SOURCE_NODE" != home ]; then
  if ! retire_nonhome_notifications "$SOURCE_NODE" "$SOURCE_IP"; then
    # Home is already the sole verified live receiver. Do not reactivate the
    # old source after a partial mask operation; keep it stopped and report the
    # incomplete retirement truthfully.
    stop_source_receiver "$SOURCE_NODE" "$SOURCE_IP" || true
    printf 'retirement_failed\t%s\t%s\n' "$SOURCE_NODE" "$SOURCE_IP" >&2
    retire_failures=1
  else
    retire_failures=0
  fi
else
  retire_failures=0
fi

while IFS=$'\t' read -r node ip; do
  [ -n "$node" ] || continue
  [ "$node" = home ] && continue
  [ "$node" = "$SOURCE_NODE" ] && continue
  if ! retire_nonhome_notifications "$node" "$ip"; then
    printf 'retirement_failed\t%s\t%s\n' "$node" "$ip" >&2
    retire_failures=$((retire_failures + 1))
  fi
done <"$STAGE/nodes.tsv"

enable_home_watchdog

FINAL_AUDIT="$STAGE/audit-final.tsv"
FINAL_UNREACHABLE="$STAGE/unreachable-final.tsv"
collect_audit "$FINAL_AUDIT" "$FINAL_UNREACHABLE"
print_audit "$FINAL_AUDIT" "$FINAL_UNREACHABLE" final
final_unreachable=$(awk 'END {print NR+0}' "$FINAL_UNREACHABLE")
final_active=$(awk -F '\t' '$7 == 1 {n++} END {print n+0}' "$FINAL_AUDIT")
final_home=$(awk -F '\t' '$1 == "home" && $7 == 1 {n++} END {print n+0}' "$FINAL_AUDIT")
final_nonhome_violation=$(awk -F '\t' '$1 != "home" && ($4 !~ /^masked/ || $5 == "active" || $6 != 0 || $11 !~ /^masked/ || $12 == "active" || $14 != 0) {n++} END {print n+0}' "$FINAL_AUDIT")

if [ "$retire_failures" -ne 0 ] || [ "$final_unreachable" -ne 0 ] || \
   [ "$final_active" -ne 1 ] || [ "$final_home" -ne 1 ] || [ "$final_nonhome_violation" -ne 0 ]; then
  echo "fleet_singleton_failures retirement=$retire_failures unreachable=$final_unreachable active=$final_active home=$final_home nonhome_policy=$final_nonhome_violation" >&2
  exit 1
fi

printf 'complete\treceiver=home\tactive_receivers=1\tfleet=%s\n' "$EXPECTED"
