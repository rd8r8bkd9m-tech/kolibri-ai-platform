#!/usr/bin/env bash
set -Eeuo pipefail

archive="${1:?release archive is required}"
commit="${2:?release commit is required}"
expected_sha256="${3:?release archive sha256 is required}"

[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || {
  echo "release_error=invalid_commit" >&2
  exit 2
}
[[ "$expected_sha256" =~ ^[0-9a-f]{64}$ ]] || {
  echo "release_error=invalid_archive_sha256" >&2
  exit 2
}
[[ -f "$archive" ]] || {
  echo "release_error=archive_missing" >&2
  exit 2
}
[[ "$(sha256sum "$archive" | awk '{print $1}')" == "$expected_sha256" ]] || {
  echo "release_error=archive_digest_mismatch" >&2
  exit 3
}

release_id="git-${commit:0:12}"
release_root="/opt/kolibri-v3/releases/$release_id"
runtime_root="$release_root/runtime"
source_root="$release_root/source"
current_link="/opt/kolibri-v3/current"
backup_root="/var/backups/kolibri-v3"
backup_dir="$backup_root/$(date -u +%Y%m%dT%H%M%SZ)-$release_id"
active_nginx="/etc/nginx/sites-enabled/kolibri"
backend_unit="/etc/systemd/system/kolibri-v3-backend.service"
frontend_unit="/etc/systemd/system/kolibri-v3-frontend.service"
secret_env="/etc/kolibri-v3/backend.env"
switched=0

exec 9>/run/lock/kolibri-v3-release.lock
flock -n 9 || {
  echo "release_error=release_locked" >&2
  exit 4
}

rollback() {
  local exit_code=$?
  trap - ERR
  if [[ "$switched" -eq 1 ]]; then
    systemctl stop kolibri-v3-frontend.service kolibri-v3-backend.service || true
    rm -f "$current_link"
    [[ ! -e "$backup_dir/previous-current" ]] ||
      mv "$backup_dir/previous-current" "$current_link"
    [[ ! -d "$backup_dir/legacy-backend" ]] ||
      mv "$backup_dir/legacy-backend" /opt/kolibri-v3/backend
    [[ ! -d "$backup_dir/legacy-frontend" ]] ||
      mv "$backup_dir/legacy-frontend" /opt/kolibri-v3/frontend
    cp -a "$backup_dir/kolibri-v3-backend.service" "$backend_unit"
    cp -a "$backup_dir/kolibri-v3-frontend.service" "$frontend_unit"
    cp -a "$backup_dir/nginx-kolibri.conf" "$active_nginx"
    systemctl daemon-reload
    systemctl restart kolibri-v3-backend.service kolibri-v3-frontend.service || true
    nginx -t && systemctl reload nginx || true
  fi
  echo "release_error=install_failed rollback=$switched backup=$backup_dir" >&2
  exit "$exit_code"
}
trap rollback ERR

install -d -o root -g root -m 755 /opt/kolibri-v3/releases
install -d -o root -g root -m 700 "$backup_root"
[[ ! -e "$release_root" ]] || {
  echo "release_error=release_exists" >&2
  exit 5
}
install -d -o ladik -g ladik -m 755 "$source_root" "$runtime_root"
tar -xzf "$archive" --strip-components=1 -C "$source_root"

test -f "$source_root/package-lock.json"
test -f "$source_root/backend/requirements.txt"
test -f "$source_root/deploy/nginx-kolibriai.conf"

runuser -u ladik -- python3 -m venv "$source_root/backend/venv"
runuser -u ladik -- "$source_root/backend/venv/bin/python" -m pip install \
  --disable-pip-version-check -r "$source_root/backend/requirements.txt"
runuser -u ladik -- bash -lc \
  "cd '$source_root' && npm ci && npm run typecheck && npm test && npm run build"

install -d -o ladik -g ladik -m 755 "$runtime_root/frontend"
cp -a "$source_root/.next/standalone/." "$runtime_root/frontend/"
install -d -o ladik -g ladik -m 755 "$runtime_root/frontend/.next"
cp -a "$source_root/.next/static" "$runtime_root/frontend/.next/static"
cp -a "$source_root/public" "$runtime_root/frontend/public"
ln -s ../source/backend "$runtime_root/backend"
chown -h ladik:ladik "$runtime_root/backend"

install -d -o root -g root -m 700 "$backup_dir"
cp -a "$active_nginx" "$backup_dir/nginx-kolibri.conf"
cp -a "$backend_unit" "$backup_dir/kolibri-v3-backend.service"
cp -a "$frontend_unit" "$backup_dir/kolibri-v3-frontend.service"
sqlite3 /opt/kolibri-v3/var/kolibri-v3.db \
  ".backup '$backup_dir/kolibri-v3.db'"
chmod 600 "$backup_dir/kolibri-v3.db"
sha256sum \
  "$backup_dir/nginx-kolibri.conf" \
  "$backup_dir/kolibri-v3-backend.service" \
  "$backup_dir/kolibri-v3-frontend.service" \
  "$backup_dir/kolibri-v3.db" \
  > "$backup_dir/SHA256SUMS"

install -d -o root -g root -m 700 /etc/kolibri-v3
csrf_value="$(
  sha256sum /opt/kolibri-v3/var/.kolibri-v3-csrf-secret | awk '{print $1}'
)"
umask 077
printf 'KOLIBRI_V3_CSRF_SECRET=%s\n' "$csrf_value" > "$secret_env.new"
mv -f "$secret_env.new" "$secret_env"

