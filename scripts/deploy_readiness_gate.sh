#!/usr/bin/env bash
set -u

PR_NUMBER="${PR_NUMBER:-46}"
GH_REPO="${GH_REPO:-rd8r8bkd9m-tech/kolibri-ai-platform}"
FACTORY_URL="${FACTORY_URL:-http://10.99.0.2:9101}"
FACTORY_TASK_ID="${FACTORY_TASK_ID:-KOL-PRODUCT-QA-E2E-20260629}"
KFRM_PROBE_TASK_ID="${KFRM_PROBE_TASK_ID:-KOL-SERVER-KFRM-PROBE-20260629}"

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
BLOCKERS=()

say() {
  printf '%s\n' "$*"
}

section() {
  printf '\n== %s ==\n' "$*"
}

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  say "PASS: $*"
}

warn() {
  WARN_COUNT=$((WARN_COUNT + 1))
  say "WARN: $*"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  BLOCKERS+=("$*")
  say "FAIL: $*"
}

have() {
  command -v "$1" >/dev/null 2>&1
}

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "${ROOT}" ]; then
  say "ERROR: not inside a git repository"
  exit 2
fi

cd "${ROOT}" || exit 2

section "Deploy readiness gate"
say "repo: ${ROOT}"
say "mode: read-only"
say "pr: ${GH_REPO}#${PR_NUMBER}"
say "factory url: ${FACTORY_URL}"
say "factory qa task: ${FACTORY_TASK_ID}"
say "kfrm probe task: ${KFRM_PROBE_TASK_ID}"
say "note: this gate does not stage, commit, push, start services, or release changes"

section "Local repository state"
CURRENT_BRANCH="$(git branch --show-current 2>/dev/null || true)"
CURRENT_HEAD="$(git rev-parse --short HEAD 2>/dev/null || true)"
say "branch: ${CURRENT_BRANCH:-DETACHED}"
say "head: ${CURRENT_HEAD:-unknown}"
git status --short --branch

if [ -n "$(git status --porcelain=v1 2>/dev/null)" ]; then
  warn "worktree has local changes; release actions should isolate an approved commit scope"
else
  pass "worktree is clean"
fi

section "PR #${PR_NUMBER} CI"
if have gh; then
  PR_JSON="$(gh pr view "${PR_NUMBER}" --repo "${GH_REPO}" --json state,isDraft,mergeable,headRefName,headRefOid,url 2>/dev/null || true)"
  if [ -n "${PR_JSON}" ]; then
    say "${PR_JSON}"
    if printf '%s' "${PR_JSON}" | grep -q '"state":"OPEN"'; then
      pass "PR is open"
    else
      fail "PR is not open or could not be confirmed open"
    fi
    if printf '%s' "${PR_JSON}" | grep -q '"isDraft":false'; then
      pass "PR is ready for review"
    else
      fail "PR is draft or draft state could not be cleared"
    fi
  else
    fail "gh could not read PR metadata for ${GH_REPO}#${PR_NUMBER}"
  fi

  CHECKS_OUTPUT="$(gh pr checks "${PR_NUMBER}" --repo "${GH_REPO}" 2>&1 || true)"
  say "${CHECKS_OUTPUT}"
  if printf '%s\n' "${CHECKS_OUTPUT}" | grep -Eiq '(^|[[:space:]])(fail|failed|failing|cancelled|timed_out|action_required)([[:space:]]|$)'; then
    fail "GitHub checks are not green"
  elif printf '%s\n' "${CHECKS_OUTPUT}" | grep -Eiq '(^|[[:space:]])(pending|queued|in_progress|waiting|skipping)([[:space:]]|$)'; then
    fail "GitHub checks are still pending"
  elif [ -n "${CHECKS_OUTPUT}" ]; then
    pass "GitHub checks report no failed or pending jobs"
  else
    fail "GitHub checks output is empty"
  fi
else
  fail "gh CLI is not installed or not on PATH"
fi

