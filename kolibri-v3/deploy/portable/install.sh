#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "install_error=root_required" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
source_root="$(cd -- "$script_dir/../.." && pwd -P)"
config_file="${1:-"$script_dir/config.env"}"
[[ -f "$config_file" ]] || {
  echo "install_error=config_missing path=$config_file" >&2
  exit 2
}

# shellcheck disable=SC1090
source "$config_file"

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
KOLIBRI_NGINX_SITE="${
  KOLIBRI_NGINX_SITE:-/etc/nginx/sites-enabled/${KOLIBRI_INSTANCE}.conf
}"
KOLIBRI_DIRECT_MODEL_RUNTIME="${KOLIBRI_DIRECT_MODEL_RUNTIME:-true}"
KOLIBRI_CODEX_BIN="${KOLIBRI_CODEX_BIN:-/usr/local/bin/codex}"
KOLIBRI_REQUIRE_MIMO="${KOLIBRI_REQUIRE_MIMO:-true}"
KOLIBRI_MIMO_BASE_URL="${KOLIBRI_MIMO_BASE_URL:-http://127.0.0.1:39231}"
KOLIBRI_MIMO_CLI_PATH="${KOLIBRI_MIMO_CLI_PATH:-/usr/local/bin/mimo}"
KOLIBRI_RUN_FRONTEND_TESTS="${KOLIBRI_RUN_FRONTEND_TESTS:-true}"
KOLIBRI_HEALTH_TIMEOUT_SECONDS="${KOLIBRI_HEALTH_TIMEOUT_SECONDS:-90}"

[[ "$KOLIBRI_INSTANCE" =~ ^[a-z0-9][a-z0-9-]{1,47}$ ]] ||
  { echo "install_error=invalid_instance" >&2; exit 2; }
