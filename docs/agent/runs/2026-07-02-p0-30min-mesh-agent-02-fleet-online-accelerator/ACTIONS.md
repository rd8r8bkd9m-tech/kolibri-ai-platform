# Actions

Implemented:

- Added `FLEET_GUARDIAN_CANONICAL_SERVERS` for the 20-server fleet target.
- Added alias handling for mesh shadow and owner-facing cards such as
  `mesh-agent-02`, `home-live`, and `primary-candidate`.
- Added `fleet_guardian_snapshot(...)` to classify each canonical server as
  `full`, `partial`, `degraded`, `unreachable`, or `stale`.
- Added stale card tracking so stale metadata remains visible but is not counted
  as working capacity.
- Added idempotent `fleet_online_repair` task suggestions for every non-working
  canonical server.
- Added `GET /v1/fleet/guardian` returning the snapshot in the canonical Fabric
  response envelope.
- Expanded the fallback/blocker taxonomy with always-online policy blocker
  classes.
- Added regression coverage in `tests/test_factory_runtime.py`.

Safety:

- No secrets printed.
- No production services restarted.
- No credentials, firewall rules, VPN settings, or live fleet state mutated.
- Work stayed inside the checked-out repository.

