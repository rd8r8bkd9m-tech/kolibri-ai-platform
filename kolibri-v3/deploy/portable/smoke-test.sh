#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
temporary_root="${TMPDIR:-/tmp}"
minimum_free_kib="${KOLIBRI_SMOKE_MIN_FREE_KIB:-10485760}"
available_kib="$(
  df -Pk "$temporary_root" | awk 'NR == 2 { print $4 }'
)"
[[ "$minimum_free_kib" =~ ^[0-9]+$ &&
  "$available_kib" =~ ^[0-9]+$ ]] || {
  echo "smoke_error=disk_capacity_probe_failed" >&2
  exit 2
}
(( available_kib >= minimum_free_kib )) || {
  echo "smoke_error=insufficient_disk available_kib=$available_kib minimum_kib=$minimum_free_kib" >&2
  exit 2
}
work_root="$(mktemp -d "$temporary_root/kolibri-v3-smoke.XXXXXX")"
work_root="$(cd -- "$work_root" && pwd -P)"
backend_port="${KOLIBRI_SMOKE_BACKEND_PORT:-18082}"
frontend_port="${KOLIBRI_SMOKE_FRONTEND_PORT:-13103}"
backend_pid=""
frontend_pid=""
product_worker_pid=""
release_archive="${1:-}"

cleanup() {
  [[ -z "$frontend_pid" ]] || kill "$frontend_pid" 2>/dev/null || true
  [[ -z "$product_worker_pid" ]] ||
    kill "$product_worker_pid" 2>/dev/null || true
  [[ -z "$backend_pid" ]] || kill "$backend_pid" 2>/dev/null || true
  rm -rf -- "$work_root"
}
trap cleanup EXIT

for command_name in curl node npm python3 tar; do
  command -v "$command_name" >/dev/null ||
    { echo "smoke_error=missing_command command=$command_name" >&2; exit 2; }
done

