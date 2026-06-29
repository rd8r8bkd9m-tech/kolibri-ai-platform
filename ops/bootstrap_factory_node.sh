#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE_NAME="kolibri-agent-host.service"
RUN_USER="kolibri-agent"
RUN_GROUP="kolibri-agent"
INSTALL_BIN="${KOLIBRI_AGENT_INSTALL_BIN:-/usr/local/bin/kolibri-agent-host}"
ENV_FILE="${KOLIBRI_AGENT_ENV_FILE:-/etc/kolibri-agent-host.env}"
SYSTEMD_DIR="${KOLIBRI_SYSTEMD_DIR:-/etc/systemd/system}"
SERVICE_FILE="${SYSTEMD_DIR}/${SERVICE_NAME}"
LOCK_FILE="${KOLIBRI_BOOTSTRAP_LOCK_FILE:-/run/lock/kolibri-bootstrap-factory-node.lock}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
SOURCE_AGENT="${KOLIBRI_AGENT_HOST_SOURCE:-${REPO_ROOT}/ops/agent_host.py}"
SOURCE_SERVICE="${KOLIBRI_AGENT_SERVICE_SOURCE:-${REPO_ROOT}/ops/systemd/${SERVICE_NAME}}"

STANDARD_CAPABILITIES="read_only_probe,generic_implementation,review,image_generation,mesh_node,permission:*"

log() {
  printf '[kolibri-bootstrap] %s\n' "$*"
}

die() {
  printf '[kolibri-bootstrap] ERROR: %s\n' "$*" >&2
  exit 1
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    die "run as root, for example: sudo $0"
  fi
}

require_command() {
  local cmd="$1"
  command -v "${cmd}" >/dev/null 2>&1 || die "missing required command: ${cmd}"
}

sha256_text() {
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$1" | sha256sum | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    printf '%s' "$1" | shasum -a 256 | awk '{print $1}'
  else
    printf '%s' "$1" | cksum | awk '{print $1}'
  fi
}

safe_hostname() {
  local host
  host="$(hostname -s 2>/dev/null || hostname 2>/dev/null || uname -n)"
  host="$(printf '%s' "${host}" | tr -c '[:alnum:]-' '-' | sed 's/--*/-/g; s/^-//; s/-$//')"
  printf '%s' "${host:-node}" | cut -c1-32
}

