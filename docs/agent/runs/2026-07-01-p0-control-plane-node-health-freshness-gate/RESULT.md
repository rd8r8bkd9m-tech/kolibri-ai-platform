# Result

Status: `failed_useful_pr97_ci_green`

The Control Plane task itself is `failed` because exact `docs/agent/runs/.../RESULT.md` was missing during verification. The useful server-created code patch was preserved and relayed into GitHub as draft PR #97.

Draft PR:

- URL: `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/97`
- Branch: `p0/control-plane-node-health-freshness-gate-2026-07-01`
- Head: `f542c5c7e828091c2bf762f5ce24a30953dc0906`
- CI: success
- Mergeability: clean

What the patch changes:

- `/v1/nodes` derives heartbeat freshness on read.
- Freshness categories:
  - `fresh` <= 30 seconds
  - `degraded` > 30 seconds
  - `stale` > 90 seconds or missing heartbeat
- Stale/degraded heartbeats override stored `health=online`, so stale nodes are no longer counted as fully online.
- `/v1/nodes` returns `counts` / `freshness` with `fresh`, `degraded`, `stale`, `online`, and `total`.
- Backend factory status mirrors freshness logic defensively.
- UI cluster view shows fresh/degraded/stale counts.
- Telegram `/nodes` includes freshness and heartbeat age.

No live runtime mutation happened.