[[ -n "$release_archive" ]] || {
  echo "smoke_error=release_archive_required" >&2
  echo "usage: $0 /absolute/path/kolibri-v3-<commit>-<digest>.tar.gz" >&2
  exit 2
}
[[ "$release_archive" = /* && -f "$release_archive" ]] || {
  echo "smoke_error=release_archive_invalid path=$release_archive" >&2
  exit 2
}

release_verification="$(
  python3 "$script_dir/release-manifest.py" verify --archive "$release_archive"
)"
printf '%s\n' "$release_verification"
release_id="$(
  awk -F= '$1 == "release_id" {print $2; exit}' <<<"$release_verification"
)"
release_commit="$(
  awk -F= '$1 == "release_commit" {print $2; exit}' <<<"$release_verification"
)"
release_migration_max="$(
  awk -F= '$1 == "release_migration_max" {print $2; exit}' \
    <<<"$release_verification"
)"
[[ "$release_id" =~ ^kolibri-v3-[0-9a-f]{12}-[0-9a-f]{12}$ &&
  "$release_commit" =~ ^[0-9a-f]{40}$ &&
  "$release_migration_max" =~ ^[0-9]{3,}$ ]] || {
  echo "smoke_error=release_identity_invalid" >&2
  exit 3
}
(( 10#$release_migration_max >= 44 )) || {
  echo "smoke_error=required_release_migrations_missing" >&2
  exit 3
}
tar -C "$work_root" -xzf "$release_archive"
project_root="$work_root/kolibri-v3"
[[ -f "$project_root/package.json" &&
  -f "$project_root/backend/app/main.py" ]] || {
  echo "smoke_error=canonical_v3_payload_missing" >&2
  exit 3
}

python3 -m venv "$project_root/backend/venv"
"$project_root/backend/venv/bin/python" -m pip install \
  --disable-pip-version-check -r "$project_root/backend/requirements.txt"
(
  cd "$project_root"
  npm ci
  npm run typecheck
  npm test
  KOLIBRI_RELEASE_ID="$release_id" \
  KOLIBRI_RELEASE_COMMIT="$release_commit" \
    npm run build
)

mkdir -p "$project_root/runtime/frontend/.next"
mkdir -p "$work_root/home"
cp -a "$project_root/.next/standalone/." "$project_root/runtime/frontend/"
cp -a "$project_root/.next/static" \
  "$project_root/runtime/frontend/.next/static"
cp -a "$project_root/public" "$project_root/runtime/frontend/public"

KOLIBRI_V3_ENV=production \
KOLIBRI_V3_DATABASE_URL="sqlite:///$work_root/kolibri-v3.db" \
KOLIBRI_V3_ALLOWED_ORIGINS="https://smoke.kolibri.invalid" \
KOLIBRI_V3_COOKIE_SECURE=true \
KOLIBRI_V3_CSRF_SECRET="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" \
KOLIBRI_V3_DIRECT_MODEL_RUNTIME=false \
KOLIBRI_V3_DEVELOPER_AGENT_ENABLED=false \
KOLIBRI_V3_REQUIRE_PRODUCT_WORKER=true \
KOLIBRI_V3_WORKER_HEARTBEAT_TTL_SECONDS=30 \
KOLIBRI_V3_PRODUCT_AUTHORITY_ID=authority_smoke01 \
KOLIBRI_V3_PRODUCT_AUTHORITY_EPOCH=1 \
KOLIBRI_V3_PRODUCT_AUTHORITY_PLACEMENT_ID=placement_smoke01 \
KOLIBRI_V3_PRODUCT_AUTHORIZATION_DECISION_ID=decision_smoke01 \
KOLIBRI_V3_PRODUCT_AUTHORITY_CAPABILITIES=product.goal.initialize.request,product.run.execute.request,product.provider.enrollment.request,product.developer.run.execute.request \
KOLIBRI_RELEASE_ID="$release_id" \
KOLIBRI_RELEASE_COMMIT="$release_commit" \
"$project_root/backend/venv/bin/python" -m uvicorn app.main:app \
  --app-dir "$project_root/backend" --host 127.0.0.1 --port "$backend_port" \
  >"$work_root/backend.log" 2>&1 &
backend_pid=$!

for _ in $(seq 1 60); do
  curl -fsS --max-time 2 "http://127.0.0.1:$backend_port/v1/live" \
    >/dev/null 2>&1 &&
    break
  kill -0 "$backend_pid" 2>/dev/null ||
    { cat "$work_root/backend.log" >&2; exit 3; }
  sleep 1
done
curl -fsS --max-time 5 "http://127.0.0.1:$backend_port/v1/health" |
  python3 -c \
    'import json, sys; payload=json.load(sys.stdin); assert payload == {"status": "ok", "service": "kolibri-v3", "releaseId": sys.argv[1], "releaseCommit": sys.argv[2]}' \
  "$release_id" "$release_commit" ||
  { cat "$work_root/backend.log" >&2; exit 3; }

chmod 600 "$work_root/kolibri-v3.db"
for sidecar_suffix in -wal -shm; do
  sidecar="$work_root/kolibri-v3.db$sidecar_suffix"
  [[ ! -e "$sidecar" ]] || chmod 600 "$sidecar"
done
worker_lock_dir="$work_root/product-worker-lock"
mkdir -m 700 "$worker_lock_dir"
(
  cd "$project_root/backend"
  exec env \
    KOLIBRI_V3_ENV=production \
    KOLIBRI_V3_DATABASE_URL="sqlite:///$work_root/kolibri-v3.db" \
    KOLIBRI_WORKER_EXPECTED_DATABASE_URL="sqlite:///$work_root/kolibri-v3.db" \
    KOLIBRI_WORKER_LOCK_PATH="$worker_lock_dir/owner.lock" \
    KOLIBRI_V3_ALLOWED_ORIGINS="https://smoke.kolibri.invalid" \
    KOLIBRI_V3_COOKIE_SECURE=true \
    KOLIBRI_V3_CSRF_SECRET="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" \
    KOLIBRI_V3_DIRECT_MODEL_RUNTIME=false \
    KOLIBRI_V3_DEVELOPER_AGENT_ENABLED=false \
    KOLIBRI_V3_REQUIRE_PRODUCT_WORKER=true \
    KOLIBRI_V3_WORKER_HEARTBEAT_TTL_SECONDS=30 \
    KOLIBRI_V3_PRODUCT_AUTHORITY_ID=authority_smoke01 \
    KOLIBRI_V3_PRODUCT_AUTHORITY_EPOCH=1 \
    KOLIBRI_V3_PRODUCT_AUTHORITY_PLACEMENT_ID=placement_smoke01 \
    KOLIBRI_V3_PRODUCT_AUTHORIZATION_DECISION_ID=decision_smoke01 \
    KOLIBRI_V3_PRODUCT_AUTHORITY_CAPABILITIES=product.goal.initialize.request,product.run.execute.request,product.provider.enrollment.request,product.developer.run.execute.request \
    KOLIBRI_V3_HOME_PRODUCT_COMMAND_URL=http://127.0.0.1:9/v1/runtime/product-text-runs \
    KOLIBRI_V3_HOME_PRODUCT_GOAL_COMMAND_URL=http://127.0.0.1:9/v1/runtime/product-goal-initializations \
    KOLIBRI_V3_HOME_PRODUCT_PROVIDER_COMMAND_URL=http://127.0.0.1:9/v1/runtime/product-provider-enrollment-intents \
    KOLIBRI_V3_HOME_PRODUCT_COMMAND_TOKEN=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
    KOLIBRI_V3_HOME_PRODUCT_IDENTITY_HMAC_KEY=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb \
    KOLIBRI_RELEASE_ID="$release_id" \
    KOLIBRI_RELEASE_COMMIT="$release_commit" \
    "$project_root/backend/venv/bin/python" \
    "$project_root/deploy/workers/worker_launcher.py" product-run
) >"$work_root/product-worker.log" 2>&1 &
product_worker_pid=$!

for _ in $(seq 1 60); do
  curl -fsS --max-time 2 "http://127.0.0.1:$backend_port/v1/ready" \
    >/dev/null 2>&1 &&
    break
  kill -0 "$product_worker_pid" 2>/dev/null ||
    { cat "$work_root/product-worker.log" >&2; exit 3; }
  sleep 1
done
curl -fsS --max-time 5 "http://127.0.0.1:$backend_port/v1/ready" |
  python3 -c \
    'import json, sys; payload=json.load(sys.stdin); assert payload == {"status": "ok", "service": "kolibri-v3", "releaseId": sys.argv[1], "releaseCommit": sys.argv[2]}' \
    "$release_id" "$release_commit" ||
  { cat "$work_root/product-worker.log" >&2; exit 3; }

(
  cd "$project_root/runtime/frontend"
  HOME="$work_root/home" \
  NODE_ENV=production \
  HOSTNAME=127.0.0.1 \
  PORT="$frontend_port" \
  KOLIBRI_V3_BACKEND_URL="http://127.0.0.1:$backend_port" \
  KOLIBRI_RELEASE_ID="$release_id" \
  KOLIBRI_RELEASE_COMMIT="$release_commit" \
  node server.js
) >"$work_root/frontend.log" 2>&1 &
frontend_pid=$!

for _ in $(seq 1 60); do
  curl -fsS --max-time 2 "http://127.0.0.1:$frontend_port/api/live" \
    >/dev/null 2>&1 &&
    break
  kill -0 "$frontend_pid" 2>/dev/null ||
    { cat "$work_root/frontend.log" >&2; exit 3; }
  sleep 1
done
curl -fsS --max-time 10 "http://127.0.0.1:$frontend_port/app" >/dev/null ||
  { cat "$work_root/frontend.log" >&2; exit 3; }
curl -fsSI --max-time 10 "http://127.0.0.1:$frontend_port/app" |
  python3 -c '
import sys

expected = sys.argv[1]
headers = {}
for line in sys.stdin:
    if ":" not in line:
        continue
    name, value = line.split(":", 1)
    headers[name.strip().lower()] = value.strip()
assert headers.get("x-kolibri-release") == expected
' "$release_id" ||
  { cat "$work_root/frontend.log" >&2; exit 3; }

curl -fsS --max-time 5 "http://127.0.0.1:$frontend_port/api/health" |
  python3 -c \
    'import json, sys; payload=json.load(sys.stdin); assert payload == {"status": "ok", "service": "kolibri-v3", "releaseId": sys.argv[1], "releaseCommit": sys.argv[2]}' \
    "$release_id" "$release_commit"

curl -fsS --max-time 5 \
  "http://127.0.0.1:$frontend_port/api/v3/session" >/dev/null

echo "smoke_status=ok"
echo "backend_url=http://127.0.0.1:$backend_port/v1/health"
echo "frontend_url=http://127.0.0.1:$frontend_port/app"
