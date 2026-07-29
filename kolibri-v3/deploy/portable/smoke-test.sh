#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
project_root="$(cd -- "$script_dir/../.." && pwd -P)"
work_root="$(mktemp -d "${TMPDIR:-/tmp}/kolibri-v3-smoke.XXXXXX")"
backend_port="${KOLIBRI_SMOKE_BACKEND_PORT:-18082}"
frontend_port="${KOLIBRI_SMOKE_FRONTEND_PORT:-13103}"
backend_pid=""
frontend_pid=""

cleanup() {
  [[ -z "$frontend_pid" ]] || kill "$frontend_pid" 2>/dev/null || true
  [[ -z "$backend_pid" ]] || kill "$backend_pid" 2>/dev/null || true
  rm -rf -- "$work_root"
}
trap cleanup EXIT

for command_name in curl node npm python3 tar; do
  command -v "$command_name" >/dev/null ||
    { echo "smoke_error=missing_command command=$command_name" >&2; exit 2; }
done

tar \
  --exclude='./node_modules' \
  --exclude='./.next' \
  --exclude='./backend/venv' \
  --exclude='./backend/var' \
  --exclude='./var' \
  --exclude='./output' \
  --exclude='./.design-qa' \
  --exclude='./.env*.local' \
  --exclude='./dist' \
  -C "$project_root" -cf - . |
  tar -C "$work_root" -xf -

python3 -m venv "$work_root/backend/venv"
"$work_root/backend/venv/bin/python" -m pip install \
  --disable-pip-version-check -r "$work_root/backend/requirements.txt"
(
  cd "$work_root"
  npm ci
  npm run typecheck
  npm test
  npm run build
)

mkdir -p "$work_root/runtime/frontend/.next"
mkdir -p "$work_root/home"
cp -a "$work_root/.next/standalone/." "$work_root/runtime/frontend/"
cp -a "$work_root/.next/static" "$work_root/runtime/frontend/.next/static"
cp -a "$work_root/public" "$work_root/runtime/frontend/public"

KOLIBRI_V3_ENV=development \
KOLIBRI_V3_DATABASE_URL="sqlite:///$work_root/kolibri-v3.db" \
KOLIBRI_V3_ALLOWED_ORIGINS="http://127.0.0.1:$frontend_port" \
KOLIBRI_V3_COOKIE_SECURE=false \
KOLIBRI_V3_DIRECT_MODEL_RUNTIME=false \
KOLIBRI_V3_DEVELOPER_AGENT_ENABLED=false \
"$work_root/backend/venv/bin/python" -m uvicorn app.main:app \
  --app-dir "$work_root/backend" --host 127.0.0.1 --port "$backend_port" \
  >"$work_root/backend.log" 2>&1 &
backend_pid=$!

for _ in $(seq 1 60); do
  curl -fsS --max-time 2 "http://127.0.0.1:$backend_port/v1/health" \
    >/dev/null 2>&1 &&
    break
  kill -0 "$backend_pid" 2>/dev/null ||
    { cat "$work_root/backend.log" >&2; exit 3; }
  sleep 1
done
curl -fsS --max-time 5 "http://127.0.0.1:$backend_port/v1/health" >/dev/null ||
  { cat "$work_root/backend.log" >&2; exit 3; }

(
  cd "$work_root/runtime/frontend"
  HOME="$work_root/home" \
  NODE_ENV=production \
  HOSTNAME=127.0.0.1 \
  PORT="$frontend_port" \
  KOLIBRI_V3_BACKEND_URL="http://127.0.0.1:$backend_port" \
  node server.js
) >"$work_root/frontend.log" 2>&1 &
frontend_pid=$!

for _ in $(seq 1 60); do
  curl -fsS --max-time 2 "http://127.0.0.1:$frontend_port/app" \
    >/dev/null 2>&1 &&
    break
  kill -0 "$frontend_pid" 2>/dev/null ||
    { cat "$work_root/frontend.log" >&2; exit 3; }
  sleep 1
done
curl -fsS --max-time 10 "http://127.0.0.1:$frontend_port/app" >/dev/null ||
  { cat "$work_root/frontend.log" >&2; exit 3; }

curl -fsS --max-time 5 \
  "http://127.0.0.1:$frontend_port/api/v3/session" >/dev/null

echo "smoke_status=ok"
echo "backend_url=http://127.0.0.1:$backend_port/v1/health"
echo "frontend_url=http://127.0.0.1:$frontend_port/app"