section "Factory health"
if have curl; then
  HEALTH_OUTPUT="$(curl -fsS --max-time 5 "${FACTORY_URL}/health" 2>&1 || true)"
  say "${HEALTH_OUTPUT}"
  if printf '%s' "${HEALTH_OUTPUT}" | grep -Eiq '"?status"?[[:space:]:=]+"?ok"?|status=ok'; then
    pass "factory health reports ok"
  else
    fail "factory health did not report ok"
  fi

  TASKS_OUTPUT="$(curl -fsS --max-time 8 "${FACTORY_URL}/v1/tasks?summary=1&compact=1&limit=20" 2>&1 || true)"
  if [ -n "${TASKS_OUTPUT}" ]; then
    printf '%s\n' "${TASKS_OUTPUT}" | head -c 4000
    printf '\n'
    pass "factory compact task summary endpoint responded"
  else
    fail "factory compact task summary endpoint did not respond"
  fi

  QA_TASK_OUTPUT="$(curl -fsS --max-time 5 "${FACTORY_URL}/v1/tasks/${FACTORY_TASK_ID}" 2>&1 || true)"
  if [ -n "${QA_TASK_OUTPUT}" ]; then
    say "${QA_TASK_OUTPUT}"
    if printf '%s' "${QA_TASK_OUTPUT}" | grep -Eiq '"state"[[:space:]]*:[[:space:]]*"completed"'; then
      pass "product QA task is completed"
    else
      fail "product QA task is not completed"
    fi
  else
    warn "could not read product QA task ${FACTORY_TASK_ID}; keeping as blocker if live QA evidence is absent"
    fail "product QA task state is unavailable"
  fi

  KFRM_TASK_OUTPUT="$(curl -fsS --max-time 5 "${FACTORY_URL}/v1/tasks/${KFRM_PROBE_TASK_ID}" 2>&1 || true)"
  if [ -n "${KFRM_TASK_OUTPUT}" ]; then
    say "${KFRM_TASK_OUTPUT}"
    if printf '%s' "${KFRM_TASK_OUTPUT}" | grep -Eiq '"state"[[:space:]]*:[[:space:]]*"completed"'; then
      pass "server-kfrm probe task is completed"
    else
      fail "server-kfrm probe task is not completed"
    fi
  else
    warn "could not read server-kfrm probe task ${KFRM_PROBE_TASK_ID}"
    fail "server-kfrm probe state is unavailable"
  fi
else
  fail "curl is not installed or not on PATH"
fi

section "PWA build command documentation"
if [ -f frontend/package.json ] && have python3; then
  PWA_SCRIPT_REPORT="$(python3 - frontend/package.json <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as fh:
    package = json.load(fh)
scripts = package.get("scripts", {})
required = {
    "build": "npm --prefix frontend run build",
    "lint": "npm --prefix frontend run lint --if-present",
    "test:mobile-layout": "npm --prefix frontend run test:mobile-layout --if-present",
    "preview": "npm --prefix frontend run preview -- --host 127.0.0.1 --port 4173 --strictPort",
}
for key, command in required.items():
    value = scripts.get(key)
    state = "present" if value else "missing"
    print(f"{key}: {state}; documented_command={command}; package_script={value or ''}")
missing = [key for key in required if key not in scripts]
sys.exit(1 if missing else 0)
PY
)"
  PWA_SCRIPT_STATUS=$?
  say "${PWA_SCRIPT_REPORT}"
  if [ "${PWA_SCRIPT_STATUS}" -eq 0 ]; then
    pass "PWA build, lint, mobile guard, and preview commands are documented"
  else
    fail "one or more PWA commands are missing from frontend/package.json"
  fi
else
  fail "frontend/package.json or python3 is unavailable"
fi

section "Release evidence docs"
for doc in \
  docs/agent-work/release-status-20260629.md \
  docs/agent-work/pr46-ci-next-report.md \
  docs/agent-work/production-preview-blocker.md; do
  if [ -f "${doc}" ]; then
    pass "found ${doc}"
  else
    fail "missing ${doc}"
  fi
done

section "GO / NO-GO"
say "passes: ${PASS_COUNT}"
say "warnings: ${WARN_COUNT}"
say "failures: ${FAIL_COUNT}"

if [ "${FAIL_COUNT}" -eq 0 ]; then
  say "GO: release gate passed with read-only evidence."
  exit 0
fi

say "NO-GO: release gate blocked."
say "Blockers:"
for blocker in "${BLOCKERS[@]}"; do
  say "- ${blocker}"
done
exit 1
