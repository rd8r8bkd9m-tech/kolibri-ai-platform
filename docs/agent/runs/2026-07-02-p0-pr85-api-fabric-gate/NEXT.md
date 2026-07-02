# Next Task

Task id: `P0_POST_MERGE_FABRIC_AND_MIMO_CANARY_2026_07_02`

Goal:

Validate the already-merged PR #85 Fabric API contract and already-merged PR #91 MIMO runner dependency through live post-merge canaries.

Steps:

1. Prepare one canary worker with Python test dependencies required by the full suite (`pydantic`, `httpx`, and any transitive requirements already declared by the repo).
2. Run `python3 -m pytest -q` on current `main`.
3. Run live Fabric API route probes for health, fleet, route, task, artifact, model stub, and admin-denied envelopes.
4. Run direct MIMO success and auth/policy failure probes after Agent Host deployment/restart on one canary node.
5. Publish a post-merge canary matrix with route, node, status, blocked reason, artifacts, and next action for each probe.

Do not merge stale PR branch heads. Use current `main`.
