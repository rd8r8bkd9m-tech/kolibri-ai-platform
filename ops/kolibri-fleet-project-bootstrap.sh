#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

VERSION="2026-07-02"
MANAGED_MARKER="# Managed by ops/kolibri-fleet-project-bootstrap.sh"
DEFAULT_REPO_URL="https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform.git"
DEFAULT_MIMO_NPM_PACKAGE="@mimo-ai/cli"

DRY_RUN=0
FETCH_NOW=0
FORCE_MANAGED_OVERWRITE=0
INSTALL_MIMO_VIA_NPM=0
MIMO_CODE_MODE="auto"
RESTART_AGENT_HOST=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SCRIPT_REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd -P)"

detect_repo_url() {
  git -C "${SCRIPT_REPO_ROOT}" config --get remote.origin.url 2>/dev/null || printf '%s\n' "${DEFAULT_REPO_URL}"
}

PROJECT_REPO_URL="${KOLIBRI_REPO_URL:-$(detect_repo_url)}"
PROJECT_BRANCH="${KOLIBRI_PROJECT_BRANCH:-}"
PROJECT_REMOTE="${KOLIBRI_PROJECT_REMOTE:-origin}"

is_git_worktree() {
  local path=$1
  [[ -e "${path}" ]] && git -C "${path}" rev-parse --is-inside-work-tree >/dev/null 2>&1
}

if [[ -n "${KOLIBRI_OWNER_PROJECT_PATH:-}" ]]; then
  PROJECT_PATH="${KOLIBRI_OWNER_PROJECT_PATH}"
elif [[ -n "${KOLIBRI_RUNTIME_REPO:-}" ]]; then
  PROJECT_PATH="${KOLIBRI_RUNTIME_REPO}"
elif is_git_worktree "${SCRIPT_REPO_ROOT}"; then
  PROJECT_PATH="${SCRIPT_REPO_ROOT}"
else
  PROJECT_PATH="/var/lib/kolibri-agent/runtime-repo"
fi

RUNTIME_REPO="${KOLIBRI_RUNTIME_REPO:-${PROJECT_PATH}}"
MEMORY_ROOT="${KOLIBRI_PROJECT_MEMORY_ROOT:-/var/lib/kolibri-agent/kfm-memory}"
AGENT_PRIVATE_MEMORY="${KOLIBRI_AGENT_PRIVATE_MEMORY:-/etc/kolibri/agent-memory.md}"
AGENT_HOST_ENV="${KOLIBRI_AGENT_HOST_ENV:-/etc/kolibri-agent-host.env}"
PROJECT_CONTEXT_ENV="${KOLIBRI_PROJECT_CONTEXT_ENV:-/etc/kolibri-project-context.env}"
MIMO_CODE_ENV="${KOLIBRI_MIMO_CODE_ENV:-/etc/kolibri/mimocode.env}"
MIMO_CODE_HOST="${MIMO_CODE_HOST:-127.0.0.1}"
MIMO_CODE_PORT="${MIMO_CODE_PORT:-39231}"
MIMO_NPM_PACKAGE="${MIMO_NPM_PACKAGE:-${DEFAULT_MIMO_NPM_PACKAGE}}"

