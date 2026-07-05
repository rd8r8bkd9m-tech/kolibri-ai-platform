# Next

Owner gate:

1. Owner reviews PR #97.
2. If approved, mark PR #97 ready and merge through GitHub.
3. Deploy/restart Control Plane through an explicit rollout task.
4. Run the post-deploy freshness canary.

Post-deploy canary:

```bash
curl -fsS http://127.0.0.1:9101/v1/nodes | python3 -m json.tool
curl -fsS http://127.0.0.1:8000/api/factory/status | python3 -m json.tool
```

Acceptance after deploy:

- `/v1/nodes` has `counts.fresh`, `counts.degraded`, `counts.stale`, `counts.online`, `counts.total`.
- Any node with heartbeat age `>90s` has `freshness=stale`.
- Stale nodes are excluded from `online`.
- `/api/factory/status` exposes matching `node_freshness` counts.

Runner follow-up:

- Fix verifier environment or run this test set inside a venv with `backend/requirements.txt` so missing `httpx` does not misclassify the release gate.
