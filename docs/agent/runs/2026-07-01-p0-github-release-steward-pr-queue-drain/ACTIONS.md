# Actions

Remote execution happened on `primary-candidate` / hostname `kolibri`.

Control Plane task:

- Task ID: `P0_GITHUB_RELEASE_STEWARD_PR_QUEUE_DRAIN_2026_07_01`
- Lease owner: `primary-candidate:agent-host-primary`
- Result artifact: `/var/lib/kolibri-agent/artifacts/P0_GITHUB_RELEASE_STEWARD_PR_QUEUE_DRAIN_2026_07_01/P0_GITHUB_RELEASE_STEWARD_PR_QUEUE_DRAIN_2026_07_01-attempt-1/result.json`
- Server-created report: `/var/lib/kolibri-agent/worktrees/P0_GITHUB_RELEASE_STEWARD_PR_QUEUE_DRAIN_2026_07_01/P0_GITHUB_RELEASE_STEWARD_PR_QUEUE_DRAIN_2026_07_01-attempt-1/repo/docs/release/2026-07-01-pr-queue-release-steward.md`

The remote task produced a useful report but Control Plane marked the task failed because the verifier expected this envelope path inside the clean server worktree:

```bash
python3 -m json.tool docs/agent/dispatcher/envelopes/P0_GITHUB_RELEASE_STEWARD_PR_QUEUE_DRAIN_2026_07_01.json >/dev/null
```

That file was not present in the clean clone. The useful report was therefore relayed into canonical run artifacts by the Mac command node.
