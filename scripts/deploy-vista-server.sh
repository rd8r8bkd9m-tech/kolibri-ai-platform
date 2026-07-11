#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v docker >/dev/null 2>&1 || { echo "Docker is required" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required" >&2; exit 1; }
[[ -f .env ]] || { echo "Create .env first: cp .env.example .env" >&2; exit 1; }

if grep -Eq '(^|=)(replace-with-|change-me|example-secret)' .env; then
  echo ".env still contains placeholder secrets" >&2
  exit 1
fi

required=(VISTA_SESSION_SECRET VISTA_OWNER_ACCESS_TOKEN VISTA_NODE_JOIN_TOKEN VISTA_NODE_SIGNING_SECRET VISTA_ALLOWED_ORIGINS)
for name in "${required[@]}"; do
  if ! grep -Eq "^${name}=.+" .env; then
    echo "Missing ${name} in .env" >&2
    exit 1
  fi
done

docker compose config --quiet
docker compose build --pull
docker compose up -d --remove-orphans

for _ in {1..80}; do
  if curl -fsS http://127.0.0.1:8000/api/ready >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -fsS http://127.0.0.1:8000/api/ready | python3 -m json.tool
curl -fsS http://127.0.0.1:8080/ >/dev/null

echo "Vista OS deployment is healthy"
echo "Frontend: http://127.0.0.1:8080"
echo "API:      http://127.0.0.1:8000/api/health"
