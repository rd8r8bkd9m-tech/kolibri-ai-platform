#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${VISTA_DESKTOP_API_BASE:?Set VISTA_DESKTOP_API_BASE to the deployed Vista API base, for example https://vista.example.com}"
cd "$ROOT/frontend"
npm ci --ignore-scripts --no-audit --no-fund
VITE_API_URL="$VISTA_DESKTOP_API_BASE" npm run build
