# Plan

Task: `P0_GITHUB_RELEASE_STEWARD_GREEN_DRAFT_QUEUE_DRAIN_MIMO_FALLBACK_2026_07_01`

Runner: MIMO fallback on `mesh-agent-01`.

Goal:

1. Reconstruct the green draft PR release-steward pass after main Codex auth failed.
2. Classify priority PRs #83, #85, #88, #89, #91, #92, #96, and #97.
3. Produce the exact release-steward artifacts requested by the fallback envelope.
4. Preserve the owner gate: no PR mutation, mark-ready, approval, merge, close, force-push, or push to `main`.

Evidence sources:

- Fallback envelope snapshot at `docs/agent/dispatcher/envelopes/P0_GITHUB_RELEASE_STEWARD_GREEN_DRAFT_QUEUE_DRAIN_MIMO_FALLBACK_2026_07_01.json`.
- Prior release-steward draft artifacts under `docs/agent/runs/2026-07-01-p0-github-release-steward-green-draft-queue-drain/`.
- Focused release gate artifacts for PRs #85, #96, and #97.
- Implementation/result artifacts for PRs #83 and #89.
- Local execution evidence from environment variables: `KOLIBRI_NODE_ID=mesh-agent-01`, `KOLIBRI_AGENT_ID=agent-host-mesh-agent-01`, and work/artifact roots under `/var/lib/kolibri-agent/logical-workers/mesh-agent-01/`.

Limits:

- The `gh` CLI is not installed in this MIMO worker, so no live GitHub API recheck was performed from this run.
- The checked-in envelope snapshot is treated as the authoritative GitHub state for draft, mergeability, head SHA, and CI status.
- No product code was inspected for modification or changed by this task.