usage() {
  cat <<'EOF'
Kolibri KFM project-context bootstrap.

Usage:
  ops/kolibri-fleet-project-bootstrap.sh [options]

Safe defaults:
  - does not print secrets;
  - does not reset, clean, pull or checkout dirty runtime repos;
  - installs a fetch-only git sync timer;
  - publishes KOLIBRI_OWNER_PROJECT_PATH and KOLIBRI_RUNTIME_REPO to Agent Host env;
  - binds MiMo Code to loopback only;
  - enables MiMo Code only through loopback `mimo serve --hostname --port`,
    or after an explicit npm install flag supplies a safe package name.

Options:
  --dry-run                         Show planned actions without writing files.
  --project-path PATH               Canonical local project checkout path.
  --runtime-repo PATH               Runtime repo path published to Agent Host.
  --memory-root PATH                Local KFM memory root, default /var/lib/kolibri-agent/kfm-memory.
  --agent-private-memory PATH       Private node memory file, default /etc/kolibri/agent-memory.md.
  --repo-url URL                    Git URL used only when project path is absent.
  --branch REF                      Branch passed to git clone when cloning a missing repo.
  --fetch-now                       Run one fetch after bootstrap; default only installs timer.
  --skip-mimo-code                  Do not install or enable kolibri-mimo-code.service.
  --enable-mimo-code                Require MiMo Code service to become enabled.
  --install-mimo-via-npm            If mimo is missing, install it with npm. Requires --mimo-npm-package.
  --mimo-npm-package PACKAGE        Safe npm package spec for explicit MiMo install, default @mimo-ai/cli.
  --mimo-code-host HOST             Must be 127.0.0.1, ::1, or localhost.
  --mimo-code-port PORT             Loopback MiMo Code port, default 39231.
  --restart-agent-host              Restart only kolibri-agent-host.service after env/drop-in update.
  --force-managed-overwrite         Allow replacing previously unmanaged target unit/drop-in files.
  -h, --help                        Show this help.
EOF
}

log() {
  printf '[kolibri-kfm-bootstrap] %s\n' "$*"
}

die() {
  printf '[kolibri-kfm-bootstrap] ERROR: %s\n' "$*" >&2
  exit 1
}

