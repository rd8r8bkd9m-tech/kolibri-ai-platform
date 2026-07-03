# Plan

Task: `P1_KOLIBRIAI_RU_PR156_CI_ARTIFACT_REPAIR_MESH_AGENT_01_2026_07_03`

PR: `#156`

Branch: `codex/kolibriai-ru-turnkey-ai-app-redesign-2026-07-03`

## Scope

- Repair the current GitHub Actions CI failure on the already pushed PR #156 branch.
- Add the missing canonical run artifacts for this repair.
- Push the same remote-authored branch without force push.
- Update the PR body when possible.

## No-Go Items

- No live deploys.
- No service restarts.
- No merge.
- No force push.
- No credential mutation.
- No Telegram, billing, FormulaLM, Control Plane, or model gateway changes.

## Verification Plan

- Reproduce the failing pytest contract from GitHub Actions.
- Run the full CI pytest command locally.
- Run frontend lint/build checks that match the PR validation notes where available.
- Confirm changed files stay inside frontend status surface and run artifacts.
