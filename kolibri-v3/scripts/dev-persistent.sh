#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
v3_root="$(cd -- "${script_dir}/.." && pwd -P)"
screen_bin="${KOLIBRI_V3_SCREEN_BIN:-/usr/bin/screen}"
npm_bin="${KOLIBRI_V3_NPM_BIN:-/opt/homebrew/bin/npm}"
session_name="kolibri-v3-dev"
backend_url="http://127.0.0.1:8002/v1/health"
app_url="http://127.0.0.1:3103/app"
runtime_log="${v3_root}/var/dev-runtime/screen.log"
screen_entry="${v3_root}/scripts/dev-screen-entry.sh"
dev_stack_pid_file="${v3_root}/var/dev-runtime/dev-stack.pid"

pid_is_alive() {
  local pid="$1"
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  kill -0 "${pid}" >/dev/null 2>&1
}

dev_stack_pid() {
  [[ -f "${dev_stack_pid_file}" ]] || return 1
  local pid
  pid="$(tr -d '[:space:]' < "${dev_stack_pid_file}" 2>/dev/null || true)"
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  if pid_is_alive "${pid}"; then
    printf '%s\n' "${pid}"
    return 0
  fi
  return 1
}

dev_stack_listener_pid() {
  # Fallback for stacks started before the pid-file guard: any process that
  # owns the V3 backend port and belongs to this repository.
  local listener_pid
  listener_pid="$(lsof -nP -iTCP:8002 -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true)"
  if [[ "${listener_pid}" =~ ^[0-9]+$ ]] &&
    ps -o command= -p "${listener_pid}" 2>/dev/null | grep -q "kolibri-v3"; then
    printf '%s\n' "${listener_pid}"
    return 0
  fi
  return 1
}

ports_busy_by_dev_stack() {
  if dev_stack_pid >/dev/null 2>&1; then
    return 0
  fi
  dev_stack_listener_pid >/dev/null 2>&1
}

dev_stack_process_group() {
  local pid="$1"
  local pgid
  pgid="$(ps -o pgid= -p "${pid}" 2>/dev/null | tr -d '[:space:]' || true)"
  [[ "${pgid}" =~ ^[0-9]+$ ]] || return 1
  printf '%s\n' "${pgid}"
}

session_exists() {
  local listing
  listing="$("${screen_bin}" -ls 2>/dev/null || true)"
  grep -Eq "[[:space:]][0-9]+[.]${session_name}[[:space:]]" <<<"${listing}"
}

runtime_ready() {
  local backend_payload app_status
  backend_payload="$(curl --fail --silent --show-error \
    --max-time 1 "${backend_url}" 2>/dev/null || true)"
  app_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --max-time 2 "${app_url}" 2>/dev/null || true)"
  [[
    "${backend_payload}" == *'"status":"ok"'* &&
    "${backend_payload}" == *'"service":"kolibri-v3"'* &&
    "${backend_payload}" == *'"instanceId":"'* &&
    "${backend_payload}" == *'"agentRuntimeContract":"kolibri.agent-runtime@1.1"'* &&
    "${backend_payload}" == *"\"sourceRoot\":\"${v3_root}\""*
  ]] && [[ "${app_status}" == "200" ]]
}

runtime_ports_free() {
  ! lsof -nP -iTCP:8002 -sTCP:LISTEN >/dev/null 2>&1 &&
    ! lsof -nP -iTCP:3103 -sTCP:LISTEN >/dev/null 2>&1 &&
    ! lsof -nP -iTCP:3104 -sTCP:LISTEN >/dev/null 2>&1 &&
    ! lsof -nP -iTCP:4104 -sTCP:LISTEN >/dev/null 2>&1
}

session_process_group() {
  local listing screen_pid session_child process_group
  listing="$("${screen_bin}" -ls 2>/dev/null || true)"
  screen_pid="$(
    sed -nE \
      "s/^[[:space:]]*([0-9]+)[.]${session_name}[[:space:]].*$/\1/p" \
      <<<"${listing}" |
      head -n 1
  )"
  [[ "${screen_pid}" =~ ^[0-9]+$ ]] || return 1
  session_child="$(pgrep -P "${screen_pid}" | head -n 1 || true)"
  [[ "${session_child}" =~ ^[0-9]+$ ]] || return 1
  process_group="$(
    ps -o pgid= -p "${session_child}" 2>/dev/null |
      tr -d '[:space:]'
  )"
  [[ "${process_group}" =~ ^[0-9]+$ ]] || return 1
  printf '%s\n' "${process_group}"
}

