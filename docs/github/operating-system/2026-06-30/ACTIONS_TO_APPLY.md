# Actions To Apply

This file lists exact commands for GitHub metadata changes. They are not automatically applied by this PR.

## Create Labels

```bash
repo=rd8r8bkd9m-tech/kolibri-ai-platform
for label in P0 P1 P2 P3; do gh label create "$label" --repo "$repo" --color d73a4a --description "Priority $label" || true; done
for label in type:bug type:feature type:docs type:infra type:security type:test type:refactor type:research type:agent-task; do gh label create "$label" --repo "$repo" --color 1d76db --description "Work type" || true; done
for label in area:frontend area:backend area:control-plane area:agent-host area:telegram area:formula-lm area:estimates area:billing area:github-ci area:devops area:fleet area:model-factory area:docs; do gh label create "$label" --repo "$repo" --color 5319e7 --description "Subsystem area" || true; done
for label in status:ready status:blocked status:needs-review status:needs-split status:waiting-ci status:in-progress status:stale status:owner-approval; do gh label create "$label" --repo "$repo" --color fbca04 --description "Workflow status" || true; done
for label in risk:low risk:medium risk:high risk:dangerous; do gh label create "$label" --repo "$repo" --color b60205 --description "Risk level" || true; done
for label in agent:codex agent:mimo agent:api agent:review agent:qa agent:human; do gh label create "$label" --repo "$repo" --color c5def5 --description "Responsible agent class" || true; done
```

## Proposed P0 Issues

Create only after deduping against existing issues:

```bash
gh issue create --repo "$repo" --title "P0 Unified Fabric API and Server Connectivity" --body-file docs/github/operating-system/2026-06-30/proposed-issues/P0_UNIFIED_FABRIC_API.md --label P0,type:infra,area:control-plane,area:fleet
gh issue create --repo "$repo" --title "P0 Agent Host Generic Runner Contract Hardening" --body-file docs/github/operating-system/2026-06-30/proposed-issues/P0_AGENT_HOST_RUNNER_CONTRACT.md --label P0,type:infra,area:agent-host,risk:high
gh issue create --repo "$repo" --title "P0 GitHub Operating System and Repository Governance" --body-file docs/github/operating-system/2026-06-30/proposed-issues/P0_GITHUB_OS.md --label P0,type:docs,area:github-ci
gh issue create --repo "$repo" --title "P0 Command Fabric HA and Any-Node Control" --body-file docs/github/operating-system/2026-06-30/proposed-issues/P0_COMMAND_FABRIC_HA.md --label P0,type:infra,area:control-plane
gh issue create --repo "$repo" --title "P0 Fleet Resource Inventory and Reachability" --body-file docs/github/operating-system/2026-06-30/proposed-issues/P0_FLEET_INVENTORY.md --label P0,type:infra,area:fleet
gh issue create --repo "$repo" --title "P0 Repair uiap/qjns Disk and Server GitHub Auth" --body-file docs/github/operating-system/2026-06-30/proposed-issues/P0_REPAIR_UIAP_QJNS_GITHUB_AUTH.md --label P0,type:infra,area:fleet,status:blocked
gh issue create --repo "$repo" --title "P0 Preserve Dirty Runtime Diffs from main and primary-candidate" --body-file docs/github/operating-system/2026-06-30/proposed-issues/P0_PRESERVE_DIRTY_RUNTIME_DIFFS.md --label P0,type:infra,area:devops
gh issue create --repo "$repo" --title "P0 Split PR #46 into safe PRs" --body-file docs/github/operating-system/2026-06-30/proposed-issues/P0_SPLIT_PR46.md --label P0,status:needs-split,risk:high
```

## Label Current High-Risk PRs

```bash
gh pr edit 46 --repo "$repo" --add-label P0,status:needs-split,risk:high
gh pr edit 83 --repo "$repo" --add-label P0,area:agent-host,risk:high,status:needs-review
gh pr edit 85 --repo "$repo" --add-label P0,area:control-plane,risk:high,status:needs-review
```
