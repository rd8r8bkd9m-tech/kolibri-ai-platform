# Launch Readiness Matrix

| Area | Current signal | Risk | First-wave action | Gate before mutation |
| --- | --- | --- | --- | --- |
| Agent Host contract | Permission-pack and runner tests exist; prior tasks exposed exact artifact failures | Read-only tasks can be misclassified if envelope asks for write powers | Reconfirm capability list and effective permissions per node | No write-capable runner unless envelope and node gate allow it |
| Factory Control runtime | Recent deploy rollback restored service, but stale route evidence remains on some live listeners | Replacing entrypoint can break Control Plane heartbeat/finalization | Probe listener and route health only | Runtime import-path release gate plus single-node canary |
| Telegram gateway | Inactive on probed node; main receiver ownership previously ambiguous then classified separately | Starting gateway can create a second receiver or mutate Bot API state | Classify receiver ownership without mutation | Owner-approved no-mutation diagnostic before any start/restart |
| GitHub/tooling | Some nodes lack `gh` or credentials | PR metadata and branch operations can fail mid-task | Classify installed tools and auth state without printing credentials | Node-specific credential/tooling repair task |
| Python dependencies | Prior canaries hit missing `httpx` and PEP 668 packaging blockers | Broad tests can fail from environment rather than product behavior | Report system Python, venv, and dependency status | Prepared backend verification environment |
| MIMO/direct runner | qjns and main have known auth/tooling blockers | Broad fanout can waste leases and produce ambiguous failures | Read-only runner readiness classification | Single direct-runner canary with non-empty parsed result |
| Capacity | Previous factory launcher intended 20 subagents/node and 1000 logical agents globally | Capacity can be overstated from stale cards | Report live CPU/RAM/disk/queue pressure | Scheduler must capacity-gate logical agents, not OS-process fanout |
| Artifacts | Multiple useful tasks failed because exact artifact aliases were missing | Control Plane cannot trust partial results | Require exact canonical run files in every child task | No completion state without exact artifacts |
