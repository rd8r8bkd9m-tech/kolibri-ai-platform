# Owner Green Draft Release Packet - 2026-07-01

Status: `remote_mimo_steward_completed_artifacts_relayed`

This packet records the command-node view of the release queue after the owner
reported that `main` still looked stale.

## Current Facts

- `origin/main`: `1b08c43a86f8e1ee943edea592f77988b45f41d9`.
- PR #95 refreshed the old README on `main`.
- PR #88, #83, #96, #91, #97, and #85 are now merged into `main`.
- Open PRs: 32.
- Draft PRs: 19.
- Ready/non-draft PRs: 13.
- The old mobile screenshot showing the pre-release README is stale relative to
  current `origin/main`; if GitHub mobile still shows it, the likely causes are
  mobile cache, viewing an old branch/ref, or repository page cache.
- The remaining release blocker is governance/automation: queue stewardship is
  not yet continuous, so draft PRs still need an explicit release steward to
  recheck head SHA, CI, mergeability, scope, and post-merge canary before merge.

## Priority PR State After Recheck

| PR | State | Merge commit | Current classification |
| --- | --- | --- | --- |
| #95 | merged | `a0d34d6d` | README release train landed; old README text is no longer in `origin/main` |
| #88 | merged | `c915d9a0` | dispatcher ledger baseline landed |
| #83 | merged | `3416ed1f` | Agent Host runner contract hardening landed; post-merge runtime canary remains needed |
| #96 | merged | `4db58db4` | read-only Agent Host permission packs landed; post-merge canary remains needed |
| #91 | merged | `9000973e` | MIMO runner output/auth classification landed; post-merge MIMO canary remains needed |
| #97 | merged | `97ec4941` | stale heartbeat classification landed; deploy/restart freshness canary remains needed |
| #85 | merged | `1b08c43a` | API-first full-control Fabric landed; post-merge Fabric API canary remains needed |
| #92 | open draft | n/a | docs-only fleet inventory candidate; needs current-base update/recheck before merge |
| #89 | open draft | n/a | Telegram candidate; hold until single receiver/cutover safety is current |

## Recommended Owner Batches

Completed in `main`:

1. PR #95 - README release train.
2. PR #88 - dispatcher ledger baseline.
3. PR #83 - Agent Host runner contract.
4. PR #96 - Agent Host read-only permission packs.
5. PR #91 - MIMO runner output/auth classification.
6. PR #97 - Control Plane stale heartbeat classification.
7. PR #85 - API-first full-control Fabric.

Next safe queue:

1. Rebase/recheck PR #92 fleet inventory docs.
2. Run post-merge canaries for #83/#96/#91/#97/#85 on the server factory.
3. Re-run release-steward on all remaining 32 open PRs and close/split stale
   branches instead of letting draft PRs accumulate.

Hold:

- PR #89 until Telegram receiver/cutover risk is closed.
- Any old branch that still targets pre-`1b08c43a` `main` until it is rebased
  and rechecked.

## Remote Steward Attempts

1. `P0_GITHUB_RELEASE_STEWARD_GREEN_DRAFT_QUEUE_DRAIN_2026_07_01`
   - Submitted to Control Plane.
   - Cancelled before lease because it was hard-targeted to stale/busy
     `primary-candidate`.

2. `P0_GITHUB_RELEASE_STEWARD_GREEN_DRAFT_QUEUE_DRAIN_MAIN_FALLBACK_2026_07_01`
   - Leased on `main:agent-host-main`.
   - Failed after clone/fetch/checkout because `/usr/bin/codex exec` could not
     refresh its token.
   - Blocker: `main_codex_auth_expired`.

3. `P0_GITHUB_RELEASE_STEWARD_GREEN_DRAFT_QUEUE_DRAIN_MIMO_FALLBACK_2026_07_01`
   - Submitted to Control Plane for `mesh-agent-01` MIMO.
   - Completed on `mesh-agent-01:agent-host-mesh-agent-01`.
   - Server commit `f7aca0dccb2ad9911b4d76c3aa99a5add04cc2d8`
     created the exact nine release-steward artifacts.
   - Mac relayed that server-created commit into dispatcher branch as
     `57ad4dcb`.
   - Worker limitation: `gh` was unavailable, so it used the provided GitHub
     snapshot plus checked-in gate artifacts; a final read-only GitHub recheck
     is required immediately before any owner-approved mark-ready/merge action.

## Required Repair

P0 runner repair is now concrete:

- Restore or rotate Codex auth on `main` without printing secrets.
- Fix review-only permission pack so the Control Plane does not assign
  `full_autonomy`, `git_push`, and `write_worktree` to no-merge review tasks.
- Confirm at least one MIMO-capable node can lease `owner_remote_task` review
  jobs and produce exact run artifacts.

No PR was marked ready, approved, merged, closed, force-pushed, or pushed to
`main` by this packet.
