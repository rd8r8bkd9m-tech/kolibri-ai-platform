# Result

Status: `blocked_for_hostvds_paris_highload_workloads`

Node: `mesh-agent-33`

Agent: `agent-host-mesh-agent-33`

Owner-facing agent: `Дмитрий — Fleet Engineer`

## Decision

`hostvds-paris-highload` is not ready to take model/build workloads now.

Reason: the target Paris highload host could not be reached by SSH, and Control Plane only has stale Paris cards without current CPU, RAM, disk, heartbeat, or runner telemetry.

## Findings

- Assigned execution did happen on the server-side mesh worker:
  - `mesh-agent-33`
  - `agent-host-mesh-agent-33`
  - host `kolibri`
  - active task `P0_AUTOPILOT_EXTRA_33_PARIS_HIGHLOAD_READINESS_2026_07_02`
- Control Plane/API routing is healthy from this worker:
  - `http://10.99.0.10:9101/health`: HTTP 200, Redis `PONG`
  - `http://10.99.0.2:9101/health`: HTTP 200, Redis `PONG`
  - `/v1/fleet/route?target_node=paris`: route metadata exists, but it points at stale metadata rather than live resource telemetry.
- Assigned worker budget is acceptable for this diagnostic and light build-style work:
  - 8 CPU cores
  - about 49 GiB free disk on `/`
  - about 7.8 GiB available RAM of 12.2 GiB
  - Docker, Python 3.12, and Git are present
- Target Paris budget cannot be trusted:
  - `hostvds-paris-highload` SSH to `95.182.83.60:22` timed out.
  - `mesh-paris` is stale/degraded with last mesh seen `2026-06-28T20:17:30.017515213Z`.
  - `paris` metadata heartbeat is stale at `2026-06-30T11:56:43.110013+00:00`.
  - No current CPU/RAM/disk data exists for Paris in Control Plane.

## Blockers

1. `hostvds-paris-highload` SSH is unreachable from the assigned worker.
2. `kolibri-primary-codex` fallback SSH denied this worker key, so it could not be used as an SSH jump verifier.
3. Control Plane Paris cards are stale and lack live resource stats.
4. Paris runner/Agent Host is not proven fresh, so workload admission would be unsafe.

## Artifacts

- `docs/agent/runs/P0_AUTOPILOT_EXTRA_33_PARIS_HIGHLOAD_READINESS_2026_07_02/PLAN.md`
- `docs/agent/runs/P0_AUTOPILOT_EXTRA_33_PARIS_HIGHLOAD_READINESS_2026_07_02/ACTIONS.md`
- `docs/agent/runs/P0_AUTOPILOT_EXTRA_33_PARIS_HIGHLOAD_READINESS_2026_07_02/TESTS.md`
- `docs/agent/runs/P0_AUTOPILOT_EXTRA_33_PARIS_HIGHLOAD_READINESS_2026_07_02/RESULT.md`
- `docs/agent/runs/P0_AUTOPILOT_EXTRA_33_PARIS_HIGHLOAD_READINESS_2026_07_02/NEXT.md`

## Russian Owner Summary

Парижский highload-узел сейчас нельзя отправлять в модельные или сборочные задачи. Задание выполнялось на серверном mesh worker `mesh-agent-33`, API Control Plane доступен, но сам `hostvds-paris-highload` по SSH не отвечает, а карточки `paris`/`mesh-paris` устарели и не содержат свежих CPU/RAM/disk данных. Без восстановления heartbeat/Agent Host и повторной проверки ресурсов узел нужно считать заблокированным для workload admission.

