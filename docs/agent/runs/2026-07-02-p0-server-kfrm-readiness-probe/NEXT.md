# Next

Exact next task:

`P0_SERVER_KFRM_FULL_WORKER_TELEMETRY_AND_GH_CLI_REPAIR_2026_07_02`

Goal:

Repair `server-kfrm` worker registration so the Control Plane card contains a
fresh heartbeat and full resource telemetry, then install or expose safe
GitHub CLI auth checks without printing secrets.

Acceptance:

- `server-kfrm` fleet card has fresh heartbeat within the normal freshness
  window.
- `server-kfrm` card includes `agent_id`, `hostname`, `cpu`, `memory`, and
  `disk.free/used/total`.
- `/v1/fleet/route?target_node=server-kfrm&required_capability=read_only_probe`
  still returns status `completed`.
- `gh auth status` can be checked on the responsible worker without printing
  tokens or credential files.
- No restart, deploy, credential rotation, or destructive action occurs without
  owner-approved scope.
