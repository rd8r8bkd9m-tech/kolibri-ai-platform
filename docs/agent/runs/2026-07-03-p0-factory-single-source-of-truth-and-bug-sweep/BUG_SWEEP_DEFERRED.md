# Bug Sweep Deferred

## Backend Factory Status Proxy

- Reason: live backend returned degraded with zero nodes while Control Plane was healthy.
- Next task: repair backend `/api/factory/status` proxy to consume Fabric API truth.
- Priority: P0.
- Owner approval needed: no, if read-only and canary deployed.

## Home Kiosk End-To-End

- Reason: Home deploy tasks are leaseable after the Control Plane deploy, but remain queued because the Home execution path is not taking leases. SSH to Home network endpoints is reachable, but current keys are rejected.
- Next task: `P0_REPAIR_HOME_AGENT_HOST_LEASE_PATH_20260703T1245Z`; then complete the Home kiosk tasks and prove result artifacts.
- Priority: P0.
- Owner approval needed: yes if Home SSH identity or service restart is required.

## Telegram Bot End-To-End

- Reason: local gateway was standby/inactive; failover guard observed primary healthy, but owner chat path was not proven here.
- Next task: prove active primary receiver path and response artifact.
- Priority: P0.
- Owner approval needed: no for read-only proof.

## Logical Worker Inventory

- Reason: 101 logical CP records but only 20 active systemd worker units observed.
- Next task: classify inactive logical workers as retired, planned, quarantined or broken.
- Priority: P0.
- Owner approval needed: yes before deleting or draining records.

## Full MIMO Rollout

- Reason: MIMO availability appears broad in CP records, but end-to-end task completion across target fleet is not proven.
- Next task: canary batch with result artifacts and no mass requeue.
- Priority: P0.
- Owner approval needed: yes for broad rollout.
