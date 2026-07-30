#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
v3_root="$(cd -- "${script_dir}/.." && pwd -P)"
python_bin="${KOLIBRI_V3_DEV_PYTHON:-${v3_root}/backend/venv/bin/python}"
backend_host="${KOLIBRI_V3_DEV_BACKEND_HOST:-127.0.0.1}"
backend_port="${KOLIBRI_V3_DEV_BACKEND_PORT:-8002}"
dev_owner_email="${KOLIBRI_V3_DEV_OWNER_EMAIL:-}"

if [[ -z "${dev_owner_email}" && -f "${v3_root}/.env.local" ]]; then
  while IFS='=' read -r key value; do
    if [[ "${key}" == "KOLIBRI_V3_DEV_OWNER_EMAIL" ]]; then
      dev_owner_email="${value}"
      break
    fi
  done < "${v3_root}/.env.local"
fi

if [[ ! -x "${python_bin}" ]]; then
  printf 'Kolibri V3 Python is not executable: %s\n' "${python_bin}" >&2
  exit 1
fi
if [[ -z "${dev_owner_email}" || "${dev_owner_email}" != *@* ]]; then
  printf '%s\n' \
    'KOLIBRI_V3_DEV_OWNER_EMAIL must identify the canonical V3 owner.' >&2
  exit 1
fi

# Keep both the working directory and the URL text stable. The development
# CSRF secret is derived from this exact URL, while SQLite resolves it from
# the V3 root. This prevents accidental starts against backend/var or a QA DB.
cd -- "${v3_root}"
export KOLIBRI_V3_ENV=development
export KOLIBRI_V3_DATABASE_URL='sqlite:///./var/kolibri-v3.db'
export KOLIBRI_V3_DIRECT_MODEL_RUNTIME=true
export KOLIBRI_V3_DEVELOPER_AGENT_ENABLED=true
export KOLIBRI_V3_DEVELOPER_WORKSPACE_ROOT="${v3_root}"
export KOLIBRI_V3_PROVIDER_EXECUTION_ENABLED=false
export KOLIBRI_V3_COOKIE_SECURE=false
export KOLIBRI_V3_ALLOWED_ORIGINS='http://127.0.0.1:3103,http://localhost:3103'
export KOLIBRI_V3_SESSION_COOKIE_NAME='kolibri_v3_session'
export KOLIBRI_V3_CSRF_COOKIE_NAME='kolibri_v3_csrf'
unset KOLIBRI_V3_CSRF_SECRET
unset KOLIBRI_V3_CSRF_SECRET_FILE
unset KOLIBRI_V3_BOOTSTRAP_OWNER_EMAIL
unset KOLIBRI_V3_ATTACHMENT_STORAGE_ROOT
unset KOLIBRI_RELEASE_ID
unset KOLIBRI_RELEASE_COMMIT

PYTHONPATH="${v3_root}/backend" "${python_bin}" -m app.dev_preflight \
  --expected-database "${v3_root}/var/kolibri-v3.db" \
  --expected-owner-email "${dev_owner_email}"

printf 'Kolibri V3 dev backend: %s/var/kolibri-v3.db (%s:%s)\n' \
  "${v3_root}" "${backend_host}" "${backend_port}"

exec "${python_bin}" -m uvicorn app.main:app \
  --app-dir "${v3_root}/backend" \
  --host "${backend_host}" \
  --port "${backend_port}"
