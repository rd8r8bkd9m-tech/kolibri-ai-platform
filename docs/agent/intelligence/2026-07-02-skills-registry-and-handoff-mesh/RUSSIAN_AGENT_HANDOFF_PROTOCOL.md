# Russian Agent Handoff Protocol

Task: `P1_SKILLS_REGISTRY_AND_TEAM_HANDOFF_MESH_2026_07_02`

This protocol defines how agents hand work to each other without losing audit
evidence. It is docs-only and does not authorize product changes.

## Identity

Every owner-facing agent must be named with a Russian human name and role:

```text
Мария — библиотекарь skills
Ольга — куратор документации
Николай — ревизор безопасности
Ирина — архитектор RAG и skills
Дмитрий — инженер флота
```

Technical identity remains attached to each handoff:

- `task_id`;
- `status`;
- `lease_owner`;
- `agent_id` when known;
- `node_id` or target pool;
- artifact paths;
- branch or PR, if any.

## Handoff Packet

Each handoff packet must include:

| Field | Required | Description |
| --- | --- | --- |
| `from_display_name` | yes | Russian source agent name and role |
| `to_display_name` | yes | Russian destination agent name and role |
| `task_id` | yes | Control Plane or dispatcher task ID |
| `status` | yes | Current status, never inferred as complete without artifacts |
| `lease_owner` | yes | Lease owner or `none_not_submitted` |
| `artifacts` | yes | Exact artifact list or explicit missing-artifact blocker |
| `blockers` | yes | Current blockers with owner/action |
| `next_action` | yes | One concrete next action |
| `scope_guard` | yes | What must not be changed |

## Handoff States

| State | Meaning | Allowed next action |
| --- | --- | --- |
| `prepared` | Envelope and docs exist but no remote lease/result yet | Submit or wait on higher-priority blocker |
| `running` | Lease owner is known | Poll and collect artifacts |
| `failed_useful_artifacts` | Task failed but useful artifacts exist | Relay/canonicalize artifacts or dispatch focused repair |
| `blocked_missing_artifact` | Required artifact is absent | Create exact artifact repair, do not claim complete |
| `completed_artifacts_exist` | Required artifacts exist and status is explicit | Promote next task |
| `blocked_runner_or_fleet` | Runner/fleet prevents safe execution | Record blocker and use fallback route |

## Required Evidence

Do not claim a handoff complete unless the handoff packet points to at least one
of these:

- exact run artifact set under `docs/agent/runs/...`;
- Control Plane result path under `/var/lib/kolibri-agent/artifacts/...`;
- dispatcher queue or log row with task status, lease owner, artifact path,
  blockers and next action;
- explicit `blocked_missing_artifact` status naming the missing file.

## No Product Mixing

Skills registry and handoff tasks may edit only:

- `docs/agent/dispatcher/**`;
- `docs/agent/runs/**`;
- `docs/agent/intelligence/**`;
- docs-only registry summaries.

They must not edit backend, frontend, ops runtime code, deployment scripts,
systemd units, nginx config or production service state.

## Initial Mesh Roles

| Display name | Handoff role | Primary responsibility |
| --- | --- | --- |
| `Мария — библиотекарь skills` | registry owner | Maintain skills and capability registry |
| `Ольга — куратор документации` | artifact owner | Ensure exact run artifacts and owner summaries exist |
| `Николай — ревизор безопасности` | safety reviewer | Validate no secrets, no forbidden node mutation, no overbroad permissions |
| `Ирина — архитектор RAG и skills` | RAG contract owner | Keep registry compatible with future uiap indexer |
| `Дмитрий — инженер флота` | fleet liaison | Classify runner/fleet blockers and node routing |

