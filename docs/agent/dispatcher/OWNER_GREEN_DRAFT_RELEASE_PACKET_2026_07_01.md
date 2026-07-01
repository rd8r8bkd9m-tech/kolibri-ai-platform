# Owner Green Draft Release Packet - 2026-07-01

Status: `command_node_packet_ready_remote_steward_blocked_by_runner_auth`

This packet records the command-node view of the release queue after the owner
reported that `main` still looked stale.

## Current Facts

- `origin/main`: `a0d34d6d97a1a2af90463a1205649a24b4a178d7`
- PR #95 refreshed the old README on `main`.
- Open PRs: 38.
- Draft PRs: 25.
- Ready/non-draft PRs: 13.
- The main blocker is release governance: many PRs are CI-green and mergeable,
  but remain draft/owner-gated.

## Green Draft P0 Queue

| PR | Head | CI | Mergeable | Release classification |
| --- | --- | --- | --- | --- |
| #88 | `d4559722` | success | clean | docs-only candidate; safe first owner batch if PR scope remains dispatcher docs only |
| #92 | `5a33c3fc` | success | clean | docs-only fleet inventory candidate |
| #96 | `42625cad` | success | clean | early runtime-contract candidate; needs post-merge Agent Host permission canary |
| #97 | `f542c5c7` | success | clean | early Control Plane candidate; needs freshness canary after deploy/restart |
| #85 | `30b7e5dc` | success | clean | API-first Fabric candidate; release gate says `merge_ready_after_owner_review` |
| #91 | `35054449` | success | clean | MIMO runner candidate; should follow Agent Host contract/permission decisions |
| #89 | `e14aae21` | success | clean | Telegram candidate; hold until single receiver/cutover safety is closed |
| #83 | `3560af06` | success | clean | runner hardening candidate; check overlap/supersession with #96 before merge |

## Recommended Owner Batches

Batch 1, low risk docs:

1. PR #88 - dispatcher ledger.
2. PR #92 - fleet inventory docs.

Batch 2, runner/control contracts:

1. PR #96 - Agent Host read-only permission pack.
2. PR #97 - Control Plane node-health freshness.

Batch 3, API/fabric:

1. PR #85 - API-first Fabric.

Hold:

- PR #91 until Agent Host contract/canary order is confirmed.
- PR #89 until Telegram receiver/cutover risk is closed.
- PR #83 until the relationship with #96 is checked.

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
   - Current state at last command-node check: `queued`, no lease yet.

## Required Repair

P0 runner repair is now concrete:

- Restore or rotate Codex auth on `main` without printing secrets.
- Fix review-only permission pack so the Control Plane does not assign
  `full_autonomy`, `git_push`, and `write_worktree` to no-merge review tasks.
- Confirm at least one MIMO-capable node can lease `owner_remote_task` review
  jobs and produce exact run artifacts.

No PR was marked ready, approved, merged, closed, force-pushed, or pushed to
`main` by this packet.
