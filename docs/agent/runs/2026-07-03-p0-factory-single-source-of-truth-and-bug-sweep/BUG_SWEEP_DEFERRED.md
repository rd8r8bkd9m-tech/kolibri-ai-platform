# Bug Sweep Deferred

## Backend Factory Status Proxy

- Status: completed in this sweep.
- Result: `/api/factory/status` now consumes canonical Control Plane health, fleet summary and queue diagnostics instead of returning a zero-node degraded fallback when Control Plane is healthy.
- Priority: P0.
- Owner approval needed: no further action unless rollback is requested.

## Home Kiosk End-To-End

- Status: completed after Home access was repaired.
- Result: Home Control Center serves clickable drill-down NOC from `http://127.0.0.1:9191`; kiosk service points at that URL.
- Artifact: `/var/lib/kolibri-agent/artifacts/P0_HOME_NOC_CLICKABLE_KIOSK_E2E_20260703/result.json`.
- Rollback: restore `/opt/kolibri-control-center/server.py.backup-p0-clickable-noc-20260703T1300Z` and restart `kolibri-control-center.service`.
- Priority: P0.
- Owner approval needed: no further action unless rollback is requested.

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
