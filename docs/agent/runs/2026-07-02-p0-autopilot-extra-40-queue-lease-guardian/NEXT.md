# Queue Lease Guardian Next

Next exact task:

`P0_RUN_QUEUE_LEASE_GUARDIAN_LIVE_AUDIT_AND_REPAIR_TASK_CREATION_2026_07_02`

Objective:

Run `kolibri-dispatch guardian` against the live Control Plane from an authenticated server worker. If the report status is `repair_required`, run `kolibri-dispatch guardian --create-repair-tasks`, collect the created task ids, and report lease owners, blockers, artifacts, and owner-facing Russian summary. Do not print secrets, do not mutate product code, do not force push, and do not push to main.