stable_node_identity() {
  local path iface mac value
  if [[ -r /etc/machine-id ]]; then
    value="$(tr -d ' \n' </etc/machine-id)"
    [[ -n "${value}" ]] && printf 'machine-id=%s\n' "${value}"
  fi

  value="$(hostname -f 2>/dev/null || hostname 2>/dev/null || uname -n)"
  [[ -n "${value}" ]] && printf 'hostname=%s\n' "${value}"

  for path in /sys/class/dmi/id/product_uuid /sys/class/dmi/id/board_serial; do
    if [[ -r "${path}" ]]; then
      value="$(tr -d ' \n' <"${path}")"
      [[ -n "${value}" ]] && printf '%s=%s\n' "${path}" "${value}"
    fi
  done

  if [[ -d /sys/class/net ]]; then
    for path in /sys/class/net/*/address; do
      [[ -r "${path}" ]] || continue
      iface="$(basename -- "$(dirname -- "${path}")")"
      [[ "${iface}" == "lo" ]] && continue
      mac="$(tr -d ' \n' <"${path}")"
      [[ -n "${mac}" && "${mac}" != "00:00:00:00:00:00" ]] && printf 'mac=%s\n' "${mac}"
    done | sort
  fi
}

stable_node_id() {
  local identity hash
  identity="$(stable_node_identity)"
  [[ -n "${identity}" ]] || identity="$(hostname 2>/dev/null || uname -n)"
  hash="$(sha256_text "${identity}" | cut -c1-12)"
  printf 'factory-%s-%s' "$(safe_hostname)" "${hash}"
}

first_control_url() {
  local urls="$1"
  printf '%s' "${urls%%,*}"
}

quote_env_value() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"' "${value}"
}

write_env_kv() {
  local key="$1"
  local value="$2"
  printf '%s=' "${key}"
  quote_env_value "${value}"
  printf '\n'
}

install_runtime_user() {
  local shell_path
  shell_path="/usr/sbin/nologin"
  [[ -x "${shell_path}" ]] || shell_path="/sbin/nologin"
  [[ -x "${shell_path}" ]] || shell_path="/bin/false"

  if ! getent group "${RUN_GROUP}" >/dev/null 2>&1; then
    log "creating system group ${RUN_GROUP}"
    if command -v groupadd >/dev/null 2>&1; then
      groupadd --system "${RUN_GROUP}"
    elif command -v addgroup >/dev/null 2>&1; then
      addgroup --system "${RUN_GROUP}"
    else
      die "cannot create ${RUN_GROUP}: groupadd/addgroup not found"
    fi
  fi

  if id -u "${RUN_USER}" >/dev/null 2>&1; then
    if command -v usermod >/dev/null 2>&1; then
      usermod -g "${RUN_GROUP}" "${RUN_USER}" >/dev/null 2>&1 || true
    fi
    return
  fi

  log "creating system user ${RUN_USER}"
  if command -v useradd >/dev/null 2>&1; then
    useradd --system --gid "${RUN_GROUP}" --home-dir /var/lib/kolibri-agent --create-home --shell "${shell_path}" "${RUN_USER}"
  elif command -v adduser >/dev/null 2>&1; then
    adduser --system --home /var/lib/kolibri-agent --ingroup "${RUN_GROUP}" --shell "${shell_path}" "${RUN_USER}"
  else
    die "cannot create ${RUN_USER}: useradd/adduser not found"
  fi
}

install_agent_binary() {
  [[ -f "${SOURCE_AGENT}" ]] || die "agent source not found: ${SOURCE_AGENT}"
  install -D -m 0755 "${SOURCE_AGENT}" "${INSTALL_BIN}"
  log "installed ${INSTALL_BIN}"
}

install_systemd_unit() {
  [[ -f "${SOURCE_SERVICE}" ]] || die "service source not found: ${SOURCE_SERVICE}"
  install -D -m 0644 "${SOURCE_SERVICE}" "${SERVICE_FILE}"
  log "installed ${SERVICE_FILE}"
}

write_env_file() {
  local control_urls control_url node_id agent_id work_root artifact_root repo_url
  local max_inflight heartbeat_interval lease_refresh permissions permission_packs capabilities
  local tmp

  control_urls="${KOLIBRI_FACTORY_CONTROL_URLS:-${KOLIBRI_FACTORY_CONTROL_URL:-http://10.99.0.2:9101}}"
  control_url="${KOLIBRI_FACTORY_CONTROL_URL:-$(first_control_url "${control_urls}")}"
  node_id="${KOLIBRI_NODE_ID:-$(stable_node_id)}"
  agent_id="${KOLIBRI_AGENT_ID:-${node_id}-agent-host}"
  capabilities="${KOLIBRI_AGENT_CAPABILITIES:-${STANDARD_CAPABILITIES}}"
  permissions="${KOLIBRI_AGENT_PERMISSIONS:-*}"
  permission_packs="${KOLIBRI_AGENT_PERMISSION_PACKS:-full_autonomy}"
  max_inflight="${KOLIBRI_MAX_INFLIGHT:-1}"
  heartbeat_interval="${KOLIBRI_HEARTBEAT_INTERVAL:-10}"
  lease_refresh="${KOLIBRI_LEASE_REFRESH:-20}"
  work_root="${KOLIBRI_AGENT_WORK_ROOT:-/var/lib/kolibri-agent/worktrees}"
  artifact_root="${KOLIBRI_AGENT_ARTIFACT_ROOT:-/var/lib/kolibri-agent/artifacts}"
  repo_url="${KOLIBRI_REPO_URL:-https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform.git}"

  install -d -o "${RUN_USER}" -g "${RUN_GROUP}" -m 0750 /var/lib/kolibri-agent
  install -d -o "${RUN_USER}" -g "${RUN_GROUP}" -m 0750 "${work_root}" "${artifact_root}"
  install -d -m 0755 "$(dirname -- "${ENV_FILE}")"

  tmp="$(mktemp)"
  chmod 0600 "${tmp}"
  if [[ -f "${ENV_FILE}" ]]; then
    awk '
      /^# BEGIN KOLIBRI FACTORY NODE PROFILE$/ { skip=1; next }
      /^# END KOLIBRI FACTORY NODE PROFILE$/ { skip=0; next }
      !skip { print }
    ' "${ENV_FILE}" >"${tmp}"
    printf '\n' >>"${tmp}"
  else
    {
      printf '# Kolibri Factory Agent Host environment.\n'
      printf '# Managed profile keys are regenerated by ops/bootstrap_factory_node.sh.\n'
      printf '# Keep secrets in a separate systemd drop-in or secret manager.\n\n'
    } >"${tmp}"
  fi

  {
    printf '# BEGIN KOLIBRI FACTORY NODE PROFILE\n'
    write_env_kv KOLIBRI_FACTORY_CONTROL_URL "${control_url}"
    write_env_kv KOLIBRI_FACTORY_CONTROL_URLS "${control_urls}"
    write_env_kv KOLIBRI_NODE_ID "${node_id}"
    write_env_kv KOLIBRI_AGENT_ID "${agent_id}"
    write_env_kv KOLIBRI_AGENT_CAPABILITIES "${capabilities}"
    write_env_kv KOLIBRI_AGENT_PERMISSIONS "${permissions}"
    write_env_kv KOLIBRI_AGENT_PERMISSION_PACKS "${permission_packs}"
    write_env_kv KOLIBRI_MAX_INFLIGHT "${max_inflight}"
    write_env_kv KOLIBRI_HEARTBEAT_INTERVAL "${heartbeat_interval}"
    write_env_kv KOLIBRI_LEASE_REFRESH "${lease_refresh}"
    write_env_kv KOLIBRI_AGENT_WORK_ROOT "${work_root}"
    write_env_kv KOLIBRI_AGENT_ARTIFACT_ROOT "${artifact_root}"
    write_env_kv KOLIBRI_REPO_URL "${repo_url}"
    printf '# END KOLIBRI FACTORY NODE PROFILE\n'
  } >>"${tmp}"

  install -m 0600 -o root -g root "${tmp}" "${ENV_FILE}"
  rm -f "${tmp}"
  log "wrote ${ENV_FILE} for node ${node_id}"
}

restart_service() {
  local jitter hash delay node_id
  systemctl daemon-reload
  systemctl reset-failed "${SERVICE_NAME}" >/dev/null 2>&1 || true
  systemctl enable "${SERVICE_NAME}"

  jitter="${KOLIBRI_BOOTSTRAP_RESTART_JITTER:-30}"
  node_id="${KOLIBRI_NODE_ID:-$(stable_node_id)}"
  if [[ "${jitter}" =~ ^[0-9]+$ ]] && (( jitter > 0 )); then
    hash="$(sha256_text "${node_id}" | cut -c1-6)"
    delay=$((16#${hash} % (jitter + 1)))
    if (( delay > 0 )); then
      log "restart jitter ${delay}s for batch-safe rollout"
      sleep "${delay}"
    fi
  fi

  systemctl restart "${SERVICE_NAME}"
  log "enabled and restarted ${SERVICE_NAME}"
}

print_health_hints() {
  local control_urls control_url node_id
  control_urls="${KOLIBRI_FACTORY_CONTROL_URLS:-${KOLIBRI_FACTORY_CONTROL_URL:-http://10.99.0.2:9101}}"
  control_url="${KOLIBRI_FACTORY_CONTROL_URL:-$(first_control_url "${control_urls}")}"
  node_id="${KOLIBRI_NODE_ID:-$(stable_node_id)}"

  cat <<EOF

Kolibri Factory Agent Host bootstrap complete.
Node id: ${node_id}
Capabilities: ${KOLIBRI_AGENT_CAPABILITIES:-${STANDARD_CAPABILITIES}}

Health hints:
  systemctl status --no-pager ${SERVICE_NAME}
  journalctl -u ${SERVICE_NAME} -n 100 --no-pager
  curl -fsS ${control_url}/health
  curl -fsS ${control_url}/v1/nodes | grep ${node_id}

Batch knobs:
  KOLIBRI_BOOTSTRAP_RESTART_JITTER=60 sudo -E ${REPO_ROOT}/ops/bootstrap_factory_node.sh
  KOLIBRI_FACTORY_CONTROL_URLS=http://control-a:9101,http://control-b:9101 sudo -E ${REPO_ROOT}/ops/bootstrap_factory_node.sh
EOF
}

main() {
  require_root
  require_command systemctl
  require_command python3
  require_command git
  require_command flock
  install -d -m 0755 "$(dirname -- "${LOCK_FILE}")"
  exec 9>"${LOCK_FILE}"
  flock -n 9 || die "another bootstrap is already running"

  install_runtime_user
  install_agent_binary
  install_systemd_unit
  write_env_file
  restart_service
  print_health_hints
}

main "$@"
