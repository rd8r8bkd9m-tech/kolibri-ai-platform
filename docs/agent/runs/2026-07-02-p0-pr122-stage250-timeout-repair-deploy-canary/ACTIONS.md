# Actions

- Read the rebroadcast task from `http://10.99.0.2:9101/v1/tasks/REBROADCAST_P0_PR122_STAGE250_TIMEOUT_REPAIR_DEPLOY_AND_CANARY_2026_07_02-DELIVERABLE-RETRY`.
- Preserved the original task `P0_PR122_STAGE250_TIMEOUT_REPAIR_DEPLOY_AND_CANARY_2026_07_02`; no cancel, delete, force-requeue, reset, or credential mutation was performed.
- Fetched PR #125 refs:
  - head: `f152e74711ad4f08b71551502ed273885cf4551d`
  - merge: `0bda96ca5bb62c375b26bae902fa01558b119e29`
- Confirmed the GitHub connector can fetch PR #125 head commit metadata and diff at `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/commit/f152e74711ad4f08b71551502ed273885cf4551d`.
- Checked GitHub REST status/check-run endpoints for PR #125; unauthenticated REST returned `404` for the private repo and local `gh` is not logged in, so GitHub check-run state is not asserted here.
- Verified PR #125 repository artifacts record focused remote tests, including `46 passed in 41.13s` and dependency-free runtime suite `126 passed in 44.66s`.
- Verified live rollback backup set exists at `/var/backups/kolibri-runtime/20260704T050348Z-REBROADCAST_P0_PR122_STAGE250_TIMEOUT_REPAIR_DEPLOY_AND_CANARY_2026_07_02-narrow`.
- Verified live Factory Control service is active on `kolibri-main-api` and the runtime binary contains the PR #125 lease fast-path markers `lease_next_task`, `maybe_requeue_expired_leases`, `LEASE_QUEUE_SCAN_LIMIT`, and `BoundedThreadingHTTPServer`.
- Ran synthetic stage canary against `http://10.99.0.2:9101/v1/tasks/lease` using node id `pr125-stage250-canary-no-claim` and non-matching capability `stage250_synthetic_no_match`.
- Verified post-canary route matrix for `/health`, `/v1/health`, `/v1/fabric/health`, `/v1/fabric/routes`, `/v1/fleet/nodes`, and `/v1/models`.

Node note:

The rebroadcast was leased by Control Plane to `main:agent-host-main`. `main` is in the task `allowed_nodes` and was healthy/fresh during execution, but the envelope also included `avoid_nodes=["qjns","uiap","main"]`. I did not reassign or requeue the task because the owner rebroadcast explicitly forbade mutating the original task and required a healthy node from `allowed_nodes`.

