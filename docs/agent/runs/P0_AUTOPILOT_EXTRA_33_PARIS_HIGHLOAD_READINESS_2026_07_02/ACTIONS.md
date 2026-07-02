# Actions

## Completed

- Confirmed `hostvds-paris-highload` SSH alias in dispatcher topology:
  - alias: `hostvds-paris-highload`
  - IP: `95.182.83.60`
  - user: `root`
- Ran direct public-key-only SSH probe from the assigned worker:
  - result: `ssh: connect to host 95.182.83.60 port 22: Connection timed out`
- Tried approved server-side fallback through `kolibri-primary-codex`:
  - result: `root@78.17.4.108: Permission denied (publickey,password)`
- Queried Fabric/Control Plane health:
  - `http://10.99.0.10:9101/health` returned HTTP 200 with Redis `PONG`
  - `http://10.99.0.2:9101/health` returned HTTP 200 with Redis `PONG`
- Queried `/v1/nodes` and route metadata for Paris/highload cards.
- Captured assigned worker budget on `mesh-agent-33`.
- Left product code untouched.

## Evidence Summary

Assigned worker:

- node: `mesh-agent-33`
- agent: `agent-host-mesh-agent-33`
- host: `kolibri`
- health: `online`
- freshness: `fresh`
- active task: `P0_AUTOPILOT_EXTRA_33_PARIS_HIGHLOAD_READINESS_2026_07_02`
- CPU: `8`
- disk: about `49 GiB` free on `/`, `48%` used
- RAM: about `7.8 GiB` available of `12.2 GiB`

Target Paris cards:

- `mesh-paris`: stale, degraded, mesh IP `95.182.83.60`, last mesh seen `2026-06-28T20:17:30.017515213Z`, no CPU/RAM/disk stats.
- `paris`: stale metadata card, heartbeat `2026-06-30T11:56:43.110013+00:00`, no hostname or resource stats.
- `hostvds-paris-highload`: SSH timed out on port 22 from this worker.

