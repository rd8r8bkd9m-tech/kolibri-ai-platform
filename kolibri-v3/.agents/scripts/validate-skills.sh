#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Package = grouped skills under <NN-*>/<skill>/SKILL.md (250 from the zip).
PACKAGE_COUNT=$(find "$ROOT/skills" -mindepth 3 -maxdepth 3 -name SKILL.md -path "$ROOT/skills/[0-9][0-9]-*/*" | wc -l | tr -d " ")
TOTAL_COUNT=$(find "$ROOT/skills" -name SKILL.md | wc -l | tr -d " ")

python3 "$ROOT/scripts/validate_skills.py" "$PACKAGE_COUNT"
echo "VALID: package=$PACKAGE_COUNT total=$TOTAL_COUNT"
