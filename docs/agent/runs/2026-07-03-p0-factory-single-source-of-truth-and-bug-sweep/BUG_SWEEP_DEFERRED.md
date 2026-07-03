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

- Reason: local gateway was standby/inactive; failover guard observed primary healthy. A read-only task was created and completed, but its artifact was generic Agent Host completion rather than owner-message evidence.
- Next task: prove active primary receiver path with a content-bearing, redacted response artifact.
- Priority: P0.
- Owner approval needed: no for read-only proof.

## Logical Worker Inventory

- Reason: 101 logical CP records but only 20 active systemd worker units observed.
- Next task: classify inactive logical workers as retired, planned, quarantined or broken.
- Priority: P0.
- Owner approval needed: yes before deleting or draining records.

## Full MIMO Rollout

- Reason: MIMO availability appears broad in CP records, but end-to-end task completion across target fleet is not proven. A bounded canary task reported completed, but the artifact file was not collectable from the reported result path during this sweep.
- Next task: `P0_MIMO_BOUNDED_CANARY_WITH_ARTIFACTS_20260703`, with result artifacts and no mass requeue.
- Priority: P0.
- Owner approval needed: yes for broad rollout.

## Root SSH Trust Bootstrap

- Status: completed for reachable canonical servers.
- Result: 20 of 21 canonical server aliases work from the command node by public-key SSH. The target accounts were bootstrapped through the established trust path with `authorized_keys` backups before edits.
- Remaining exception: `agent-10`, because the provider/network route to `217.60.38.191` is unavailable before SSH authentication starts.
- Priority: P0.
- Owner approval needed: no further action unless key rotation or rollback is requested.

## Agent-10 Network

- Reason: `agent-10` is canonical but has no real Control Plane heartbeat and is unreachable at `217.60.38.191`; both primary and Home traces fail at upstream `46.8.226.1` with host unreachable.
- Next task: provider-console/network repair or owner-approved retirement. Registry diagnostics already quarantine it as `provider_network_unreachable`.
- Priority: P0.
- Owner approval needed: yes before retiring the record.
