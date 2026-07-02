# Safe Agent Launch Wave

Task id: `P0_30MIN_SECOND_WAVE_MESH_AGENT_03_AGENT_LAUNCH_GATE_2026_07_02`

## Verdict

Second-wave launch is allowed only as a bounded Control Plane wave. The gate
does not approve unmanaged local processes, direct provider fanout, fake
accounts, provider-limit bypass, destructive runtime changes or stale-node
routing.

## Launch Slots

| Slot | Target | Kind | Runner | Max inflight | Purpose | Gate |
| --- | --- | --- | --- | ---: | --- | --- |
| `S1` | `primary-candidate` or `mesh-agent-01` | artifact repair | `codex` | 1 | Repair missing exact Telegram diagnostic artifacts from useful output. | Only docs under the diagnostic run directory. |
| `S2` | `main` or `mesh-agent-03` | queue hygiene classifier | `codex` | 1 | Classify stale queued MIMO/Codex tasks and produce cancel/expire proposal. | Read-only Control Plane plus docs artifact. |
| `S3` | `new` | review probe | `codex` if available, otherwise read-only runner | 1 | Verify review-node artifact contract and GitHub metadata path. | No write outside run artifact directory. |
| `S4` | `uiap` | RAG/knowledge readiness probe | node-native read-only | 1 | Verify RAG-specialized readiness and resource pressure. | No general implementation work. |
| `S5` | `qjns` | credential/runner classification | read-only | 1 | Classify GitHub/MIMO runner blockers without printing secrets. | No login, token rotation or provider access attempt beyond approved probes. |
| `S6` | `mesh-9fts` | model-node readiness probe | read-only | 1 | Verify low-memory model-node suitability before model work. | No heavy benchmark or model download. |

## Excluded Targets

These targets are excluded until fresh evidence exists:

- `mesh-agent-04`
- `mesh-agent-05`
- `mesh-agent-06`
- `mesh-agent-07`
- `mesh-agent-08`
- `mesh-agent-09`
- `mesh-highload`
- `mesh-home`
- `mesh-main`
- `mesh-new`
- `mesh-paris`
- `mesh-primary`
- `mesh-qjns`
- `mesh-reserve242`
- `mesh-server-kfrm`
- `mesh-uiap`
- stale metadata cards `agent-01..09`, `9fts`, `highload`, `paris`,
  `reserve242`, and `server-kfrm`

## Envelope Requirements

Every launched follow-up must include:

- stable `task_id` and `idempotency_key`;
- `max_retries` no greater than 1 for diagnostic/repair gates;
- `target_node` or small allowed node set;
- `required_capability`;
- narrow `write_scope`;
- exact `required_outputs`;
- verification commands that include `git diff --check` and `test -f` checks;
- explicit no-secret, no-provider-bypass, no-fake-account constraints;
- no service mutation unless a later owner-approved task specifically grants it.

## Stop Conditions

Stop launching new work when any of these are true:

- Control Plane `/health` is not `ok`;
- node card is stale or lacks fresh heartbeat;
- target node has an active non-terminal task;
- queue hygiene classifier has not cleared stale queued work;
- runner credentials are unclassified;
- disk, memory or CPU pressure is above the node-specific safe threshold;
- required artifacts cannot be verified.

## Capacity Statement

The current wave counts `mesh-agent-03` as one fresh implementation runner. It
does not count stale cards as capacity and does not claim the global 1000-agent
target. The global target remains scheduler capacity to be earned through fresh
resource, runner, queue and provider-policy evidence.
