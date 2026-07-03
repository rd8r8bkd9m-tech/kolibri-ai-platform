# Runner Registry

Runner source: `RUNNER_REGISTRY` in `ops/factory_registry.py`.

| Runner | Capability | Health Check | Fallback |
| --- | --- | --- | --- |
| codex | runner:codex | `runners.codex.status == available` | MIMO/API only when task policy allows |
| mimo | runner:mimo | `runners.mimo.status == available` | Codex/API only when task policy allows |
| api | runner:api | `runners.api.status == available` | Fabric relay |
| local_llm | runner:local_llm | model runtime health | Blocked until model node authenticated |
| review | review | review capability and runner state | github_review alias only on capable node |
| qa | qa | qa capability | capability-compatible fallback if policy allows |
| generic_implementation | generic_implementation | implementation alias | capability-compatible fallback if policy allows |

Runner availability must come from node heartbeat data. It must not be inferred from IP reachability alone.

