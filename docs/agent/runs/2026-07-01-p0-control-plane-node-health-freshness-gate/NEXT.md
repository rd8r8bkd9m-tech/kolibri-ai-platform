# Next

Owner/release gate:

1. Review draft PR #97.
2. If approved, mark ready and merge through the normal GitHub path.
3. Deploy/restart Control Plane through an explicit rollout task.
4. Run the post-deploy freshness canary.

Post-deploy canary:

```bash
curl -s http://127.0.0.1:9101/v1/nodes
```

Expected checks:

- `.counts.fresh`, `.counts.degraded`, `.counts.stale`, `.counts.online`, and `.counts.total` exist.
- Any node with heartbeat age >90s has `freshness=stale`.
- Stale nodes are not included in `online`.
- `/api/factory/status` exposes matching `node_freshness` counts.

Follow-up task:

`P0_PR97_CONTROL_PLANE_HEALTH_FRESHNESS_RELEASE_GATE_2026_07_01`