redact_url() {
  local value=${1-}
  if [[ "${value}" == *"://"* && "${value}" == *"@"* ]]; then
    local scheme rest host_path
    scheme="${value%%://*}"
    rest="${value#*://}"
    host_path="${rest#*@}"
    printf '%s://<redacted>@%s\n' "${scheme}" "${host_path}"
  else
    printf '%s\n' "${value}"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --project-path)
      [[ $# -ge 2 ]] || die "--project-path requires a value"
      PROJECT_PATH="$2"
      shift 2
      ;;
    --runtime-repo)
      [[ $# -ge 2 ]] || die "--runtime-repo requires a value"
      RUNTIME_REPO="$2"
      shift 2
      ;;
    --memory-root)
      [[ $# -ge 2 ]] || die "--memory-root requires a value"
      MEMORY_ROOT="$2"
      shift 2
      ;;
    --agent-private-memory)
      [[ $# -ge 2 ]] || die "--agent-private-memory requires a value"
      AGENT_PRIVATE_MEMORY="$2"
      shift 2
      ;;
    --repo-url)
      [[ $# -ge 2 ]] || die "--repo-url requires a value"
      PROJECT_REPO_URL="$2"
      shift 2
      ;;
    --branch)
      [[ $# -ge 2 ]] || die "--branch requires a value"
      PROJECT_BRANCH="$2"
      shift 2
      ;;
    --fetch-now)
      FETCH_NOW=1
      shift
      ;;
    --skip-mimo-code)
      MIMO_CODE_MODE="skip"
      shift
      ;;
    --enable-mimo-code|--require-mimo-code)
      MIMO_CODE_MODE="enable"
      shift
      ;;
    --install-mimo-via-npm)
      INSTALL_MIMO_VIA_NPM=1
      shift
      ;;
    --mimo-npm-package)
      [[ $# -ge 2 ]] || die "--mimo-npm-package requires a value"
      MIMO_NPM_PACKAGE="$2"
      shift 2
      ;;
    --mimo-code-host)
      [[ $# -ge 2 ]] || die "--mimo-code-host requires a value"
      MIMO_CODE_HOST="$2"
      shift 2
      ;;
    --mimo-code-port)
      [[ $# -ge 2 ]] || die "--mimo-code-port requires a value"
      MIMO_CODE_PORT="$2"
      shift 2
      ;;
    --restart-agent-host)
      RESTART_AGENT_HOST=1
      shift
      ;;
    --force-managed-overwrite)
      FORCE_MANAGED_OVERWRITE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

validate_absolute_path() {
  local name=$1
  local path=$2
  [[ "${path}" == /* ]] || die "${name} must be an absolute path: ${path}"
}

validate_no_inline_credentials() {
  local url=$1
  if [[ "${url}" =~ ^https?://[^/]*@ ]]; then
    die "repo URL with inline credentials is forbidden; use git credential helper or SSH identity"
  fi
}

validate_mimo_host() {
  case "${MIMO_CODE_HOST}" in
    127.0.0.1|localhost|::1) ;;
    *) die "MiMo Code host must be loopback only, got: ${MIMO_CODE_HOST}" ;;
  esac
}

validate_port() {
  [[ "${MIMO_CODE_PORT}" =~ ^[0-9]+$ ]] || die "MiMo Code port must be numeric"
  (( MIMO_CODE_PORT >= 1024 && MIMO_CODE_PORT <= 65535 )) || die "MiMo Code port must be between 1024 and 65535"
}

validate_npm_package() {
  local package=$1
  [[ -n "${package}" ]] || die "--install-mimo-via-npm requires --mimo-npm-package"
  [[ "${package}" != -* ]] || die "npm package must not start with '-'"
  [[ "${package}" != *"://"* && "${package}" != file:* && "${package}" != git+* ]] || die "npm package must be a registry package, not URL/file/git"
  [[ "${package}" =~ ^(@[A-Za-z0-9._-]+/)?[A-Za-z0-9._-]+(@[A-Za-z0-9._~+-]+)?$ ]] || die "npm package contains unsupported characters"
}

require_root_for_apply() {
  if [[ "${DRY_RUN}" -eq 0 && "${EUID}" -ne 0 ]]; then
    die "non-dry-run bootstrap writes /etc/systemd and /var/lib; run with sudo/root"
  fi
}

run_cmd() {
  local description=$1
  shift
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "dry-run: ${description}"
    return 0
  fi
  log "${description}"
  "$@"
}

systemctl_available() {
  command -v systemctl >/dev/null 2>&1
}

ensure_dir() {
  local path=$1
  local mode=$2
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "dry-run: ensure dir ${path} mode ${mode}"
    return 0
  fi
  install -d -m "${mode}" "${path}"
}

write_managed_file() {
  local path=$1
  local mode=$2
  local content=$3
  local tmp
  tmp="$(mktemp)"
  printf '%s\n' "${content}" > "${tmp}"

  if [[ -e "${path}" && "${FORCE_MANAGED_OVERWRITE}" -ne 1 ]] && ! grep -Fq "${MANAGED_MARKER}" "${path}" 2>/dev/null; then
    rm -f "${tmp}"
    die "${path} exists and is not managed by this bootstrap; leaving existing KFM setup untouched"
  fi

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "dry-run: write managed file ${path} mode ${mode}"
    rm -f "${tmp}"
    return 0
  fi

  mkdir -p "$(dirname "${path}")"
  if [[ -f "${path}" ]] && cmp -s "${tmp}" "${path}"; then
    log "unchanged: ${path}"
    rm -f "${tmp}"
    return 0
  fi
  install -m "${mode}" "${tmp}" "${path}"
  chown root:root "${path}" 2>/dev/null || true
  rm -f "${tmp}"
}

quote_env_value() {
  local value=${1-}
  printf "'"
  printf '%s' "${value}" | sed "s/'/'\\\\''/g"
  printf "'"
}

upsert_env_line() {
  local file=$1
  local key=$2
  local value=$3
  local mode tmp quoted

  [[ "${key}" =~ ^[A-Z0-9_]+$ ]] || die "invalid env key: ${key}"
  quoted="$(quote_env_value "${value}")"
  mode=0640
  if [[ "${file}" == "${MIMO_CODE_ENV}" ]]; then
    mode=0600
  fi

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "dry-run: set ${key} in ${file}"
    return 0
  fi

  mkdir -p "$(dirname "${file}")"
  tmp="$(mktemp)"
  if [[ -f "${file}" ]]; then
    awk -v key="${key}" '$0 !~ "^[[:space:]]*" key "=" { print }' "${file}" > "${tmp}"
  else
    printf '%s\n' "${MANAGED_MARKER}" > "${tmp}"
    printf '# Non-secret project context only. Do not put tokens, cookies, keys, passwords or provider credentials here.\n' >> "${tmp}"
  fi
  printf '%s=%s\n' "${key}" "${quoted}" >> "${tmp}"
  install -m "${mode}" "${tmp}" "${file}"
  chown root:root "${file}" 2>/dev/null || true
  rm -f "${tmp}"
}

ensure_git_project() {
  validate_no_inline_credentials "${PROJECT_REPO_URL}"
  validate_absolute_path "project path" "${PROJECT_PATH}"
  validate_absolute_path "runtime repo" "${RUNTIME_REPO}"

  if [[ -e "${PROJECT_PATH}" ]] && ! is_git_worktree "${PROJECT_PATH}"; then
    die "${PROJECT_PATH} exists but is not a git repo; refusing to overwrite it"
  fi

  if is_git_worktree "${PROJECT_PATH}"; then
    run_cmd "verify existing git project at ${PROJECT_PATH}" git -C "${PROJECT_PATH}" rev-parse --is-inside-work-tree >/dev/null
  else
    local clone_cmd=(git clone)
    if [[ -n "${PROJECT_BRANCH}" ]]; then
      clone_cmd+=(--branch "${PROJECT_BRANCH}")
    fi
    clone_cmd+=("${PROJECT_REPO_URL}" "${PROJECT_PATH}")
    run_cmd "clone Kolibri project into ${PROJECT_PATH} from $(redact_url "${PROJECT_REPO_URL}")" "${clone_cmd[@]}"
  fi

  if [[ "${RUNTIME_REPO}" != "${PROJECT_PATH}" ]]; then
    if [[ -e "${RUNTIME_REPO}" ]] && ! is_git_worktree "${RUNTIME_REPO}"; then
      die "${RUNTIME_REPO} exists but is not a git repo; refusing to overwrite it"
    fi
    if is_git_worktree "${RUNTIME_REPO}"; then
      run_cmd "verify existing runtime git repo at ${RUNTIME_REPO}" git -C "${RUNTIME_REPO}" rev-parse --is-inside-work-tree >/dev/null
    else
      local runtime_clone_cmd=(git clone)
      if [[ -n "${PROJECT_BRANCH}" ]]; then
        runtime_clone_cmd+=(--branch "${PROJECT_BRANCH}")
      fi
      runtime_clone_cmd+=("${PROJECT_REPO_URL}" "${RUNTIME_REPO}")
      run_cmd "clone Kolibri runtime repo into ${RUNTIME_REPO} from $(redact_url "${PROJECT_REPO_URL}")" "${runtime_clone_cmd[@]}"
    fi
  fi
}

ensure_memory_root() {
  validate_absolute_path "memory root" "${MEMORY_ROOT}"
  validate_absolute_path "agent private memory" "${AGENT_PRIVATE_MEMORY}"
  ensure_dir "${MEMORY_ROOT}" 0700
  ensure_dir "${MEMORY_ROOT}/state" 0700
  ensure_dir "${MEMORY_ROOT}/notes" 0700
  ensure_dir "${MEMORY_ROOT}/index" 0700
  ensure_dir "${MEMORY_ROOT}/cache" 0700

  local readme
  readme="${MANAGED_MARKER}
# Kolibri Fleet Memory

This directory is node-local KFM memory. It is intentionally outside the git
project by default and must not contain secrets.

Allowed: node state, redacted notes, indexes, cache metadata and rollout
evidence.

Forbidden: API keys, tokens, cookies, SSH private keys, passwords, OAuth
credentials and provider session data.
"
  write_managed_file "${MEMORY_ROOT}/README.md" 0600 "${readme}"

  local node_name project_memory private_memory
  node_name="$(hostname -s 2>/dev/null || hostname 2>/dev/null || printf 'node')"
  if is_git_worktree "${PROJECT_PATH}"; then
    project_memory="${MANAGED_MARKER}
# Kolibri AI Node Memory

Node: ${node_name}
Role: remote Kolibri AI factory worker.
Project source of truth: GitHub repository rd8r8bkd9m-tech/kolibri-ai-platform.
Local project mirror: ${PROJECT_PATH}.
Control Plane mesh URL: http://10.99.0.2:9101, fallback http://10.99.0.10:9101.

Operating rules:
- Work in Russian with the owner and human-readable deputy roles.
- Keep secrets out of repository files and task logs.
- Use GitHub as synchronization source; do not create a shared writable root disk.
- Publish files through /kolibri/nodes/<node_id> namespace metadata.
- Prefer MiMo Code/Agent Host tasks for autonomous work when the owner is offline.
"
    write_managed_file "${PROJECT_PATH}/MEMORY.md" 0644 "${project_memory}"
    if [[ "${DRY_RUN}" -eq 1 ]]; then
      log "dry-run: exclude ${PROJECT_PATH}/MEMORY.md from git"
    else
      grep -qxF MEMORY.md "${PROJECT_PATH}/.git/info/exclude" 2>/dev/null || echo MEMORY.md >> "${PROJECT_PATH}/.git/info/exclude"
    fi
  fi

  private_memory="${MANAGED_MARKER}
# Private Kolibri Agent Memory

Node: ${node_name}
Project: ${PROJECT_PATH}
Public memory: ${PROJECT_PATH}/MEMORY.md
Control Plane: http://10.99.0.2:9101, http://10.99.0.10:9101
Filesystem namespace: /kolibri/nodes/${node_name}
Policy: never print secrets; use node-local worktrees/artifacts; sync through GitHub and Control Plane.
"
  write_managed_file "${AGENT_PRIVATE_MEMORY}" 0600 "${private_memory}"
}

publish_project_env() {
  upsert_env_line "${PROJECT_CONTEXT_ENV}" "KOLIBRI_OWNER_PROJECT_PATH" "${PROJECT_PATH}"
  upsert_env_line "${PROJECT_CONTEXT_ENV}" "KOLIBRI_RUNTIME_REPO" "${RUNTIME_REPO}"
  upsert_env_line "${PROJECT_CONTEXT_ENV}" "KOLIBRI_PROJECT_MEMORY_ROOT" "${MEMORY_ROOT}"
  upsert_env_line "${PROJECT_CONTEXT_ENV}" "KOLIBRI_PROJECT_REMOTE" "${PROJECT_REMOTE}"
  upsert_env_line "${PROJECT_CONTEXT_ENV}" "KOLIBRI_PROJECT_SYNC_MODE" "fetch"
  upsert_env_line "${PROJECT_CONTEXT_ENV}" "KOLIBRI_FILE_ROOTS" "root=/:ro"

  upsert_env_line "${AGENT_HOST_ENV}" "KOLIBRI_OWNER_PROJECT_PATH" "${PROJECT_PATH}"
  upsert_env_line "${AGENT_HOST_ENV}" "KOLIBRI_RUNTIME_REPO" "${RUNTIME_REPO}"
  upsert_env_line "${AGENT_HOST_ENV}" "KOLIBRI_PROJECT_MEMORY_ROOT" "${MEMORY_ROOT}"
  upsert_env_line "${AGENT_HOST_ENV}" "KOLIBRI_FILE_ROOTS" "root=/:ro"
}

install_agent_host_dropin() {
  local content
  content="${MANAGED_MARKER}
[Service]
EnvironmentFile=-${PROJECT_CONTEXT_ENV}
"
  write_managed_file "/etc/systemd/system/kolibri-agent-host.service.d/20-project-context.conf" 0644 "${content}"
}

install_sync_timer() {
  local service timer
  service="${MANAGED_MARKER}
[Unit]
Description=Kolibri project git metadata sync (fetch-only)
After=network-online.target
Wants=network-online.target
ConditionPathExists=${PROJECT_CONTEXT_ENV}

[Service]
Type=oneshot
EnvironmentFile=${PROJECT_CONTEXT_ENV}
ExecStart=/bin/sh -eu -c 'case \"\${KOLIBRI_PROJECT_SYNC_MODE:-fetch}\" in fetch) ;; *) echo \"unsupported sync mode\" >&2; exit 2;; esac; test -n \"\${KOLIBRI_RUNTIME_REPO:-}\"; git -C \"\$KOLIBRI_RUNTIME_REPO\" rev-parse --is-inside-work-tree >/dev/null; exec git -C \"\$KOLIBRI_RUNTIME_REPO\" fetch --prune --tags \"\${KOLIBRI_PROJECT_REMOTE:-origin}\"'
"
  timer="${MANAGED_MARKER}
[Unit]
Description=Kolibri project git metadata sync timer

[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
RandomizedDelaySec=3min
Persistent=true
Unit=kolibri-project-sync.service

[Install]
WantedBy=timers.target
"
  write_managed_file "/etc/systemd/system/kolibri-project-sync.service" 0644 "${service}"
  write_managed_file "/etc/systemd/system/kolibri-project-sync.timer" 0644 "${timer}"
}

install_mimo_via_npm_if_allowed() {
  [[ "${INSTALL_MIMO_VIA_NPM}" -eq 1 ]] || return 1
  validate_npm_package "${MIMO_NPM_PACKAGE}"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "dry-run: would require npm and install MiMo CLI package ${MIMO_NPM_PACKAGE}"
    return 0
  fi
  command -v npm >/dev/null 2>&1 || die "npm is not available, cannot install mimo"
  run_cmd "install MiMo CLI via npm package ${MIMO_NPM_PACKAGE}" npm install -g --omit=dev --no-audit --no-fund "${MIMO_NPM_PACKAGE}"
  command -v mimo >/dev/null 2>&1
}

maybe_install_mimo() {
  if command -v mimo >/dev/null 2>&1; then
    return 0
  fi
  install_mimo_via_npm_if_allowed
}

ensure_mimo_code_password() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "dry-run: ensure ${MIMO_CODE_ENV} contains MIMOCODE_SERVER_PASSWORD"
    return 0
  fi

  mkdir -p "$(dirname "${MIMO_CODE_ENV}")"
  if [[ ! -s "${MIMO_CODE_ENV}" ]] || ! grep -q '^MIMOCODE_SERVER_PASSWORD=' "${MIMO_CODE_ENV}"; then
    local password
    if command -v openssl >/dev/null 2>&1; then
      password="$(openssl rand -hex 24)"
    else
      password="$(date +%s%N)"
    fi
    {
      printf '%s\n' "${MANAGED_MARKER}"
      printf '# Secret local MiMo Code auth. Do not print this file.\n'
      printf 'MIMOCODE_SERVER_PASSWORD=%s\n' "${password}"
    } > "${MIMO_CODE_ENV}"
  fi
  chmod 0600 "${MIMO_CODE_ENV}"
  chown root:root "${MIMO_CODE_ENV}" 2>/dev/null || true
}

install_mimo_code_service() {
  [[ "${MIMO_CODE_MODE}" != "skip" ]] || {
    log "MiMo Code service skipped by flag"
    return 0
  }

  validate_mimo_host
  validate_port

  if ! maybe_install_mimo; then
    if [[ "${MIMO_CODE_MODE}" == "enable" ]]; then
      die "MiMo Code requested but mimo CLI is not installed"
    fi
    log "mimo CLI is not installed; leaving MiMo Code service disabled"
    return 0
  fi

  local mimo_bin
  mimo_bin="$(command -v mimo || true)"
  if [[ "${DRY_RUN}" -eq 1 && -z "${mimo_bin}" && "${INSTALL_MIMO_VIA_NPM}" -eq 1 ]]; then
    validate_npm_package "${MIMO_NPM_PACKAGE}"
    log "dry-run: assuming MiMo CLI would be available after explicit npm install"
    mimo_bin="mimo"
  fi
  if [[ -z "${mimo_bin}" && "${MIMO_CODE_MODE}" == "enable" ]]; then
    die "MiMo Code requested but mimo CLI is not available after bootstrap"
  fi

  ensure_mimo_code_password
  upsert_env_line "${MIMO_CODE_ENV}" "KOLIBRI_OWNER_PROJECT_PATH" "${PROJECT_PATH}"
  upsert_env_line "${MIMO_CODE_ENV}" "KOLIBRI_RUNTIME_REPO" "${RUNTIME_REPO}"
  upsert_env_line "${MIMO_CODE_ENV}" "KOLIBRI_PROJECT_MEMORY_ROOT" "${MEMORY_ROOT}"
  upsert_env_line "${MIMO_CODE_ENV}" "MIMO_CODE_HOST" "${MIMO_CODE_HOST}"
  upsert_env_line "${MIMO_CODE_ENV}" "MIMO_CODE_PORT" "${MIMO_CODE_PORT}"

  local service
  service="${MANAGED_MARKER}
[Unit]
Description=Kolibri MiMo Code loopback service
After=network-online.target
Wants=network-online.target
ConditionPathExists=${MIMO_CODE_ENV}

[Service]
Type=simple
EnvironmentFile=${MIMO_CODE_ENV}
ExecStart=/bin/sh -eu -c 'case \"\${MIMO_CODE_HOST:-127.0.0.1}\" in 127.0.0.1|localhost|::1) ;; *) echo \"refusing non-loopback MiMo Code host\" >&2; exit 2;; esac; cd \"\${KOLIBRI_RUNTIME_REPO:?}\"; exec \"\$(command -v mimo)\" serve --hostname \"\${MIMO_CODE_HOST:-127.0.0.1}\" --port \"\${MIMO_CODE_PORT:-39231}\"'
Restart=on-failure
RestartSec=10
NoNewPrivileges=true
PrivateTmp=true
RestrictSUIDSGID=true

[Install]
WantedBy=multi-user.target
"
  write_managed_file "/etc/systemd/system/kolibri-mimo-code.service" 0644 "${service}"
}

reload_and_enable_systemd() {
  if ! systemctl_available; then
    if [[ "${DRY_RUN}" -eq 1 ]]; then
      log "dry-run: systemctl not available here; target fleet nodes must have systemd"
      return 0
    fi
    die "systemctl is not available; cannot install required sync timer"
  fi
  run_cmd "reload systemd units" systemctl daemon-reload
  run_cmd "enable/start fetch-only project sync timer" systemctl enable --now kolibri-project-sync.timer

  if [[ "${MIMO_CODE_MODE}" != "skip" && -f /etc/systemd/system/kolibri-mimo-code.service ]]; then
    run_cmd "enable/start loopback MiMo Code service" systemctl enable --now kolibri-mimo-code.service
  fi

  if [[ "${RESTART_AGENT_HOST}" -eq 1 ]]; then
    run_cmd "restart kolibri-agent-host.service to pick up project context env" systemctl restart kolibri-agent-host.service
  else
    log "Agent Host env/drop-in installed; service restart skipped"
  fi
}

fetch_now_if_requested() {
  [[ "${FETCH_NOW}" -eq 1 ]] || return 0
  if ! is_git_worktree "${RUNTIME_REPO}"; then
    die "cannot fetch now: ${RUNTIME_REPO} is not a git repo"
  fi
  run_cmd "fetch runtime repo metadata without modifying worktree" git -C "${RUNTIME_REPO}" fetch --prune --tags "${PROJECT_REMOTE}"
}

main() {
  validate_absolute_path "agent private memory" "${AGENT_PRIVATE_MEMORY}"
  validate_absolute_path "Agent Host env" "${AGENT_HOST_ENV}"
  validate_absolute_path "project context env" "${PROJECT_CONTEXT_ENV}"
  validate_absolute_path "MiMo Code env" "${MIMO_CODE_ENV}"
  require_root_for_apply

  log "version ${VERSION}"
  log "project path: ${PROJECT_PATH}"
  log "runtime repo: ${RUNTIME_REPO}"
  log "memory root: ${MEMORY_ROOT}"
  log "repo url: $(redact_url "${PROJECT_REPO_URL}")"

  ensure_git_project
  ensure_memory_root
  publish_project_env
  install_agent_host_dropin
  install_sync_timer
  install_mimo_code_service
  reload_and_enable_systemd
  fetch_now_if_requested

  log "bootstrap complete"
}

main "$@"
