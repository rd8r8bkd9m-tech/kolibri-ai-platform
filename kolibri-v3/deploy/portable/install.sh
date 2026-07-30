#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "install_error=root_required" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
for bootstrap_command in readlink stat; do
  command -v "$bootstrap_command" >/dev/null || {
    echo "install_error=missing_command command=$bootstrap_command" >&2
    exit 3
  }
done

sudo_uid="${SUDO_UID:-0}"
[[ "$sudo_uid" =~ ^[0-9]+$ ]] || sudo_uid=0
validate_trusted_input() {
  local path="$1"
  local label="$2"
  local owner mode canonical
  [[ "$path" = /* && -f "$path" && ! -L "$path" ]] || {
    echo "install_error=${label}_invalid path=$path" >&2
    return 2
  }
  canonical="$(readlink -f -- "$path")"
  [[ "$canonical" == "$path" ]] || {
    echo "install_error=${label}_not_canonical path=$path" >&2
    return 2
  }
  read -r owner mode < <(stat -c '%u %a' "$path")
  [[ "$owner" == "0" || "$owner" == "$sudo_uid" ]] || {
    echo "install_error=${label}_owner_invalid" >&2
    return 2
  }
  (( (8#$mode & 8#022) == 0 )) || {
    echo "install_error=${label}_writable_by_untrusted_user" >&2
    return 2
  }
}
verify_open_input() {
  local path="$1"
  local descriptor_path="$2"
  local path_identity descriptor_identity
  path_identity="$(stat -c '%d:%i' "$path")"
  descriptor_identity="$(stat -Lc '%d:%i' "$descriptor_path")"
  [[ "$path_identity" == "$descriptor_identity" ]] || {
    echo "install_error=input_changed_during_open path=$path" >&2
    return 3
  }
}

config_candidate="${1:-"$script_dir/config.env"}"
if [[ "$config_candidate" != /* ]]; then
  config_candidate="$(pwd -P)/$config_candidate"
fi
[[ ! -L "$config_candidate" ]] || {
  echo "install_error=config_symlink_forbidden path=$config_candidate" >&2
  exit 2
}
config_file="$(readlink -f -- "$config_candidate" 2>/dev/null || true)"
[[ -n "$config_file" ]] || {
  echo "install_error=config_missing path=$config_candidate" >&2
  exit 2
}
validate_trusted_input "$config_file" config
exec 5<"$config_file"
verify_open_input "$config_file" /proc/self/fd/5

declare -A install_config=()
config_line_number=0
while IFS= read -r config_line <&5 || [[ -n "$config_line" ]]; do
  ((config_line_number += 1))
  [[ "$config_line" != *$'\r'* ]] || {
    echo "install_error=config_line_invalid line=$config_line_number" >&2
    exit 2
  }
  [[ "$config_line" =~ ^[[:space:]]*$ ||
    "$config_line" =~ ^[[:space:]]*# ]] && continue
  [[ "$config_line" =~ ^([A-Z][A-Z0-9_]*)=(.*)$ ]] || {
    echo "install_error=config_line_invalid line=$config_line_number" >&2
    exit 2
  }
  config_key="${BASH_REMATCH[1]}"
  config_value="${BASH_REMATCH[2]}"
  case "$config_key" in
    KOLIBRI_INSTANCE|KOLIBRI_SERVICE_USER|KOLIBRI_INSTALL_ROOT|\
KOLIBRI_CONFIG_ROOT|KOLIBRI_BACKUP_ROOT|KOLIBRI_BACKEND_PORT|\
KOLIBRI_FRONTEND_PORT|KOLIBRI_DOMAIN|KOLIBRI_PUBLIC_SCHEME|\
KOLIBRI_ENABLE_NGINX|KOLIBRI_NGINX_SITE|KOLIBRI_TLS_CERTIFICATE|\
KOLIBRI_TLS_CERTIFICATE_KEY|KOLIBRI_DIRECT_MODEL_RUNTIME|\
KOLIBRI_CODEX_BIN|KOLIBRI_REQUIRE_MIMO|KOLIBRI_MIMO_BASE_URL|\
KOLIBRI_MIMO_CLI_PATH|KOLIBRI_RUN_FRONTEND_TESTS|\
KOLIBRI_HEALTH_TIMEOUT_SECONDS|KOLIBRI_PREFLIGHT_ONLY|\
KOLIBRI_ENABLE_PRODUCT_WORKER|KOLIBRI_ENABLE_PROVIDER_WORKER|\
KOLIBRI_RELEASE_ARCHIVE)
      ;;
    *)
      echo "install_error=config_key_not_allowed key=$config_key" >&2
      exit 2
      ;;
  esac
  [[ ! -v "install_config[$config_key]" ]] || {
    echo "install_error=config_key_duplicate key=$config_key" >&2
    exit 2
  }
  install_config["$config_key"]="$config_value"
done
for config_key in "${!install_config[@]}"; do
  printf -v "$config_key" '%s' "${install_config[$config_key]}"
done
release_archive="${2:-${KOLIBRI_RELEASE_ARCHIVE:-}}"

: "${KOLIBRI_INSTANCE:?KOLIBRI_INSTANCE is required}"
: "${KOLIBRI_SERVICE_USER:?KOLIBRI_SERVICE_USER is required}"
: "${KOLIBRI_INSTALL_ROOT:?KOLIBRI_INSTALL_ROOT is required}"
: "${KOLIBRI_CONFIG_ROOT:?KOLIBRI_CONFIG_ROOT is required}"
: "${KOLIBRI_BACKUP_ROOT:?KOLIBRI_BACKUP_ROOT is required}"
: "${KOLIBRI_BACKEND_PORT:?KOLIBRI_BACKEND_PORT is required}"
: "${KOLIBRI_FRONTEND_PORT:?KOLIBRI_FRONTEND_PORT is required}"
: "${KOLIBRI_DOMAIN:?KOLIBRI_DOMAIN is required}"
: "${KOLIBRI_PUBLIC_SCHEME:?KOLIBRI_PUBLIC_SCHEME is required}"

KOLIBRI_ENABLE_NGINX="${KOLIBRI_ENABLE_NGINX:-true}"
KOLIBRI_NGINX_SITE="${KOLIBRI_NGINX_SITE:-/etc/nginx/sites-enabled/${KOLIBRI_INSTANCE}.conf}"
KOLIBRI_DIRECT_MODEL_RUNTIME="${KOLIBRI_DIRECT_MODEL_RUNTIME:-true}"
KOLIBRI_CODEX_BIN="${KOLIBRI_CODEX_BIN:-/usr/local/bin/codex}"
KOLIBRI_REQUIRE_MIMO="${KOLIBRI_REQUIRE_MIMO:-true}"
KOLIBRI_MIMO_BASE_URL="${KOLIBRI_MIMO_BASE_URL:-http://127.0.0.1:39231}"
KOLIBRI_MIMO_CLI_PATH="${KOLIBRI_MIMO_CLI_PATH:-/usr/local/bin/mimo}"
KOLIBRI_RUN_FRONTEND_TESTS="${KOLIBRI_RUN_FRONTEND_TESTS:-true}"
KOLIBRI_HEALTH_TIMEOUT_SECONDS="${KOLIBRI_HEALTH_TIMEOUT_SECONDS:-90}"
KOLIBRI_PREFLIGHT_ONLY="${KOLIBRI_PREFLIGHT_ONLY:-false}"
KOLIBRI_ENABLE_PRODUCT_WORKER="${KOLIBRI_ENABLE_PRODUCT_WORKER:-true}"
KOLIBRI_ENABLE_PROVIDER_WORKER="${KOLIBRI_ENABLE_PROVIDER_WORKER:-false}"

[[ "$KOLIBRI_INSTANCE" =~ ^[a-z0-9][a-z0-9-]{1,47}$ ]] ||
  { echo "install_error=invalid_instance" >&2; exit 2; }
[[ "$KOLIBRI_SERVICE_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] ||
  { echo "install_error=invalid_service_user" >&2; exit 2; }
[[ "$KOLIBRI_DOMAIN" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*[A-Za-z0-9]$ &&
  "$KOLIBRI_DOMAIN" != *..* ]] ||
  { echo "install_error=invalid_domain" >&2; exit 2; }
[[ "$KOLIBRI_PUBLIC_SCHEME" == "https" ]] ||
  { echo "install_error=production_requires_https" >&2; exit 2; }
for boolean_name in \
  KOLIBRI_ENABLE_NGINX \
  KOLIBRI_DIRECT_MODEL_RUNTIME \
  KOLIBRI_REQUIRE_MIMO \
  KOLIBRI_RUN_FRONTEND_TESTS \
  KOLIBRI_PREFLIGHT_ONLY \
  KOLIBRI_ENABLE_PRODUCT_WORKER \
  KOLIBRI_ENABLE_PROVIDER_WORKER; do
  boolean_value="${!boolean_name}"
  [[ "$boolean_value" == "true" || "$boolean_value" == "false" ]] || {
    echo "install_error=invalid_boolean name=$boolean_name" >&2
    exit 2
  }
done
[[ "$KOLIBRI_ENABLE_PRODUCT_WORKER" == "true" ]] || {
  echo "install_error=product_worker_required" >&2
  exit 2
}
for port in "$KOLIBRI_BACKEND_PORT" "$KOLIBRI_FRONTEND_PORT"; do
  [[ "$port" =~ ^[0-9]+$ ]] && (( port >= 1024 && port <= 65535 )) ||
    { echo "install_error=invalid_port value=$port" >&2; exit 2; }
done
[[ "$KOLIBRI_BACKEND_PORT" != "$KOLIBRI_FRONTEND_PORT" ]] ||
  { echo "install_error=ports_must_differ" >&2; exit 2; }
[[ "$KOLIBRI_HEALTH_TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] &&
  (( KOLIBRI_HEALTH_TIMEOUT_SECONDS >= 10 &&
    KOLIBRI_HEALTH_TIMEOUT_SECONDS <= 600 )) || {
  echo "install_error=health_timeout_invalid" >&2
  exit 2
}

for path in "$KOLIBRI_INSTALL_ROOT" "$KOLIBRI_CONFIG_ROOT" "$KOLIBRI_BACKUP_ROOT"; do
  [[ "$path" =~ ^/[A-Za-z0-9._/-]+$ &&
    "$path" != "/" &&
    "$path" != *//* &&
    "$(readlink -m -- "$path")" == "$path" ]] ||
    { echo "install_error=unsafe_path value=$path" >&2; exit 2; }
done

id "$KOLIBRI_SERVICE_USER" >/dev/null 2>&1 ||
  { echo "install_error=service_user_missing user=$KOLIBRI_SERVICE_USER" >&2; exit 3; }
service_group="$(id -gn "$KOLIBRI_SERVICE_USER")"
[[ "$service_group" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] ||
  { echo "install_error=invalid_service_group" >&2; exit 3; }
service_uid="$(id -u "$KOLIBRI_SERVICE_USER")"
service_gid="$(id -g "$KOLIBRI_SERVICE_USER")"
service_home="$(getent passwd "$KOLIBRI_SERVICE_USER" | cut -d: -f6)"
[[ -n "$service_home" && -d "$service_home" ]] ||
  { echo "install_error=service_home_missing user=$KOLIBRI_SERVICE_USER" >&2; exit 3; }

for command_name in \
  awk basename bash chmod chown cmp cp curl find flock grep head install \
  journalctl mktemp mv node npm python3 readlink rm runuser sleep stat systemctl \
  systemd-analyze tar; do
  command -v "$command_name" >/dev/null ||
    { echo "install_error=missing_command command=$command_name" >&2; exit 3; }
done
node_major="$(node -p 'Number(process.versions.node.split(".")[0])')"
(( node_major >= 20 )) ||
  { echo "install_error=node_too_old version=$(node --version)" >&2; exit 3; }
python3 -c 'import venv' >/dev/null 2>&1 ||
  { echo "install_error=python_venv_unavailable" >&2; exit 3; }

release_manifest_path="${release_archive}.manifest.json"
release_checksum_path="${release_archive}.sha256"
validate_trusted_input "$release_archive" release_archive
validate_trusted_input "$release_manifest_path" release_manifest
validate_trusted_input "$release_checksum_path" release_checksum
release_archive_name="$(basename -- "$release_archive")"
[[ "$release_archive_name" =~ ^kolibri-v3-[0-9a-f]{12}-[0-9a-f]{12}[.]tar[.]gz$ ]] || {
  echo "install_error=release_archive_name_invalid" >&2
  exit 2
}
exec 7<"$release_archive"
exec 8<"$release_manifest_path"
exec 6<"$release_checksum_path"
verify_open_input "$release_archive" /proc/self/fd/7
verify_open_input "$release_manifest_path" /proc/self/fd/8
verify_open_input "$release_checksum_path" /proc/self/fd/6
release_verification="$(
  python3 "$script_dir/release-manifest.py" verify \
    --archive /proc/self/fd/7 \
    --archive-name "$release_archive_name" \
    --manifest /proc/self/fd/8 \
    --checksum /proc/self/fd/6
)" || {
  echo "install_error=release_archive_verification_failed" >&2
  exit 3
}
release_id="$(
  awk -F= '$1 == "release_id" {print $2; exit}' <<<"$release_verification"
)"
release_commit="$(
  awk -F= '$1 == "release_commit" {print $2; exit}' <<<"$release_verification"
)"
release_content_digest="$(
  awk -F= '$1 == "release_content_digest" {print $2; exit}' \
    <<<"$release_verification"
)"
release_migration_max="$(
  awk -F= '$1 == "release_migration_max" {print $2; exit}' \
    <<<"$release_verification"
)"
[[ "$release_id" =~ ^kolibri-v3-[0-9a-f]{12}-[0-9a-f]{12}$ &&
  "$release_commit" =~ ^[0-9a-f]{40}$ &&
  "$release_content_digest" =~ ^[0-9a-f]{64}$ &&
  "$release_migration_max" =~ ^[0-9]{3,}$ ]] || {
  echo "install_error=release_provenance_invalid" >&2
  exit 3
}
(( 10#$release_migration_max >= 44 )) || {
  echo "install_error=required_migration_missing" >&2
  exit 3
}

if [[ "$KOLIBRI_DIRECT_MODEL_RUNTIME" == "true" ]]; then
  [[ -x "$KOLIBRI_CODEX_BIN" ]] ||
    { echo "install_error=codex_missing path=$KOLIBRI_CODEX_BIN" >&2; exit 3; }
  runuser -u "$KOLIBRI_SERVICE_USER" -- "$KOLIBRI_CODEX_BIN" --version >/dev/null ||
    { echo "install_error=codex_unusable user=$KOLIBRI_SERVICE_USER" >&2; exit 3; }
  runuser -u "$KOLIBRI_SERVICE_USER" -- env HOME="$service_home" \
    "$KOLIBRI_CODEX_BIN" login status >/dev/null ||
    { echo "install_error=codex_not_authenticated user=$KOLIBRI_SERVICE_USER" >&2; exit 3; }
fi

if [[ "$KOLIBRI_REQUIRE_MIMO" == "true" ]]; then
  [[ -x "$KOLIBRI_MIMO_CLI_PATH" ]] ||
    { echo "install_error=mimo_missing path=$KOLIBRI_MIMO_CLI_PATH" >&2; exit 3; }
  curl -fsS --max-time 5 "$KOLIBRI_MIMO_BASE_URL/global/health" |
    python3 -c 'import json, sys; assert json.load(sys.stdin).get("healthy") is True' ||
    { echo "install_error=mimo_unhealthy url=$KOLIBRI_MIMO_BASE_URL" >&2; exit 3; }
fi

if [[ "$KOLIBRI_ENABLE_NGINX" == "true" ]]; then
  [[ "$KOLIBRI_NGINX_SITE" =~ ^/etc/nginx/sites-enabled/[A-Za-z0-9._-]+$ ]] ||
    { echo "install_error=unsafe_nginx_site path=$KOLIBRI_NGINX_SITE" >&2; exit 2; }
  command -v nginx >/dev/null ||
    { echo "install_error=nginx_missing" >&2; exit 3; }
  : "${KOLIBRI_TLS_CERTIFICATE:?KOLIBRI_TLS_CERTIFICATE is required}"
  : "${KOLIBRI_TLS_CERTIFICATE_KEY:?KOLIBRI_TLS_CERTIFICATE_KEY is required}"
  [[ "$KOLIBRI_TLS_CERTIFICATE" =~ ^/[A-Za-z0-9._/-]+$ &&
    "$KOLIBRI_TLS_CERTIFICATE_KEY" =~ ^/[A-Za-z0-9._/-]+$ &&
    -r "$KOLIBRI_TLS_CERTIFICATE" &&
    -r "$KOLIBRI_TLS_CERTIFICATE_KEY" ]] ||
    { echo "install_error=tls_files_unreadable" >&2; exit 3; }
fi

validate_operator_backend_environment() {
  local path="$1"
  shift
  python3 "$script_dir/install-contract.py" \
    validate-operator-backend-env \
    --backend-env "$path" \
    --expected-uid 0 \
    "$@"
}
validate_operator_backend_environment \
  "$KOLIBRI_CONFIG_ROOT/backend.env" \
  --allow-missing

preflight_worker_configuration() {
  local kind="$1"
  local workers_environment="$2"
  python3 "$script_dir/install-contract.py" validate-worker-enablement \
    --kind "$kind" \
    --workers-env "$workers_environment" \
    --credentials-root "$KOLIBRI_CONFIG_ROOT/credentials" \
    --expected-uid 0
}
if [[ "$KOLIBRI_ENABLE_PRODUCT_WORKER" == "true" ]]; then
  preflight_worker_configuration product "$KOLIBRI_CONFIG_ROOT/workers.env"
fi
if [[ "$KOLIBRI_ENABLE_PROVIDER_WORKER" == "true" ]]; then
  preflight_worker_configuration provider "$KOLIBRI_CONFIG_ROOT/workers.env"
fi

if [[ "$KOLIBRI_PREFLIGHT_ONLY" == "true" ]]; then
  echo "preflight_status=ok"
  echo "instance=$KOLIBRI_INSTANCE"
  echo "service_user=$KOLIBRI_SERVICE_USER"
  echo "release=$release_id"
  echo "commit=$release_commit"
  echo "product_worker_requested=$KOLIBRI_ENABLE_PRODUCT_WORKER"
  echo "provider_worker_requested=$KOLIBRI_ENABLE_PROVIDER_WORKER"
  echo "developer_execution=externalized_home_provider_worker_plane"
  echo "trusted_agent_plane=kolibri_agent_host"
  echo "embedded_developer_agent=forbidden_in_production"
  exit 0
fi

release_root="$KOLIBRI_INSTALL_ROOT/releases/$release_id"
current_link="$KOLIBRI_INSTALL_ROOT/current"
data_root="$KOLIBRI_INSTALL_ROOT/var"
scheduled_backup_root="$KOLIBRI_BACKUP_ROOT/database"
backend_env_file="$KOLIBRI_CONFIG_ROOT/backend.env"
release_env_file="$KOLIBRI_CONFIG_ROOT/release.env"
frontend_env_file="$KOLIBRI_CONFIG_ROOT/frontend.env"
workers_env_file="$KOLIBRI_CONFIG_ROOT/workers.env"
credentials_root="$KOLIBRI_CONFIG_ROOT/credentials"
backend_unit="/etc/systemd/system/${KOLIBRI_INSTANCE}-backend.service"
frontend_unit="/etc/systemd/system/${KOLIBRI_INSTANCE}-frontend.service"
product_worker_unit="/etc/systemd/system/${KOLIBRI_INSTANCE}-product-run-worker.service"
provider_worker_unit="/etc/systemd/system/${KOLIBRI_INSTANCE}-provider-enrollment-worker.service"
audit_worker_unit="/etc/systemd/system/${KOLIBRI_INSTANCE}-estimate-reconciliation-audit.service"
monitor_unit="/etc/systemd/system/${KOLIBRI_INSTANCE}-release-monitor.service"
monitor_timer="/etc/systemd/system/${KOLIBRI_INSTANCE}-release-monitor.timer"
backup_service_unit="/etc/systemd/system/${KOLIBRI_INSTANCE}-database-backup.service"
backup_timer_unit="/etc/systemd/system/${KOLIBRI_INSTANCE}-database-backup.timer"
worker_units=(
  "${KOLIBRI_INSTANCE}-product-run-worker.service"
  "${KOLIBRI_INSTANCE}-provider-enrollment-worker.service"
  "${KOLIBRI_INSTANCE}-estimate-reconciliation-audit.service"
)
durable_worker_units=(
  "${KOLIBRI_INSTANCE}-product-run-worker.service"
  "${KOLIBRI_INSTANCE}-provider-enrollment-worker.service"
)
libexec_root="$KOLIBRI_INSTALL_ROOT/libexec"
worker_launcher="$libexec_root/worker_launcher.py"
database_helper="$libexec_root/database-rehearsal.py"
systemctl_path="$(command -v systemctl)"
journalctl_path="$(command -v journalctl)"
allowed_origin="$KOLIBRI_PUBLIC_SCHEME://$KOLIBRI_DOMAIN"
nginx_site="$KOLIBRI_NGINX_SITE"
backup_dir="$KOLIBRI_BACKUP_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-$release_id"
lock_file="/run/lock/${KOLIBRI_INSTANCE}-release.lock"
switched=0
services_stopped=0
release_stage=""
release_promoted=0

exec 9>"$lock_file"
flock -n 9 ||
  { echo "install_error=release_locked instance=$KOLIBRI_INSTANCE" >&2; exit 4; }

cleanup_staging() {
  if [[ -n "$release_stage" && "$release_promoted" -eq 0 &&
    -d "$release_stage" ]]; then
    rm -rf -- "$release_stage"
  fi
  rm -f -- \
    "$backend_env_file.new" \
    "$release_env_file.new" \
    "$frontend_env_file.new" \
    "$workers_env_file.new" \
    "$backend_unit.new" \
    "$frontend_unit.new" \
    "$product_worker_unit.new" \
    "$provider_worker_unit.new" \
    "$audit_worker_unit.new" \
    "$monitor_unit.new" \
    "$monitor_timer.new" \
    "$backup_service_unit.new" \
    "$backup_timer_unit.new" \
    "$worker_launcher.new" \
    "$database_helper.new"
  if [[ "$KOLIBRI_ENABLE_NGINX" == "true" ]]; then
    rm -f -- "$nginx_site.new"
  fi
}
trap cleanup_staging EXIT
cleanup_staging

for managed_path in \
  "$KOLIBRI_INSTALL_ROOT" \
  "$KOLIBRI_INSTALL_ROOT/releases" \
  "$data_root" \
  "$KOLIBRI_BACKUP_ROOT" \
  "$scheduled_backup_root" \
  "$KOLIBRI_CONFIG_ROOT"; do
  [[ ! -L "$managed_path" ]] || {
    echo "install_error=managed_directory_symlink path=$managed_path" >&2
    exit 3
  }
done
install -d -o root -g root -m 755 \
  "$KOLIBRI_INSTALL_ROOT" "$KOLIBRI_INSTALL_ROOT/releases"
install -d -o root -g "$service_group" -m 710 "$KOLIBRI_BACKUP_ROOT"
install -d -o root -g root -m 700 "$KOLIBRI_CONFIG_ROOT"
install -d -o "$KOLIBRI_SERVICE_USER" -g "$service_group" -m 700 \
  "$data_root" "$scheduled_backup_root"
for managed_path in \
  "$KOLIBRI_INSTALL_ROOT" \
  "$KOLIBRI_INSTALL_ROOT/releases" \
  "$data_root" \
  "$KOLIBRI_BACKUP_ROOT" \
  "$scheduled_backup_root" \
  "$KOLIBRI_CONFIG_ROOT"; do
  [[ "$(readlink -f -- "$managed_path")" == "$managed_path" ]] || {
    echo "install_error=managed_directory_not_canonical path=$managed_path" >&2
    exit 3
  }
done
[[ ! -e "$release_root" && ! -L "$release_root" ]] ||
  { echo "install_error=release_exists release=$release_id" >&2; exit 5; }

release_stage="$(
  mktemp -d "$KOLIBRI_INSTALL_ROOT/releases/.${release_id}.XXXXXX"
)"
[[ -n "$release_stage" && -d "$release_stage" &&
  ! -L "$release_stage" ]] || {
  echo "install_error=release_staging_failed" >&2
  exit 3
}
build_root="$release_stage/build"
runtime_root="$release_stage/runtime"
install -d -o "$KOLIBRI_SERVICE_USER" -g "$service_group" -m 755 \
  "$build_root" "$runtime_root"

tar --strip-components=1 -C "$build_root" \
  --extract --gzip --file=/proc/self/fd/7
[[ -f "$build_root/RELEASE_PROVENANCE.json" &&
  -f "$build_root/RELEASE_CONTENTS.sha256" &&
  -f "$build_root/MIGRATIONS.sha256" ]] || {
  echo "install_error=extracted_release_provenance_missing" >&2
  exit 3
}
for linked_installer_file in \
  install.sh install-contract.py release-manifest.py; do
  cmp -s \
    "$script_dir/$linked_installer_file" \
    "$build_root/deploy/portable/$linked_installer_file" || {
    echo "install_error=installer_release_mismatch file=$linked_installer_file" >&2
    exit 3
  }
done
chown -R "$KOLIBRI_SERVICE_USER:$service_group" "$release_stage"

run_as_service() {
  runuser -u "$KOLIBRI_SERVICE_USER" -- env HOME="$service_home" "$@"
}

run_as_service python3 -m venv "$build_root/backend/venv"
run_as_service "$build_root/backend/venv/bin/python" -m pip install \
  --disable-pip-version-check -r "$build_root/backend/requirements.txt"
run_as_service env \
  KOLIBRI_RELEASE_ID="$release_id" \
  KOLIBRI_RELEASE_COMMIT="$release_commit" \
  bash -lc \
  "cd '$build_root/backend' && ./venv/bin/python -c 'import app.main'"
run_as_service env \
  KOLIBRI_RELEASE_ID="$release_id" \
  KOLIBRI_RELEASE_COMMIT="$release_commit" \
  bash -lc "cd '$build_root' && npm ci"
run_as_service env \
  KOLIBRI_RELEASE_ID="$release_id" \
  KOLIBRI_RELEASE_COMMIT="$release_commit" \
  bash -lc "cd '$build_root' && npm run typecheck"
if [[ "$KOLIBRI_RUN_FRONTEND_TESTS" == "true" ]]; then
  run_as_service env \
    KOLIBRI_RELEASE_ID="$release_id" \
    KOLIBRI_RELEASE_COMMIT="$release_commit" \
    bash -lc "cd '$build_root' && npm test"
fi
run_as_service env \
  KOLIBRI_RELEASE_ID="$release_id" \
  KOLIBRI_RELEASE_COMMIT="$release_commit" \
  bash -lc "cd '$build_root' && npm run build"

install -d -o "$KOLIBRI_SERVICE_USER" -g "$service_group" -m 755 \
  "$runtime_root/frontend" "$runtime_root/frontend/.next"
cp -a "$build_root/.next/standalone/." "$runtime_root/frontend/"
cp -a "$build_root/.next/static" "$runtime_root/frontend/.next/static"

post_build_verification="$(
  python3 "$script_dir/release-manifest.py" verify \
    --archive /proc/self/fd/7 \
    --archive-name "$release_archive_name" \
    --manifest /proc/self/fd/8 \
    --checksum /proc/self/fd/6
)" || {
  echo "install_error=release_archive_post_build_verification_failed" >&2
  exit 3
}
[[ "$post_build_verification" == "$release_verification" ]] || {
  echo "install_error=release_provenance_changed_during_build" >&2
  exit 3
}
source_root="$release_stage/source"
install -d -o root -g root -m 755 "$source_root"
tar --strip-components=1 -C "$source_root" \
  --extract --gzip --file=/proc/self/fd/7
[[ -f "$source_root/RELEASE_PROVENANCE.json" &&
  -f "$source_root/RELEASE_CONTENTS.sha256" &&
  -f "$source_root/MIGRATIONS.sha256" ]] || {
  echo "install_error=clean_release_source_missing" >&2
  exit 3
}
mv "$build_root/backend/venv" "$source_root/backend/venv"
cp -a "$source_root/public" "$runtime_root/frontend/public"
ln -s ../source/backend "$runtime_root/backend"
chown -h "$KOLIBRI_SERVICE_USER:$service_group" "$runtime_root/backend"
rm -rf -- "$build_root"

host_assets_root="$release_stage/host-assets"
worker_render_root="$host_assets_root/worker-units"
operation_render_root="$host_assets_root/operation-units"
install -d -o root -g root -m 700 \
  "$host_assets_root" "$worker_render_root" "$operation_render_root"
install -o root -g root -m 755 \
  "$source_root/deploy/workers/worker_launcher.py" \
  "$host_assets_root/worker_launcher.py"
python3 "$script_dir/install-contract.py" render-workers \
  --source-root "$source_root/deploy/workers" \
  --output-dir "$worker_render_root" \
  --instance "$KOLIBRI_INSTANCE" \
  --install-root "$KOLIBRI_INSTALL_ROOT" \
  --config-root "$KOLIBRI_CONFIG_ROOT" \
  --service-user "$KOLIBRI_SERVICE_USER" \
  --service-group "$service_group" \
  --backend-service "${KOLIBRI_INSTANCE}-backend.service"
python3 "$script_dir/install-contract.py" render-operations \
  --output-dir "$operation_render_root" \
  --instance "$KOLIBRI_INSTANCE" \
  --current-link "$current_link" \
  --service-user "$KOLIBRI_SERVICE_USER" \
  --service-group "$service_group" \
  --service-uid "$service_uid" \
  --data-root "$data_root" \
  --backup-root "$scheduled_backup_root" \
  --backend-port "$KOLIBRI_BACKEND_PORT" \
  --frontend-port "$KOLIBRI_FRONTEND_PORT" \
  --public-origin "$allowed_origin" \
  --release-id "$release_id" \
  --release-commit "$release_commit" \
  --expected-schema "$release_migration_max" \
  --systemctl "$systemctl_path" \
  --journalctl "$journalctl_path" \
  --database-helper "$database_helper"
printf '%s\n' "$release_content_digest" > "$release_stage/CONTENT_SHA256"
printf '%s\n' "$release_commit" > "$release_stage/GIT_COMMIT"

chown -R root:root "$release_stage"
find "$release_stage" -type d -exec chmod 0555 {} +
find "$release_stage" -type f -perm -0100 -exec chmod 0555 {} +
find "$release_stage" -type f ! -perm -0100 -exec chmod 0444 {} +
if find "$release_stage" -type f -perm -0222 -print -quit | grep -q .; then
  echo "install_error=release_tree_not_immutable" >&2
  exit 3
fi
mv -T "$release_stage" "$release_root"
release_promoted=1
runtime_root="$release_root/runtime"
source_root="$release_root/source"
host_assets_root="$release_root/host-assets"
worker_render_root="$host_assets_root/worker-units"
operation_render_root="$host_assets_root/operation-units"

install -d -o root -g root -m 700 "$backup_dir"
backup_optional_file() {
  local source_path="$1"
  local backup_name="$2"
  if [[ -f "$source_path" && ! -L "$source_path" ]]; then
    cp -a "$source_path" "$backup_dir/$backup_name"
  elif [[ -e "$source_path" || -L "$source_path" ]]; then
    echo "install_error=unsafe_existing_host_file path=$source_path" >&2
    return 3
  else
    : > "$backup_dir/$backup_name.absent"
  fi
}
if [[ -e "$current_link" && ! -L "$current_link" ]]; then
  echo "install_error=current_release_pointer_unsafe" >&2
  exit 3
fi
[[ ! -L "$current_link" ]] || cp -a "$current_link" "$backup_dir/previous-current"
backup_optional_file "$backend_unit" backend.service
backup_optional_file "$frontend_unit" frontend.service
backup_optional_file "$product_worker_unit" product-worker.service
backup_optional_file "$provider_worker_unit" provider-worker.service
backup_optional_file "$audit_worker_unit" audit-worker.service
backup_optional_file "$monitor_unit" release-monitor.service
backup_optional_file "$monitor_timer" release-monitor.timer
backup_optional_file "$backup_service_unit" database-backup.service
backup_optional_file "$backup_timer_unit" database-backup.timer
backup_optional_file "$worker_launcher" worker_launcher.py
backup_optional_file "$database_helper" database-rehearsal.py
backup_optional_file "$backend_env_file" backend.env
backup_optional_file "$release_env_file" release.env
backup_optional_file "$frontend_env_file" frontend.env
backup_optional_file "$workers_env_file" workers.env
if [[ "$KOLIBRI_ENABLE_NGINX" == "true" ]]; then
  backup_optional_file "$nginx_site" nginx.conf
fi
for worker_unit_name in "${worker_units[@]}"; do
  systemctl is-enabled "$worker_unit_name" \
    > "$backup_dir/$worker_unit_name.enablement" 2>&1 || true
  systemctl is-active "$worker_unit_name" \
    > "$backup_dir/$worker_unit_name.activity" 2>&1 || true
done
systemctl is-enabled "${KOLIBRI_INSTANCE}-release-monitor.timer" \
  > "$backup_dir/release-monitor.timer.enablement" 2>&1 || true
systemctl is-active "${KOLIBRI_INSTANCE}-release-monitor.timer" \
  > "$backup_dir/release-monitor.timer.activity" 2>&1 || true
systemctl is-enabled "${KOLIBRI_INSTANCE}-database-backup.timer" \
  > "$backup_dir/database-backup.timer.enablement" 2>&1 || true
systemctl is-active "${KOLIBRI_INSTANCE}-database-backup.timer" \
  > "$backup_dir/database-backup.timer.activity" 2>&1 || true
if [[ -e "$data_root/kolibri-v3.db" || -L "$data_root/kolibri-v3.db" ]]; then
  [[ -f "$data_root/kolibri-v3.db" &&
    ! -L "$data_root/kolibri-v3.db" &&
    "$(readlink -f -- "$data_root/kolibri-v3.db")" == "$data_root/kolibri-v3.db" ]] || {
    echo "install_error=database_path_unsafe" >&2
    exit 3
  }
  "$source_root/backend/venv/bin/python" \
    "$source_root/deploy/portable/database-rehearsal.py" backup \
    --source "$data_root/kolibri-v3.db" \
    --output "$backup_dir/kolibri-v3.db"
fi

csrf_file="$data_root/.csrf-secret"
if [[ ! -e "$csrf_file" && ! -L "$csrf_file" ]]; then
  umask 077
  csrf_temporary="$(mktemp "$data_root/.csrf-secret.XXXXXX")"
  python3 -c \
    'import secrets, sys; sys.stdout.write(secrets.token_hex(32))' \
    > "$csrf_temporary"
  chmod 600 "$csrf_temporary"
  chown "$KOLIBRI_SERVICE_USER:$service_group" "$csrf_temporary"
  mv -T "$csrf_temporary" "$csrf_file"
fi
[[ -f "$csrf_file" && ! -L "$csrf_file" &&
  "$(readlink -f -- "$csrf_file")" == "$csrf_file" ]] || {
  echo "install_error=csrf_secret_unsafe" >&2
  exit 3
}
read -r csrf_uid csrf_gid csrf_mode csrf_size < <(
  stat -c '%u %g %a %s' "$csrf_file"
)
[[ "$csrf_uid" == "$service_uid" &&
  "$csrf_gid" == "$service_gid" &&
  "$csrf_mode" == "600" &&
  "$csrf_size" == "64" ]] || {
  echo "install_error=csrf_secret_permissions_invalid" >&2
  exit 3
}
exec 4<"$csrf_file"
verify_open_input "$csrf_file" /proc/self/fd/4
IFS= read -r -N 64 csrf_value <&4 || true
[[ "$csrf_value" =~ ^[0-9a-f]{64}$ ]] || {
  echo "install_error=csrf_secret_value_invalid" >&2
  exit 3
}
umask 077
if [[ -f "$backend_env_file" && ! -L "$backend_env_file" ]]; then
  read -r backend_env_uid backend_env_mode < <(
    stat -c '%u %a' "$backend_env_file"
  )
  [[ "$backend_env_uid" == "0" && "$backend_env_mode" == "600" ]] || {
    echo "install_error=operator_backend_environment_permissions_invalid" >&2
    exit 3
  }
elif [[ -e "$backend_env_file" || -L "$backend_env_file" ]]; then
  echo "install_error=operator_backend_environment_unsafe" >&2
  exit 3
else
  install -o root -g root -m 600 /dev/null "$backend_env_file.new"
fi
if [[ -f "$backend_env_file.new" ]]; then
  validate_operator_backend_environment "$backend_env_file.new"
else
  validate_operator_backend_environment "$backend_env_file"
fi

cat > "$release_env_file.new" <<EOF
KOLIBRI_V3_ENV=production
KOLIBRI_V3_DATABASE_URL=sqlite:///$data_root/kolibri-v3.db
KOLIBRI_V3_ALLOWED_ORIGINS=$allowed_origin
KOLIBRI_V3_COOKIE_SECURE=true
KOLIBRI_V3_CSRF_SECRET=$csrf_value
KOLIBRI_V3_DIRECT_MODEL_RUNTIME=$KOLIBRI_DIRECT_MODEL_RUNTIME
KOLIBRI_V3_REQUIRE_PRODUCT_WORKER=true
KOLIBRI_V3_WORKER_HEARTBEAT_TTL_SECONDS=30
KOLIBRI_RELEASE_ID=$release_id
KOLIBRI_RELEASE_COMMIT=$release_commit
EOF
chmod 600 "$release_env_file.new"

cat > "$frontend_env_file.new" <<EOF
HOME=$service_home
NODE_ENV=production
KOLIBRI_V3_BACKEND_URL=http://127.0.0.1:$KOLIBRI_BACKEND_PORT
KOLIBRI_RELEASE_ID=$release_id
KOLIBRI_RELEASE_COMMIT=$release_commit
EOF

cat > "$backend_unit.new" <<EOF
[Unit]
Description=Kolibri V3 backend ($KOLIBRI_INSTANCE)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$KOLIBRI_SERVICE_USER
Group=$service_group
EnvironmentFile=$backend_env_file
EnvironmentFile=$release_env_file
UMask=0077
WorkingDirectory=$current_link/backend
ExecStart=$current_link/backend/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port $KOLIBRI_BACKEND_PORT --no-access-log
Restart=always
RestartSec=3s
TimeoutStartSec=60s
TimeoutStopSec=30s
LimitNOFILE=65536
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

cat > "$frontend_unit.new" <<EOF
[Unit]
Description=Kolibri V3 frontend ($KOLIBRI_INSTANCE)
Wants=network-online.target
After=network-online.target ${KOLIBRI_INSTANCE}-backend.service

[Service]
Type=simple
User=$KOLIBRI_SERVICE_USER
Group=$service_group
EnvironmentFile=$frontend_env_file
Environment=HOSTNAME=127.0.0.1
Environment=PORT=$KOLIBRI_FRONTEND_PORT
WorkingDirectory=$current_link/frontend
ExecStart=$(command -v node) $current_link/frontend/server.js
Restart=always
RestartSec=3s
TimeoutStartSec=60s
TimeoutStopSec=30s
LimitNOFILE=65536
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

install -d -o root -g root -m 755 "$libexec_root"
[[ ! -L "$credentials_root" ]] || {
  echo "install_error=worker_credentials_root_unsafe" >&2
  exit 3
}
install -d -o root -g root -m 700 "$credentials_root"
[[ "$(readlink -f -- "$credentials_root")" == "$credentials_root" ]] || {
  echo "install_error=worker_credentials_root_not_canonical" >&2
  exit 3
}
install -o root -g root -m 755 \
  "$host_assets_root/worker_launcher.py" "$worker_launcher.new"
install -o root -g root -m 755 \
  "$source_root/deploy/portable/database-rehearsal.py" \
  "$database_helper.new"
install -o root -g root -m 644 \
  "$worker_render_root/${KOLIBRI_INSTANCE}-product-run-worker.service" \
  "$product_worker_unit.new"
install -o root -g root -m 644 \
  "$worker_render_root/${KOLIBRI_INSTANCE}-provider-enrollment-worker.service" \
  "$provider_worker_unit.new"
install -o root -g root -m 644 \
  "$worker_render_root/${KOLIBRI_INSTANCE}-estimate-reconciliation-audit.service" \
  "$audit_worker_unit.new"
install -o root -g root -m 644 \
  "$operation_render_root/${KOLIBRI_INSTANCE}-release-monitor.service" \
  "$monitor_unit.new"
install -o root -g root -m 644 \
  "$operation_render_root/${KOLIBRI_INSTANCE}-release-monitor.timer" \
  "$monitor_timer.new"
install -o root -g root -m 644 \
  "$operation_render_root/${KOLIBRI_INSTANCE}-database-backup.service" \
  "$backup_service_unit.new"
install -o root -g root -m 644 \
  "$operation_render_root/${KOLIBRI_INSTANCE}-database-backup.timer" \
  "$backup_timer_unit.new"
if [[ -f "$workers_env_file" && ! -L "$workers_env_file" ]]; then
  read -r workers_env_uid workers_env_mode < <(
    stat -c '%u %a' "$workers_env_file"
  )
  [[ "$workers_env_uid" == "0" && "$workers_env_mode" == "600" ]] || {
    echo "install_error=workers_environment_permissions_invalid" >&2
    exit 3
  }
  install -o root -g root -m 600 "$workers_env_file" "$workers_env_file.new"
elif [[ -e "$workers_env_file" || -L "$workers_env_file" ]]; then
  echo "install_error=workers_environment_unsafe" >&2
  exit 3
else
  install -o root -g root -m 600 \
    "$source_root/deploy/workers/workers.env.example" \
    "$workers_env_file.new"
fi
if [[ "$KOLIBRI_ENABLE_PRODUCT_WORKER" == "true" ]]; then
  preflight_worker_configuration product "$workers_env_file.new"
fi
if [[ "$KOLIBRI_ENABLE_PROVIDER_WORKER" == "true" ]]; then
  preflight_worker_configuration provider "$workers_env_file.new"
fi

if [[ "$KOLIBRI_ENABLE_NGINX" == "true" ]]; then
  cat > "$nginx_site.new" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $KOLIBRI_DOMAIN;
    location ^~ /.well-known/acme-challenge/ { root /var/www/html; }
    return 301 https://$KOLIBRI_DOMAIN\$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name $KOLIBRI_DOMAIN;
    ssl_certificate $KOLIBRI_TLS_CERTIFICATE;
    ssl_certificate_key $KOLIBRI_TLS_CERTIFICATE_KEY;
    client_max_body_size 64m;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options SAMEORIGIN always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
    location = /livez {
        access_log off;
        proxy_pass http://127.0.0.1:$KOLIBRI_FRONTEND_PORT/api/live;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_connect_timeout 3s;
        proxy_read_timeout 5s;
        proxy_buffering off;
    }
    location = /readyz {
        access_log off;
        proxy_pass http://127.0.0.1:$KOLIBRI_FRONTEND_PORT/api/health;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_connect_timeout 3s;
        proxy_read_timeout 5s;
        proxy_buffering off;
    }
    location = /healthz {
        access_log off;
        proxy_pass http://127.0.0.1:$KOLIBRI_FRONTEND_PORT/api/health;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_connect_timeout 3s;
        proxy_read_timeout 5s;
        proxy_buffering off;
    }
    location / {
        proxy_pass http://127.0.0.1:$KOLIBRI_FRONTEND_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_connect_timeout 10s;
        proxy_send_timeout 1800s;
        proxy_read_timeout 1800s;
        proxy_buffering off;
        proxy_request_buffering off;
    }
}
EOF
fi

restore_previous_durable_workers() {
  local unit_name enablement activity
  for unit_name in "${durable_worker_units[@]}"; do
    enablement="$(
      head -n 1 "$backup_dir/$unit_name.enablement" 2>/dev/null || true
    )"
    activity="$(
      head -n 1 "$backup_dir/$unit_name.activity" 2>/dev/null || true
    )"
    case "$enablement" in
      enabled)
        systemctl enable "$unit_name" >/dev/null 2>&1 || true
        ;;
      enabled-runtime)
        systemctl enable --runtime "$unit_name" >/dev/null 2>&1 || true
        ;;
      *)
        systemctl disable "$unit_name" >/dev/null 2>&1 || true
        ;;
    esac
    if [[ "$activity" == "active" ]]; then
      systemctl start "$unit_name" >/dev/null 2>&1 || true
    else
      systemctl stop "$unit_name" >/dev/null 2>&1 || true
    fi
  done
}

restore_previous_monitor() {
  local enablement activity
  enablement="$(
    head -n 1 "$backup_dir/release-monitor.timer.enablement" \
      2>/dev/null || true
  )"
  activity="$(
    head -n 1 "$backup_dir/release-monitor.timer.activity" \
      2>/dev/null || true
  )"
  case "$enablement" in
    enabled)
      systemctl enable "${KOLIBRI_INSTANCE}-release-monitor.timer" \
        >/dev/null 2>&1 || true
      ;;
    enabled-runtime)
      systemctl enable --runtime \
        "${KOLIBRI_INSTANCE}-release-monitor.timer" \
        >/dev/null 2>&1 || true
      ;;
    *)
      systemctl disable "${KOLIBRI_INSTANCE}-release-monitor.timer" \
        >/dev/null 2>&1 || true
      ;;
  esac
  if [[ "$activity" == "active" ]]; then
    systemctl start "${KOLIBRI_INSTANCE}-release-monitor.timer" \
      >/dev/null 2>&1 || true
  else
    systemctl stop "${KOLIBRI_INSTANCE}-release-monitor.timer" \
      >/dev/null 2>&1 || true
  fi
}

restore_previous_backup_timer() {
  local enablement activity
  enablement="$(
    head -n 1 "$backup_dir/database-backup.timer.enablement" \
      2>/dev/null || true
  )"
  activity="$(
    head -n 1 "$backup_dir/database-backup.timer.activity" \
      2>/dev/null || true
  )"
  case "$enablement" in
    enabled)
      systemctl enable "${KOLIBRI_INSTANCE}-database-backup.timer" \
        >/dev/null 2>&1 || true
      ;;
    enabled-runtime)
      systemctl enable --runtime \
        "${KOLIBRI_INSTANCE}-database-backup.timer" \
        >/dev/null 2>&1 || true
      ;;
    *)
      systemctl disable "${KOLIBRI_INSTANCE}-database-backup.timer" \
        >/dev/null 2>&1 || true
      ;;
  esac
  if [[ "$activity" == "active" ]]; then
    systemctl start "${KOLIBRI_INSTANCE}-database-backup.timer" \
      >/dev/null 2>&1 || true
  else
    systemctl stop "${KOLIBRI_INSTANCE}-database-backup.timer" \
      >/dev/null 2>&1 || true
  fi
}

rollback() {
  local exit_code=$?
  trap - ERR
  systemctl disable --now \
    "${KOLIBRI_INSTANCE}-release-monitor.timer" 2>/dev/null || true
  systemctl stop \
    "${KOLIBRI_INSTANCE}-release-monitor.service" 2>/dev/null || true
  systemctl disable --now \
    "${KOLIBRI_INSTANCE}-database-backup.timer" 2>/dev/null || true
  systemctl stop \
    "${KOLIBRI_INSTANCE}-database-backup.service" 2>/dev/null || true
  systemctl disable --now "${durable_worker_units[@]}" 2>/dev/null || true
  systemctl stop "${worker_units[@]}" 2>/dev/null || true
  if [[ "$switched" -eq 1 ]]; then
    systemctl stop "${KOLIBRI_INSTANCE}-frontend.service" \
      "${KOLIBRI_INSTANCE}-backend.service" || true
    rm -f "$current_link"
    [[ ! -L "$backup_dir/previous-current" ]] ||
      cp -a "$backup_dir/previous-current" "$current_link"
    restore_optional_file() {
      local backup_name="$1"
      local destination="$2"
      rm -f -- "$destination"
      if [[ -f "$backup_dir/$backup_name" ]]; then
        cp -a "$backup_dir/$backup_name" "$destination"
      elif [[ ! -f "$backup_dir/$backup_name.absent" ]]; then
        echo "install_error=rollback_evidence_missing file=$backup_name" >&2
        return 1
      fi
    }
    restore_optional_file backend.service "$backend_unit"
    restore_optional_file frontend.service "$frontend_unit"
    restore_optional_file product-worker.service "$product_worker_unit"
    restore_optional_file provider-worker.service "$provider_worker_unit"
    restore_optional_file audit-worker.service "$audit_worker_unit"
    restore_optional_file release-monitor.service "$monitor_unit"
    restore_optional_file release-monitor.timer "$monitor_timer"
    restore_optional_file database-backup.service "$backup_service_unit"
    restore_optional_file database-backup.timer "$backup_timer_unit"
    restore_optional_file worker_launcher.py "$worker_launcher"
    restore_optional_file database-rehearsal.py "$database_helper"
    restore_optional_file backend.env "$backend_env_file"
    restore_optional_file release.env "$release_env_file"
    restore_optional_file frontend.env "$frontend_env_file"
    restore_optional_file workers.env "$workers_env_file"
    if [[ "$KOLIBRI_ENABLE_NGINX" == "true" ]]; then
      restore_optional_file nginx.conf "$nginx_site"
    fi
    systemctl daemon-reload
    systemctl restart "${KOLIBRI_INSTANCE}-backend.service" \
      "${KOLIBRI_INSTANCE}-frontend.service" || true
    restore_previous_durable_workers
    restore_previous_monitor
    restore_previous_backup_timer
    if [[ "$KOLIBRI_ENABLE_NGINX" == "true" ]]; then
      nginx -t && systemctl reload nginx || true
    fi
  elif [[ "$services_stopped" -eq 1 ]]; then
    systemctl restart "${KOLIBRI_INSTANCE}-backend.service" \
      "${KOLIBRI_INSTANCE}-frontend.service" || true
    restore_previous_durable_workers
    restore_previous_monitor
    restore_previous_backup_timer
  fi
  echo "install_error=activation_failed rollback=$switched backup=$backup_dir" >&2
  exit "$exit_code"
}
trap rollback ERR

systemctl disable --now \
  "${KOLIBRI_INSTANCE}-release-monitor.timer" 2>/dev/null || true
systemctl stop \
  "${KOLIBRI_INSTANCE}-release-monitor.service" 2>/dev/null || true
systemctl disable --now \
  "${KOLIBRI_INSTANCE}-database-backup.timer" 2>/dev/null || true
systemctl stop \
  "${KOLIBRI_INSTANCE}-database-backup.service" 2>/dev/null || true
systemctl disable --now "${durable_worker_units[@]}" 2>/dev/null || true
systemctl stop "${worker_units[@]}" 2>/dev/null || true
systemctl stop "${KOLIBRI_INSTANCE}-frontend.service" \
  "${KOLIBRI_INSTANCE}-backend.service" 2>/dev/null || true
services_stopped=1
python3 "$script_dir/install-contract.py" normalize-database \
  --data-root "$data_root" \
  --service-uid "$service_uid" \
  --service-gid "$service_gid"

switched=1
rm -f "$current_link.new"
ln -s "releases/$release_id/runtime" "$current_link.new"
mv -Tf "$current_link.new" "$current_link"
if [[ -f "$backend_env_file.new" ]]; then
  mv -f "$backend_env_file.new" "$backend_env_file"
fi
mv -f "$release_env_file.new" "$release_env_file"
mv -f "$frontend_env_file.new" "$frontend_env_file"
mv -f "$workers_env_file.new" "$workers_env_file"
mv -f "$backend_unit.new" "$backend_unit"
mv -f "$frontend_unit.new" "$frontend_unit"
mv -f "$product_worker_unit.new" "$product_worker_unit"
mv -f "$provider_worker_unit.new" "$provider_worker_unit"
mv -f "$audit_worker_unit.new" "$audit_worker_unit"
mv -f "$monitor_unit.new" "$monitor_unit"
mv -f "$monitor_timer.new" "$monitor_timer"
mv -f "$backup_service_unit.new" "$backup_service_unit"
mv -f "$backup_timer_unit.new" "$backup_timer_unit"
mv -f "$worker_launcher.new" "$worker_launcher"
mv -f "$database_helper.new" "$database_helper"
if [[ "$KOLIBRI_ENABLE_NGINX" == "true" ]]; then
  mv -f "$nginx_site.new" "$nginx_site"
fi

systemctl daemon-reload
systemctl reset-failed \
  "${KOLIBRI_INSTANCE}-backend.service" \
  "${KOLIBRI_INSTANCE}-frontend.service" \
  "${KOLIBRI_INSTANCE}-product-run-worker.service" \
  "${KOLIBRI_INSTANCE}-provider-enrollment-worker.service" \
  "${KOLIBRI_INSTANCE}-database-backup.service" \
  "${KOLIBRI_INSTANCE}-release-monitor.service" 2>/dev/null || true
systemd-analyze verify \
  "$backend_unit" \
  "$frontend_unit" \
  "$product_worker_unit" \
  "$provider_worker_unit" \
  "$audit_worker_unit" \
  "$monitor_unit" \
  "$monitor_timer" \
  "$backup_service_unit" \
  "$backup_timer_unit"
systemctl enable "${KOLIBRI_INSTANCE}-backend.service" \
  "${KOLIBRI_INSTANCE}-frontend.service"
systemctl disable --now "${durable_worker_units[@]}"
systemctl stop "${worker_units[@]}" 2>/dev/null || true
for durable_worker_unit in "${durable_worker_units[@]}"; do
  if systemctl is-enabled --quiet "$durable_worker_unit"; then
    echo "install_error=worker_enabled_before_explicit_preflight unit=$durable_worker_unit" >&2
    exit 3
  fi
done
if [[ "$KOLIBRI_ENABLE_NGINX" == "true" ]]; then
  nginx -t
fi
systemctl restart "${KOLIBRI_INSTANCE}-backend.service"

wait_for_url() {
  local url="$1"
  shift
  local deadline=$((SECONDS + KOLIBRI_HEALTH_TIMEOUT_SECONDS))
  until curl -fsS --max-time 3 "$@" "$url" >/dev/null; do
    (( SECONDS < deadline )) || return 1
    sleep 1
  done
}

release_health_is_exact() {
  local url="$1"
  shift
  curl -fsS --max-time 5 "$@" "$url" |
    python3 -c '
import json
import sys

payload = json.load(sys.stdin)
expected = {
    "status": "ok",
    "service": "kolibri-v3",
    "releaseId": sys.argv[1],
    "releaseCommit": sys.argv[2],
}
assert payload == expected
' "$release_id" "$release_commit"
}

wait_for_release_health() {
  local url="$1"
  shift
  local deadline=$((SECONDS + KOLIBRI_HEALTH_TIMEOUT_SECONDS))
  until release_health_is_exact "$url" "$@"; do
    (( SECONDS < deadline )) || return 1
    sleep 1
  done
}

wait_for_url "http://127.0.0.1:$KOLIBRI_BACKEND_PORT/v1/live"
wait_for_release_health \
  "http://127.0.0.1:$KOLIBRI_BACKEND_PORT/v1/health"
product_worker_status=required_pending
provider_worker_status=disabled_by_configuration
preflight_worker_configuration product "$workers_env_file"
systemctl start "${KOLIBRI_INSTANCE}-product-run-worker.service"
systemctl is-active --quiet \
  "${KOLIBRI_INSTANCE}-product-run-worker.service"
systemctl enable "${KOLIBRI_INSTANCE}-product-run-worker.service"
product_worker_status=enabled_active
wait_for_release_health \
  "http://127.0.0.1:$KOLIBRI_BACKEND_PORT/v1/ready"
systemctl restart "${KOLIBRI_INSTANCE}-frontend.service"
wait_for_url "http://127.0.0.1:$KOLIBRI_FRONTEND_PORT/api/live"
wait_for_url "http://127.0.0.1:$KOLIBRI_FRONTEND_PORT/app"
wait_for_release_health \
  "http://127.0.0.1:$KOLIBRI_FRONTEND_PORT/api/health"
if [[ "$KOLIBRI_ENABLE_NGINX" == "true" ]]; then
  systemctl reload nginx
  wait_for_url \
    "https://$KOLIBRI_DOMAIN/livez" \
    --resolve "$KOLIBRI_DOMAIN:443:127.0.0.1"
  wait_for_release_health \
    "https://$KOLIBRI_DOMAIN/readyz" \
    --resolve "$KOLIBRI_DOMAIN:443:127.0.0.1"
  wait_for_release_health \
    "https://$KOLIBRI_DOMAIN/healthz" \
    --resolve "$KOLIBRI_DOMAIN:443:127.0.0.1"
fi

if [[ "$KOLIBRI_ENABLE_PROVIDER_WORKER" == "true" ]]; then
  preflight_worker_configuration provider "$workers_env_file"
  systemctl start "${KOLIBRI_INSTANCE}-provider-enrollment-worker.service"
  systemctl is-active --quiet \
    "${KOLIBRI_INSTANCE}-provider-enrollment-worker.service"
  systemctl enable "${KOLIBRI_INSTANCE}-provider-enrollment-worker.service"
  provider_worker_status=enabled_active
fi
systemctl stop \
  "${KOLIBRI_INSTANCE}-estimate-reconciliation-audit.service" \
  2>/dev/null || true
systemctl start "${KOLIBRI_INSTANCE}-database-backup.service"
[[ "$(
  systemctl show \
    --property=Result \
    --value \
    "${KOLIBRI_INSTANCE}-database-backup.service"
)" == "success" ]] || {
  echo "install_error=database_backup_failed" >&2
  exit 3
}
systemctl enable --now "${KOLIBRI_INSTANCE}-database-backup.timer"
systemctl is-active --quiet "${KOLIBRI_INSTANCE}-database-backup.timer"
backup_status=enabled_active
systemctl start "${KOLIBRI_INSTANCE}-release-monitor.service"
[[ "$(
  systemctl show \
    --property=Result \
    --value \
    "${KOLIBRI_INSTANCE}-release-monitor.service"
)" == "success" ]] || {
  echo "install_error=release_monitor_failed" >&2
  exit 3
}
systemctl enable --now "${KOLIBRI_INSTANCE}-release-monitor.timer"
systemctl is-active --quiet "${KOLIBRI_INSTANCE}-release-monitor.timer"
monitor_status=enabled_active
switched=0
trap - ERR

echo "install_status=ok"
echo "instance=$KOLIBRI_INSTANCE"
echo "release=$release_id"
echo "commit=$release_commit"
echo "public_url=$allowed_origin/app"
echo "product_worker=$product_worker_status"
echo "provider_worker=$provider_worker_status"
echo "reconciliation_audit=installed_not_started"
echo "release_monitor=$monitor_status"
echo "database_backup=$backup_status"
echo "developer_execution=externalized_home_provider_worker_plane"
echo "trusted_agent_plane=kolibri_agent_host"
echo "embedded_developer_agent=forbidden_in_production"
echo "backup=$backup_dir"