systemctl stop kolibri-v3-frontend.service kolibri-v3-backend.service
[[ ! -e "$current_link" ]] || mv "$current_link" "$backup_dir/previous-current"
[[ ! -d /opt/kolibri-v3/backend ]] ||
  mv /opt/kolibri-v3/backend "$backup_dir/legacy-backend"
[[ ! -d /opt/kolibri-v3/frontend ]] ||
  mv /opt/kolibri-v3/frontend "$backup_dir/legacy-frontend"
ln -s "releases/$release_id/runtime" "$current_link.new"
mv -T "$current_link.new" "$current_link"
cp -a "$source_root/deploy/kolibri-v3-backend.service" "$backend_unit"
cp -a "$source_root/deploy/kolibri-v3-frontend.service" "$frontend_unit"
cp -a "$source_root/deploy/nginx-kolibriai.conf" "$active_nginx.new"
chmod --reference="$active_nginx" "$active_nginx.new"
chown --reference="$active_nginx" "$active_nginx.new"
mv -f "$active_nginx.new" "$active_nginx"
switched=1

systemctl daemon-reload
nginx -t
systemctl restart kolibri-v3-backend.service
for _ in $(seq 1 60); do
  curl -fsS --max-time 2 http://127.0.0.1:8002/v1/health >/dev/null && break
  sleep 1
done
curl -fsS --max-time 5 http://127.0.0.1:8002/v1/health >/dev/null

systemctl restart kolibri-v3-frontend.service
for _ in $(seq 1 60); do
  curl -fsS --max-time 2 http://127.0.0.1:3103/app >/dev/null && break
  sleep 1
done
curl -fsS --max-time 10 http://127.0.0.1:3103/app >/dev/null

systemctl reload nginx
curl -fsS --resolve kolibriai.ru:443:127.0.0.1 \
  --max-time 15 https://kolibriai.ru/healthz >/dev/null
curl -fsS --resolve kolibriai.ru:443:127.0.0.1 \
  --max-time 30 https://kolibriai.ru/app >/dev/null

chmod 600 /opt/kolibri-v3/var/kolibri-v3.db
printf '%s\n' "$commit" > "$release_root/GIT_COMMIT"
printf '%s\n' "$expected_sha256" > "$release_root/ARCHIVE_SHA256"
switched=0
trap - ERR

echo "release_id=$release_id"
echo "commit=$commit"
echo "backup=$backup_dir"
echo "public_url=https://kolibriai.ru/app"
