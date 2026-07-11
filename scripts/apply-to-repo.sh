#!/usr/bin/env bash
set -euo pipefail
TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then echo "usage: apply-to-repo.sh /path/to/kolibri-ai-platform"; exit 1; fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$TARGET"
rsync -a --delete --exclude='.git' "$ROOT/" "$TARGET/"
echo "Vista OS working MVP applied to $TARGET"
