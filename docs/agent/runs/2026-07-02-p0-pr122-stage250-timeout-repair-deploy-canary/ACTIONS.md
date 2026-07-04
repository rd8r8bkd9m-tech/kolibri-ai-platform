# Actions

Runtime inspection:

- Confirmed `gh` is unavailable in this container; local git is used for commit/push evidence.
- Confirmed current repo branch is `rebroadcast/p0_pr122_stage250_timeout_repair_deploy_and_canary_2026_07_02`.
- Confirmed the live runtime directory `/opt/kolibri-ai-platform` is not a Git checkout.
- Confirmed raw deployment of this branch over live runtime would be unsafe because live `factory_control.py` contains registry/access-fabric code not present in this older branch.
- Confirmed local healthy endpoint is `10.99.0.10:9101`; `10.99.0.2:9101` is a different/main endpoint and still returned legacy lease behavior during the initial probe.

Rollback setup:

- Created rollback directory: `/opt/kolibri-ai-platform/.rollback/20260704T053602Z-stage250-lease-timeout`.
- Backed up runtime file: `/opt/kolibri-ai-platform/.rollback/20260704T053602Z-stage250-lease-timeout/factory_control.py.before`.
- Backed up unit file: `/opt/kolibri-ai-platform/.rollback/20260704T053602Z-stage250-lease-timeout/kolibri-factory-control.service.before`.

Runtime deploy:

- Patched only `/opt/kolibri-ai-platform/ops/factory_control.py`.
- Added bounded HTTP admission with `MAX_HTTP_WORKERS=64` and `HTTP_REQUEST_BACKLOG=1024`.
- Added lease idle/overload envelopes so canary lease paths return structured HTTP 200 `no_task` or `overloaded` instead of lease 5xx/204.
- Added `LEASE_QUEUE_SCAN_LIMIT=100`.
- Added lock-gated `maybe_requeue_expired_leases()` and `LEASE_REAPER_BATCH_LIMIT=250` to stop every lease poll from scanning all tasks.
- Exposed capacity controls in `/v1/health` and `/v1/superfactory/status`.
- Restarted only `kolibri-factory-control.service`.

Canary:

- Ran route matrix on `10.99.0.10:9101`.
- Ran 250 concurrent lease polls at concurrency 25 with capability `stage250_runtime_canary_no_matching_task`.
- The canary did not create tasks and leased zero queued tasks.