start_runtime() {
  if session_exists; then
    if runtime_ready; then
      printf '%s\n' "Kolibri V3 persistent development runtime is ready."
      return
    fi
    # A session that exists but cannot pass readiness is broken; tear it down
    # and start fresh instead of leaving the runtime wedged forever.
    stop_runtime
  fi

  if lsof -nP -iTCP:8002 -sTCP:LISTEN >/dev/null 2>&1 ||
    lsof -nP -iTCP:3103 -sTCP:LISTEN >/dev/null 2>&1 ||
    lsof -nP -iTCP:3104 -sTCP:LISTEN >/dev/null 2>&1 ||
    lsof -nP -iTCP:4104 -sTCP:LISTEN >/dev/null 2>&1; then
    printf '%s\n' \
      "V3 ports 8002/3103/3104/4104 are occupied outside the persistent V3 session." >&2
    exit 1
  fi

  [[ -x "${screen_bin}" ]] || {
    printf 'GNU screen is not executable: %s\n' "${screen_bin}" >&2
    exit 1
  }
  [[ -x "${npm_bin}" ]] || {
    printf 'npm is not executable: %s\n' "${npm_bin}" >&2
    exit 1
  }
  [[ -x "${screen_entry}" ]] || {
    printf 'Kolibri V3 screen entry is not executable: %s\n' \
      "${screen_entry}" >&2
    exit 1
  }

  cd -- "${v3_root}"
  mkdir -p -- "$(dirname -- "${runtime_log}")"

  # A live stack that lost its screen session must be reaped first, otherwise
  # the fresh session would fight it for ports (the "server keeps falling"
  # symptom: backend bind errors and UI 502 flapping).
  if ports_busy_by_dev_stack; then
    printf '%s\n' \
      "Kolibri V3 runtime is alive outside its screen session; stopping it." >&2
    stop_runtime
  fi

  "${screen_bin}" -dmS "${session_name}" \
    /usr/bin/env \
    PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
    KOLIBRI_V3_NPM_BIN="${npm_bin}" \
    /bin/bash "${screen_entry}"

  for _attempt in {1..150}; do
    if runtime_ready; then
      printf '%s\n' "Kolibri V3 persistent development runtime is ready."
      printf 'Attach logs with: screen -r %s\n' "${session_name}"
      return
    fi
    sleep 0.1
  done

  "${screen_bin}" -S "${session_name}" -X quit >/dev/null 2>&1 || true
  printf '%s\n' "Kolibri V3 persistent runtime failed readiness." >&2
  exit 1
}

stop_runtime() {
  local process_group=""
  if ! session_exists; then
    if ports_busy_by_dev_stack; then
      local stack_pid stack_pgid
      stack_pid="$(dev_stack_pid || dev_stack_listener_pid)"
      stack_pgid="$(dev_stack_process_group "${stack_pid}" || true)"
      if [[ "${stack_pgid}" =~ ^[0-9]+$ ]]; then
        kill -TERM -- "-${stack_pgid}" >/dev/null 2>&1 || true
      else
        kill -TERM "${stack_pid}" >/dev/null 2>&1 || true
      fi
      for _attempt in {1..100}; do
        if runtime_ports_free; then
          printf '%s\n' "Kolibri V3 persistent development runtime stopped."
          return
        fi
        sleep 0.1
      done
      printf '%s\n' \
        "Kolibri V3 orphaned dev stack did not release its ports." >&2
      exit 1
    fi
    if ! runtime_ports_free; then
      printf '%s\n' \
        "Kolibri V3 session is absent but its ports are still occupied." >&2
      exit 1
    fi
    printf '%s\n' "Kolibri V3 persistent development runtime is not running."
    return
  fi

  process_group="$(session_process_group || true)"
  "${screen_bin}" -S "${session_name}" -X stuff $'\003'
  for _attempt in {1..100}; do
    if ! session_exists && runtime_ports_free; then
      printf '%s\n' "Kolibri V3 persistent development runtime stopped."
      return
    fi
    sleep 0.1
  done

  "${screen_bin}" -S "${session_name}" -X quit >/dev/null 2>&1 || true
  if [[ "${process_group}" =~ ^[0-9]+$ ]]; then
    kill -TERM -- "-${process_group}" >/dev/null 2>&1 || true
  fi
  for _attempt in {1..50}; do
    if ! session_exists && runtime_ports_free; then
      printf '%s\n' "Kolibri V3 persistent development runtime stopped."
      return
    fi
    sleep 0.1
  done

  printf '%s\n' \
    "Kolibri V3 persistent runtime did not release its ports." >&2
  exit 1
}

show_status() {
  if ! session_exists; then
    if ports_busy_by_dev_stack; then
      printf '%s\n' "screen_session=orphaned"
      if runtime_ready; then
        printf '%s\n' "runtime=ready"
        return
      fi
      printf '%s\n' "runtime=not_ready"
      exit 1
    fi
    printf '%s\n' "screen_session=stopped"
    exit 1
  fi
  printf '%s\n' "screen_session=running"
  if runtime_ready; then
    printf '%s\n' "runtime=ready"
    return
  fi
  printf '%s\n' "runtime=not_ready"
  exit 1
}

case "${1:-start}" in
  start)
    start_runtime
    ;;
  stop)
    stop_runtime
    ;;
  restart)
    stop_runtime
    start_runtime
    ;;
  status)
    show_status
    ;;
  *)
    printf 'usage: %s {start|stop|restart|status}\n' "$0" >&2
    exit 2
    ;;
esac
