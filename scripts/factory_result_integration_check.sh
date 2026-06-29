#!/usr/bin/env bash
set -u

TASK_ID="${TASK_ID:-KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629}"
RESULT_BRANCH="${RESULT_BRANCH:-agent/KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629/app-unblock}"
REMOTE="${REMOTE:-origin}"
BASE_REF="${BASE_REF:-origin/main}"
ENVELOPE="${ENVELOPE:-ops/envelopes/KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629.json}"

say() {
  printf '%s\n' "$*"
}

section() {
  printf '\n== %s ==\n' "$*"
}

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "${ROOT}" ]; then
  say "ERROR: not inside a git repository"
  exit 2
fi

cd "${ROOT}" || exit 2

section "Factory result integration read-only check"
say "repo: ${ROOT}"
say "task: ${TASK_ID}"
say "remote: ${REMOTE}"
say "result branch: ${RESULT_BRANCH}"
say "base ref: ${BASE_REF}"

section "Local git state"
CURRENT_BRANCH="$(git branch --show-current 2>/dev/null || true)"
CURRENT_HEAD="$(git rev-parse --short HEAD 2>/dev/null || true)"
say "current branch: ${CURRENT_BRANCH:-DETACHED}"
say "current HEAD: ${CURRENT_HEAD:-unknown}"
git status --short --branch

section "Task envelope"
if [ -f "${ENVELOPE}" ]; then
  say "found: ${ENVELOPE}"
  if command -v python3 >/dev/null 2>&1; then
    python3 - "${ENVELOPE}" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh)

for key in ("task_id", "branch", "base_ref", "kind", "target_node"):
    print(f"{key}: {data.get(key, '')}")
PY
  else
    say "python3 not found; skipping envelope JSON summary"
  fi
else
  say "missing: ${ENVELOPE}"
fi

section "Remote branch check"
REMOTE_LINE="$(git ls-remote --heads "${REMOTE}" "${RESULT_BRANCH}" 2>/dev/null || true)"
if [ -n "${REMOTE_LINE}" ]; then
  RESULT_SHA="$(printf '%s\n' "${REMOTE_LINE}" | awk '{print $1}')"
  say "remote branch found: ${RESULT_SHA}"
  REMOTE_FOUND=1
else
  say "remote branch not found yet"
  REMOTE_FOUND=0
fi

section "Local refs"
RESULT_REF="refs/remotes/${REMOTE}/${RESULT_BRANCH}"
if git show-ref --verify --quiet "${RESULT_REF}"; then
  say "local remote-tracking ref exists: ${RESULT_REF}"
  git log --oneline --decorate --max-count=5 "${RESULT_REF}"
else
  say "local remote-tracking ref missing: ${RESULT_REF}"
fi

if git rev-parse --verify --quiet "${BASE_REF}" >/dev/null; then
  say "base ref exists locally: ${BASE_REF}"
else
  say "base ref missing locally: ${BASE_REF}"
fi

section "Frontend local changes"
say "unstaged:"
git diff --name-status -- frontend || true
say "staged:"
git diff --cached --name-status -- frontend || true
UNTRACKED_FRONTEND="$(git ls-files --others --exclude-standard frontend 2>/dev/null || true)"
if [ -n "${UNTRACKED_FRONTEND}" ]; then
  say "untracked frontend files:"
  printf '%s\n' "${UNTRACKED_FRONTEND}"
else
  say "untracked frontend files: none"
fi

section "Next commands"
say "# 1. Confirm externally that ${TASK_ID} is completed."
say "# 2. Snapshot local frontend changes without staging:"
say "mkdir -p /tmp/kolibri-factory-integration"
say "git status --short --branch > /tmp/kolibri-factory-integration/status.before.txt"
say "git diff -- frontend > /tmp/kolibri-factory-integration/local-frontend.before.patch"
say "git diff --cached -- frontend > /tmp/kolibri-factory-integration/local-frontend.cached.before.patch"
say "git diff --name-status -- frontend > /tmp/kolibri-factory-integration/local-frontend.files.txt"
say "git diff --cached --name-status -- frontend > /tmp/kolibri-factory-integration/local-frontend.cached.files.txt"

if [ "${REMOTE_FOUND}" -eq 1 ]; then
  say "# 3. Fetch only the result branch into a remote-tracking ref:"
  say "RESULT_BRANCH='${RESULT_BRANCH}'"
  say "RESULT_REF='${RESULT_REF}'"
  say "git fetch --no-tags ${REMOTE} \"\${RESULT_BRANCH}:\${RESULT_REF}\""
  say "git diff --name-status ${BASE_REF}...\"\${RESULT_REF}\""
  say "git diff --name-status ${BASE_REF}...\"\${RESULT_REF}\" -- frontend"
  say "# 4. Integrate in a separate worktree, then choose cherry-pick or merge --no-commit:"
  say "git worktree add -b codex/integrate-${TASK_ID} ../kolibri-ai-platform-integrate-${TASK_ID} \"\$(git branch --show-current)\""
  say "cd ../kolibri-ai-platform-integrate-${TASK_ID}"
  say "git cherry-pick --no-commit <result-commit-sha>"
  say "# or:"
  say "git merge --no-ff --no-commit \"\${RESULT_REF}\""
  say "# 5. Verify before any stage/commit/push:"
  say "npm --prefix frontend run lint --if-present"
  say "npm --prefix frontend run build"
  say "python3 -m compileall -q backend ops"
  say "git diff --check"
else
  say "# Result branch is not available yet. Re-run this script after factory completion."
fi

section "Safety"
say "This script did not fetch, merge, cherry-pick, checkout, reset, stage, commit, push, deploy, or contact live app/control services."

if [ "${REMOTE_FOUND}" -eq 1 ]; then
  exit 0
fi
exit 1
