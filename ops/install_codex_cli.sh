#!/usr/bin/env bash
set -Eeuo pipefail

RUN_USER="${KOLIBRI_AGENT_RUN_USER:-kolibri-agent}"
RUN_GROUP="${KOLIBRI_AGENT_RUN_GROUP:-kolibri-agent}"
INSTALL_CMD="${KOLIBRI_CODEX_INSTALL_CMD:-npm install -g @openai/codex@latest}"
CODEX_BIN="${KOLIBRI_CODEX_BIN:-codex}"
CODEX_HOME_DIR="${KOLIBRI_CODEX_HOME:-/var/lib/kolibri-agent/.codex}"
TOKEN_FILE="${KOLIBRI_CODEX_ACCESS_TOKEN_FILE:-}"
AUTH_MODE="${KOLIBRI_CODEX_AUTH_MODE:-access_token}"

log() {
  printf '[kolibri-codex-cli] %s\n' "$*"
}

die() {
  printf '[kolibri-codex-cli] ERROR: %s\n' "$*" >&2
  exit 1
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    die "run as root, for example: sudo -E $0"
  fi
}

require_command() {
  local cmd="$1"
  command -v "${cmd}" >/dev/null 2>&1 || die "missing required command: ${cmd}"
}

ensure_runtime_user() {
  local shell_path
  shell_path="/usr/sbin/nologin"
  [[ -x "${shell_path}" ]] || shell_path="/sbin/nologin"
  [[ -x "${shell_path}" ]] || shell_path="/bin/false"

  if ! getent group "${RUN_GROUP}" >/dev/null 2>&1; then
    groupadd --system "${RUN_GROUP}"
  fi
  if ! id -u "${RUN_USER}" >/dev/null 2>&1; then
    useradd --system --gid "${RUN_GROUP}" --home-dir /var/lib/kolibri-agent --create-home --shell "${shell_path}" "${RUN_USER}"
  fi
}

install_codex() {
  if command -v "${CODEX_BIN}" >/dev/null 2>&1; then
    log "codex already installed at $(command -v "${CODEX_BIN}")"
    return
  fi
  require_command npm
  log "installing Codex CLI with configured package manager command"
  # The command is intentionally configurable because package sources differ by image.
  /bin/sh -lc "${INSTALL_CMD}"
}

codex_as_agent() {
  local script="$1"
  if command -v runuser >/dev/null 2>&1; then
    runuser -u "${RUN_USER}" -- env CODEX_HOME="${CODEX_HOME_DIR}" HOME="/var/lib/kolibri-agent" /bin/sh -lc "${script}"
  else
    su -s /bin/sh "${RUN_USER}" -c "CODEX_HOME='${CODEX_HOME_DIR}' HOME='/var/lib/kolibri-agent' ${script}"
  fi
}

prepare_codex_home() {
  install -d -m 0700 -o "${RUN_USER}" -g "${RUN_GROUP}" "$(dirname -- "${CODEX_HOME_DIR}")" "${CODEX_HOME_DIR}"
}

auth_codex() {
  local token=""
  if [[ "${AUTH_MODE}" == "none" ]]; then
    log "auth skipped by KOLIBRI_CODEX_AUTH_MODE=none"
    return
  fi
  if [[ -n "${CODEX_ACCESS_TOKEN:-}" ]]; then
    token="${CODEX_ACCESS_TOKEN}"
  elif [[ -n "${TOKEN_FILE}" && -r "${TOKEN_FILE}" ]]; then
    token="$(tr -d '\n' <"${TOKEN_FILE}")"
  fi
  if [[ -z "${token}" ]]; then
    log "auth token not present; install verified, auth remains blocked"
    return 2
  fi
  log "logging Codex CLI in with access token from secure environment/file"
  if command -v runuser >/dev/null 2>&1; then
    printf '%s' "${token}" | runuser -u "${RUN_USER}" -- env CODEX_HOME="${CODEX_HOME_DIR}" HOME="/var/lib/kolibri-agent" codex login --with-access-token >/dev/null
  else
    printf '%s' "${token}" | su -s /bin/sh "${RUN_USER}" -c "CODEX_HOME='${CODEX_HOME_DIR}' HOME='/var/lib/kolibri-agent' codex login --with-access-token >/dev/null"
  fi
}

verify_codex() {
  local version_output
  version_output="$("${CODEX_BIN}" --version 2>&1 || true)"
  if [[ -n "${version_output}" ]]; then
    log "codex version: ${version_output}"
  else
    log "codex installed; version command returned no text"
  fi
  codex_as_agent 'codex --help >/dev/null'
  if [[ -f "${CODEX_HOME_DIR}/auth.json" ]]; then
    log "auth cache present for ${RUN_USER} at CODEX_HOME (path redacted from reports)"
  else
    log "auth cache not present; provide CODEX_ACCESS_TOKEN or KOLIBRI_CODEX_ACCESS_TOKEN_FILE for non-interactive auth"
  fi
}

main() {
  require_root
  ensure_runtime_user
  install_codex
  prepare_codex_home
  set +e
  auth_codex
  auth_rc=$?
  set -e
  verify_codex
  if [[ "${auth_rc}" -eq 2 ]]; then
    exit 2
  fi
  exit "${auth_rc}"
}

main "$@"
