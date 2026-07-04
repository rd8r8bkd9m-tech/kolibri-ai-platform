# P0 PR122/PR125 Stage-250 Lease Timeout Repair Deploy Canary Plan

Date: 2026-07-04 UTC

Objective: run a rollback-protected Factory Control runtime deploy and canary for the stage-250 lease timeout repair without requeueing a full worker wave or mutating the original rebroadcast task.

Execution node:

- Hostname: `kolibri`
- Healthy local control endpoint: `10.99.0.10:9101`
- Local service: `kolibri-factory-control.service`
- Runtime path: `/opt/kolibri-ai-platform/ops/factory_control.py`

Scope:

- Restart only `kolibri-factory-control.service`.
- Do not touch Telegram services, webhooks, messages, secrets, or receiver ownership.
- Do not cancel, delete, or mutate the original task.
- Do not launch a broad worker wave.
- Canary only `/v1/tasks/lease` with a non-matching capability so no queued task is leased.

Deploy gate:

1. Confirm the service unit points at `/opt/kolibri-ai-platform`.
2. Create a rollback backup before editing runtime files.
3. Apply only the lease timeout/capacity runtime patch needed on the live file.
4. Run `python3 -m py_compile` and `scripts/preflight-factory-control-runtime.sh /opt/kolibri-ai-platform`.
5. Restart only `kolibri-factory-control.service`.
6. Verify health/fabric/model routes and a 250-request lease canary.
7. Roll back immediately if health, preflight, restart, or route checks fail.