[[ "$KOLIBRI_DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] ||
  { echo "install_error=invalid_domain" >&2; exit 2; }
[[ "$KOLIBRI_PUBLIC_SCHEME" == "http" || "$KOLIBRI_PUBLIC_SCHEME" == "https" ]] ||
  { echo "install_error=invalid_public_scheme" >&2; exit 2; }
for port in "$KOLIBRI_BACKEND_PORT" "$KOLIBRI_FRONTEND_PORT"; do
  [[ "$port" =~ ^[0-9]+$ ]] && (( port >= 1024 && port <= 65535 )) ||
    { echo "install_error=invalid_port value=$port" >&2; exit 2; }
done
[[ "$KOLIBRI_BACKEND_PORT" != "$KOLIBRI_FRONTEND_PORT" ]] ||
  { echo "install_error=ports_must_differ" >&2; exit 2; }

for path in "$KOLIBRI_INSTALL_ROOT" "$KOLIBRI_CONFIG_ROOT" "$KOLIBRI_BACKUP_ROOT"; do
  [[ "$path" == /* && "$path" != "/" ]] ||
    { echo "install_error=unsafe_path value=$path" >&2; exit 2; }
done

id "$KOLIBRI_SERVICE_USER" >/dev/null 2>&1 ||
  { echo "install_error=service_user_missing user=$KOLIBRI_SERVICE_USER" >&2; exit 3; }
service_group="$(id -gn "$KOLIBRI_SERVICE_USER")"
service_home="$(getent passwd "$KOLIBRI_SERVICE_USER" | cut -d: -f6)"
[[ -n "$service_home" && -d "$service_home" ]] ||
  { echo "install_error=service_home_missing user=$KOLIBRI_SERVICE_USER" >&2; exit 3; }

for command_name in bash curl flock git node npm python3 runuser sha256sum systemctl tar; do
  command -v "$command_name" >/dev/null ||
    { echo "install_error=missing_command command=$command_name" >&2; exit 3; }
done
node_major="$(node -p 'Number(process.versions.node.split(\".\")[0])')"
(( node_major >= 20 )) ||
  { echo "install_error=node_too_old version=$(node --version)" >&2; exit 3; }
python3 -c 'import venv' >/dev/null 2>&1 ||
  { echo "install_error=python_venv_unavailable" >&2; exit 3; }

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
  [[ "$KOLIBRI_NGINX_SITE" == /etc/nginx/sites-enabled/* &&
    "$KOLIBRI_NGINX_SITE" != */../* ]] ||
    { echo "install_error=unsafe_nginx_site path=$KOLIBRI_NGINX_SITE" >&2; exit 2; }
  command -v nginx >/dev/null ||
    { echo "install_error=nginx_missing" >&2; exit 3; }
  : "${KOLIBRI_TLS_CERTIFICATE:?KOLIBRI_TLS_CERTIFICATE is required}"
  : "${KOLIBRI_TLS_CERTIFICATE_KEY:?KOLIBRI_TLS_CERTIFICATE_KEY is required}"
  [[ -r "$KOLIBRI_TLS_CERTIFICATE" && -r "$KOLIBRI_TLS_CERTIFICATE_KEY" ]] ||
    { echo "install_error=tls_files_unreadable" >&2; exit 3; }
fi

test -f "$source_root/package-lock.json"
test -f "$source_root/backend/requirements.txt"
test -f "$source_root/deploy/portable/config.env.example"

source_digest="$(
  {
    find "$source_root" -type f \
      ! -path "$source_root/node_modules/*" \
      ! -path "$source_root/.next/*" \
      ! -path "$source_root/backend/venv/*" \
      ! -path "$source_root/backend/var/*" \
      ! -path "$source_root/var/*" \
      ! -path "$source_root/output/*" \
      ! -path "$source_root/.design-qa/*" \
      ! -name '.env*.local' \
      -print0 |
      LC_ALL=C sort -z |
      xargs -0 sha256sum
  } | sha256sum | awk '{print $1}'
)"
release_id="src-${source_digest:0:12}"
release_root="$KOLIBRI_INSTALL_ROOT/releases/$release_id"
build_root="$release_root/build"
runtime_root="$release_root/runtime"
current_link="$KOLIBRI_INSTALL_ROOT/current"
data_root="$KOLIBRI_INSTALL_ROOT/var"
backend_env_file="$KOLIBRI_CONFIG_ROOT/backend.env"
frontend_env_file="$KOLIBRI_CONFIG_ROOT/frontend.env"
backend_unit="/etc/systemd/system/${KOLIBRI_INSTANCE}-backend.service"
frontend_unit="/etc/systemd/system/${KOLIBRI_INSTANCE}-frontend.service"
nginx_site="$KOLIBRI_NGINX_SITE"
backup_dir="$KOLIBRI_BACKUP_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-$release_id"
lock_file="/run/lock/${KOLIBRI_INSTANCE}-release.lock"
switched=0

exec 9>"$lock_file"
flock -n 9 ||
  { echo "install_error=release_locked instance=$KOLIBRI_INSTANCE" >&2; exit 4; }

install -d -o "$KOLIBRI_SERVICE_USER" -g "$service_group" -m 755 \
  "$KOLIBRI_INSTALL_ROOT" "$KOLIBRI_INSTALL_ROOT/releases" "$data_root"
install -d -o root -g root -m 700 "$KOLIBRI_BACKUP_ROOT" "$KOLIBRI_CONFIG_ROOT"
[[ ! -e "$release_root" ]] ||
  { echo "install_error=release_exists release=$release_id" >&2; exit 5; }
install -d -o "$KOLIBRI_SERVICE_USER" -g "$service_group" -m 755 \
  "$build_root" "$runtime_root"

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
  -C "$source_root" -cf - . |
  tar -C "$build_root" -xf -
chown -R "$KOLIBRI_SERVICE_USER:$service_group" "$release_root"

run_as_service() {
  runuser -u "$KOLIBRI_SERVICE_USER" -- env HOME="$service_home" "$@"
}

run_as_service python3 -m venv "$build_root/backend/venv"
run_as_service "$build_root/backend/venv/bin/python" -m pip install \
  --disable-pip-version-check -r "$build_root/backend/requirements.txt"
run_as_service bash -lc \
  "cd '$build_root/backend' && ./venv/bin/python -c 'import app.main'"
run_as_service bash -lc "cd '$build_root' && npm ci"
run_as_service bash -lc "cd '$build_root' && npm run typecheck"
if [[ "$KOLIBRI_RUN_FRONTEND_TESTS" == "true" ]]; then
  run_as_service bash -lc "cd '$build_root' && npm test"
fi
run_as_service bash -lc "cd '$build_root' && npm run build"

install -d -o "$KOLIBRI_SERVICE_USER" -g "$service_group" -m 755 \
  "$runtime_root/frontend" "$runtime_root/frontend/.next"
cp -a "$build_root/.next/standalone/." "$runtime_root/frontend/"
cp -a "$build_root/.next/static" "$runtime_root/frontend/.next/static"
cp -a "$build_root/public" "$runtime_root/frontend/public"
ln -s ../build/backend "$runtime_root/backend"
chown -h "$KOLIBRI_SERVICE_USER:$service_group" "$runtime_root/backend"

install -d -o root -g root -m 700 "$backup_dir"
[[ ! -L "$current_link" ]] || cp -a "$current_link" "$backup_dir/previous-current"
[[ ! -f "$backend_unit" ]] || cp -a "$backend_unit" "$backup_dir/backend.service"
[[ ! -f "$frontend_unit" ]] || cp -a "$frontend_unit" "$backup_dir/frontend.service"
[[ ! -f "$nginx_site" ]] || cp -a "$nginx_site" "$backup_dir/nginx.conf"
[[ ! -f "$backend_env_file" ]] ||
  cp -a "$backend_env_file" "$backup_dir/backend.env"
[[ ! -f "$frontend_env_file" ]] ||
  cp -a "$frontend_env_file" "$backup_dir/frontend.env"
if [[ -f "$data_root/kolibri-v3.db" ]]; then
  "$build_root/backend/venv/bin/python" - "$data_root/kolibri-v3.db" "$backup_dir/kolibri-v3.db" <<'PY'
import sqlite3
import sys
source = sqlite3.connect(sys.argv[1])
destination = sqlite3.connect(sys.argv[2])
source.backup(destination)
destination.close()
source.close()
PY
  chmod 600 "$backup_dir/kolibri-v3.db"
fi

csrf_file="$data_root/.csrf-secret"
if [[ ! -s "$csrf_file" ]]; then
  umask 077
  python3 -c 'import secrets; print(secrets.token_hex(32))' > "$csrf_file"
  chown "$KOLIBRI_SERVICE_USER:$service_group" "$csrf_file"
fi
csrf_value="$(tr -d '\r\n' < "$csrf_file")"
allowed_origin="$KOLIBRI_PUBLIC_SCHEME://$KOLIBRI_DOMAIN"

umask 077
cat > "$backend_env_file.new" <<EOF
HOME=$service_home
PATH=$(dirname "$KOLIBRI_CODEX_BIN"):/usr/local/bin:/usr/bin:/bin
KOLIBRI_V3_ENV=production
KOLIBRI_V3_DATABASE_URL=sqlite:///$data_root/kolibri-v3.db
KOLIBRI_V3_ALLOWED_ORIGINS=$allowed_origin
KOLIBRI_V3_COOKIE_SECURE=$([[ "$KOLIBRI_PUBLIC_SCHEME" == "https" ]] && echo true || echo false)
KOLIBRI_V3_CSRF_SECRET=$csrf_value
KOLIBRI_V3_PRODUCT_AUTHORITY_ID=authority_product_data_v1
KOLIBRI_V3_PRODUCT_AUTHORITY_EPOCH=1
KOLIBRI_V3_PRODUCT_AUTHORITY_PLACEMENT_ID=placement_product_backend
KOLIBRI_V3_PRODUCT_AUTHORIZATION_DECISION_ID=decision_product_data_v1
KOLIBRI_V3_DIRECT_MODEL_RUNTIME=$KOLIBRI_DIRECT_MODEL_RUNTIME
KOLIBRI_V3_DEVELOPER_AGENT_ENABLED=false
KOLIBRI_V3_MIMO_BASE_URL=$KOLIBRI_MIMO_BASE_URL
KOLIBRI_V3_MIMO_CLI_PATH=$KOLIBRI_MIMO_CLI_PATH
EOF

cat > "$frontend_env_file.new" <<EOF
HOME=$service_home
NODE_ENV=production
KOLIBRI_V3_BACKEND_URL=http://127.0.0.1:$KOLIBRI_BACKEND_PORT
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
WorkingDirectory=$current_link/backend
ExecStart=$current_link/backend/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port $KOLIBRI_BACKEND_PORT
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
    location = /healthz { access_log off; default_type text/plain; return 200 "ok\n"; }
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

rollback() {
  local exit_code=$?
  trap - ERR
  if [[ "$switched" -eq 1 ]]; then
    systemctl stop "${KOLIBRI_INSTANCE}-frontend.service" \
      "${KOLIBRI_INSTANCE}-backend.service" || true
    rm -f "$current_link"
    [[ ! -L "$backup_dir/previous-current" ]] ||
      cp -a "$backup_dir/previous-current" "$current_link"
    [[ ! -f "$backup_dir/backend.service" ]] ||
      cp -a "$backup_dir/backend.service" "$backend_unit"
    [[ -f "$backup_dir/backend.service" ]] || rm -f "$backend_unit"
    [[ ! -f "$backup_dir/frontend.service" ]] ||
      cp -a "$backup_dir/frontend.service" "$frontend_unit"
    [[ -f "$backup_dir/frontend.service" ]] || rm -f "$frontend_unit"
    [[ ! -f "$backup_dir/nginx.conf" ]] ||
      cp -a "$backup_dir/nginx.conf" "$nginx_site"
    [[ -f "$backup_dir/nginx.conf" ]] || rm -f "$nginx_site"
    if [[ -f "$backup_dir/backend.env" ]]; then
      cp -a "$backup_dir/backend.env" "$backend_env_file"
    else
      rm -f "$backend_env_file"
    fi
    if [[ -f "$backup_dir/frontend.env" ]]; then
      cp -a "$backup_dir/frontend.env" "$frontend_env_file"
    else
      rm -f "$frontend_env_file"
    fi
    systemctl daemon-reload
    systemctl restart "${KOLIBRI_INSTANCE}-backend.service" \
      "${KOLIBRI_INSTANCE}-frontend.service" || true
    if [[ "$KOLIBRI_ENABLE_NGINX" == "true" ]]; then
      nginx -t && systemctl reload nginx || true
    fi
  fi
  echo "install_error=activation_failed rollback=$switched backup=$backup_dir" >&2
  exit "$exit_code"
}
trap rollback ERR

systemctl stop "${KOLIBRI_INSTANCE}-frontend.service" \
  "${KOLIBRI_INSTANCE}-backend.service" 2>/dev/null || true
rm -f "$current_link.new"
ln -s "releases/$release_id/runtime" "$current_link.new"
mv -Tf "$current_link.new" "$current_link"
mv -f "$backend_env_file.new" "$backend_env_file"
mv -f "$frontend_env_file.new" "$frontend_env_file"
mv -f "$backend_unit.new" "$backend_unit"
mv -f "$frontend_unit.new" "$frontend_unit"
if [[ "$KOLIBRI_ENABLE_NGINX" == "true" ]]; then
  mv -f "$nginx_site.new" "$nginx_site"
fi
switched=1

systemctl daemon-reload
systemctl enable "${KOLIBRI_INSTANCE}-backend.service" \
  "${KOLIBRI_INSTANCE}-frontend.service"
if [[ "$KOLIBRI_ENABLE_NGINX" == "true" ]]; then
  nginx -t
fi
systemctl restart "${KOLIBRI_INSTANCE}-backend.service"

wait_for_url() {
  local url="$1"
  local deadline=$((SECONDS + KOLIBRI_HEALTH_TIMEOUT_SECONDS))
  until curl -fsS --max-time 3 "$url" >/dev/null; do
    (( SECONDS < deadline )) || return 1
    sleep 1
  done
}

wait_for_url "http://127.0.0.1:$KOLIBRI_BACKEND_PORT/v1/health"
systemctl restart "${KOLIBRI_INSTANCE}-frontend.service"
wait_for_url "http://127.0.0.1:$KOLIBRI_FRONTEND_PORT/app"
if [[ "$KOLIBRI_ENABLE_NGINX" == "true" ]]; then
  systemctl reload nginx
  curl -fsS --resolve "$KOLIBRI_DOMAIN:443:127.0.0.1" \
    --max-time 15 "https://$KOLIBRI_DOMAIN/healthz" >/dev/null
fi

printf '%s\n' "$source_digest" > "$release_root/SOURCE_SHA256"
switched=0
trap - ERR

echo "install_status=ok"
echo "instance=$KOLIBRI_INSTANCE"
echo "release=$release_id"
echo "public_url=$allowed_origin/app"
echo "backup=$backup_dir"
