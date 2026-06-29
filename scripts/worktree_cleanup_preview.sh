#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

print_category() {
  local name="$1"
  shift
  printf '\n[%s]\n' "$name"
  if [ "$#" -eq 0 ]; then
    printf '  (empty)\n'
    return
  fi
  local path
  for path in "$@"; do
    printf '  %s\n' "$path"
  done
}

commit_p0_runtime=(
  "backend/billing.py"
  "backend/desktop_control_contracts.py"
  "backend/tests/test_billing.py"
  "ops/agent_host.py"
  "ops/factory_control.py"
  "ops/factory_role_catalog.json"
  "ops/telegram_gateway.py"
  "ops/envelopes/KOL-DESKTOP-CONTROL-APP-MVP-20260629.json"
  "ops/envelopes/KOL-DOCS-STEWARD-20260629.json"
  "ops/envelopes/KOL-FORMULALM-REMOTE-BENCH-6H-20260629.json"
  "ops/envelopes/KOL-GITHUB-PROJECT-OPS-20260629.json"
  "ops/envelopes/KOL-INVESTOR-OUTREACH-20260629.json"
  "ops/envelopes/KOL-LIVING-BIRD-RD-20260629.json"
  "ops/envelopes/KOL-P0-APP-QUEUE-UNBLOCK-20260629.json"
  "ops/envelopes/KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629.json"
  "ops/envelopes/KOL-PREMIUM-LANDING-UI-20260629.json"
  "ops/envelopes/KOL-PRODUCT-QA-E2E-20260629.json"
  "ops/envelopes/KOL-SUBAGENT-POOL-SUPERVISOR-20260629.json"
  "tests/test_desktop_control_contracts.py"
  "tests/test_factory_agent_messages.py"
  "tests/test_factory_runtime_queue_contracts.py"
  "tests/test_telegram_gateway.py"
)

commit_frontend=(
  "frontend/eslint.config.js"
  "frontend/index.html"
  "frontend/public/manifest.webmanifest"
  "frontend/src/App.css"
  "frontend/src/App.jsx"
  "frontend/src/assets/landing-hero.png"
  "frontend/src/components/AppHeader.jsx"
  "frontend/src/components/KolibriBird.jsx"
  "frontend/src/components/LandingShell.jsx"
  "frontend/src/components/LivingKolibri.jsx"
  "frontend/src/components/chat/ChatComposer.jsx"
  "frontend/src/components/chat/ChatWorkspace.jsx"
  "frontend/src/components/control/ControlFab.jsx"
  "frontend/src/components/control/ControlPanel.jsx"
)

commit_docs=(
  "README.md"
  "docs/"
  "ops/hourly-sync-report.md"
  "ops/secondary-control-plane-watchdog.md"
  "scripts/worktree_cleanup_preview.sh"
)

exclude_generated=(
  ".playwright-cli/"
)

candidate_delete_unused=()
if [ -d ".playwright-cli" ]; then
  while IFS= read -r generated_file; do
    candidate_delete_unused+=("$generated_file")
  done < <(find .playwright-cli -maxdepth 1 -type f | sort)
fi

print_category "commit_p0_runtime" "${commit_p0_runtime[@]}"
print_category "commit_frontend" "${commit_frontend[@]}"
print_category "commit_docs" "${commit_docs[@]}"
print_category "exclude_generated" "${exclude_generated[@]}"
print_category "candidate_delete_unused" "${candidate_delete_unused[@]}"

printf '\n[preview_commands]\n'
printf '  git add'
printf ' %q' "${commit_p0_runtime[@]}" "${commit_frontend[@]}" "${commit_docs[@]}"
printf '\n'

if [ "${#candidate_delete_unused[@]}" -gt 0 ]; then
  printf '  rm -v'
  printf ' %q' "${candidate_delete_unused[@]}"
  printf '\n'
else
  printf '  # no generated files found for rm preview\n'
fi
