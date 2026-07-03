# Capability Registry

Capability source: `CAPABILITY_REGISTRY` and `capability_satisfied()` in `ops/factory_registry.py`.

| Capability | Aliases | Safety |
| --- | --- | --- |
| implementation | generic_implementation | Does not imply a specific runner |
| generic_implementation | implementation | Generic implementation only |
| devops | permission:* | Allowed only when policy allows privileged work |
| github_review | review, generic_review | Must be a real review capability |
| review | generic_review, github_review | Must be a real review capability |
| runner:codex | runner_codex, codex_runner | Requires actual Codex availability |
| runner:mimo | runner_mimo, mimo_runner | Requires actual MIMO availability |
| runner:api | runner_api, api_runner | Requires authenticated API runner |

No task may be routed by pretending a node has a missing capability.

