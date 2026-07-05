# Agent Runtime Status

Date: 2026-07-05

## Current Capabilities

- Agent host contract exists in `ops/agent_host.py`.
- Task envelope, permission pack, artifact verification, and deny/blocked-result behavior exist.
- Telegram/Superfactory runner policy is tested.
- Fabric task/artifact aliases are tested.

## Calibri V1 Requirements

| Requirement | Status | Evidence / Next Action |
| --- | --- | --- |
| enroll | partial/gap | Present as bootstrap/node registration concept; needs explicit tested endpoint. |
| heartbeat | partial | Factory node heartbeat state exists; add canonical alias test. |
| capabilities | partial | Fabric capability map exists; normalize into agent model. |
| receive/poll task | partial | Redis queue/task lease model exists. |
| emit events | gap | Add event append/list skeleton after compatibility tests. |
| register/upload artifacts | partial | Artifact paths in task result envelopes; add metadata registration skeleton. |
| safe demo execution | partial | Agent host permission packs and runner contracts. |
| unsafe command denied | partial | Admin-denied envelopes and permission contracts; keep expanding tests. |
| no worker SSH | documented | `.kolibri` policy and docs. |
| no raw secrets | protected | `.gitignore`, CI secret scan, publication check. |

## Next Safe Action

Implement a minimal read-only agent status endpoint group before adding mutating endpoints.
