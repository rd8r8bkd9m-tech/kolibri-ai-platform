# READINESS MATRIX

| Surface | Status | Evidence | Blocker |
| --- | --- | --- | --- |
| Control Plane canonical card `agent-02` | stale | heartbeat `2026-06-30T11:56:41Z`, `fresh=false`, `health=stale` | stale metadata shadow must not be used for scheduling |
| Control Plane mesh card `mesh-agent-02` | online | `fresh=true`, `health=online`, `agent_id=agent-host-mesh-agent-02`, no active task | none for inventory |
| Node identity | partially verified | `mesh_source_node_id=agent-02`, `mesh_ip=213.232.204.223`, hostname in card `kolibri` | direct host identity command did not run because SSH timed out |
| API route | degraded | Control Plane `/v1/nodes` works; `/v1/fabric/routes` returns 404; SSH route timed out | Fabric route unavailable and direct SSH unavailable |
| Disk | ready | `free=52322934784`, `total=105590231040`, about 52.3 GB free | none observed |
| RAM/CPU | ready | `cpu=8`, `MemAvailable=7966780 kB`, `MemTotal=12247028 kB` | none observed |
| Runner card | looks ready | capabilities include `generic_implementation`, `remote_implementation_runner_ready`, `runner:codex`, `runner:mimo` | scheduler did not honor target node |
| GitHub auth | unknown | cannot safely check on host because direct route timed out; no tokens printed | run bounded redacted auth probe after route repair |
| Factory work readiness | blocked | resources and runner card look good, but targeted execution failed | repair scheduler/route before assigning real factory work |
