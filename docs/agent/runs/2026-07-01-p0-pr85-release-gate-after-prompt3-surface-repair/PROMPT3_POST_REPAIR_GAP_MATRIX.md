# Prompt #3 Post-Repair Gap Matrix

| requirement_id | requirement_text | source | implemented_or_safely_stubbed_in_pr85 | files_evidence | tests_evidence | remaining_risk | required_action | blocks_merge |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P3-HEALTH | `GET /v1/health` | Prompt #3 / API-first addendum | yes | `ops/factory_control.py` | `tests/test_fabric_control.py` | none identified | none | no |
| P3-FLEET | `/v1/fleet/nodes`, `/topology`, `/route`, `/capabilities` | Prompt #3 | yes | `ops/factory_control.py` | `tests/test_prompt3_fabric_api_surface.py` | live Redis-backed behavior should still be canaried after deploy | post-merge runtime canary | no |
| P3-MODELS | `GET /v1/models` | Prompt #3 | safe stub/catalog | `ops/factory_control.py` | `tests/test_prompt3_fabric_api_surface.py` | model runtime is not enabled by this PR | model-node integration task later | no |
| P3-RESPONSES | `POST /v1/responses` | Prompt #3 / OpenAI-compatible contract | safe blocked stub | `ops/factory_control.py` | `tests/test_prompt3_fabric_api_surface.py` | no live model route yet | later model gateway task | no |
| P3-CHAT | `POST /v1/chat/completions` | Prompt #3 / compatibility | safe blocked stub | `ops/factory_control.py` | `tests/test_prompt3_fabric_api_surface.py` | no live model route yet | later model gateway task | no |
| P3-AGENTS | `/v1/agents/tasks`, `/status/{task_id}`, `/artifacts/{task_id}`, `/cancel/{task_id}` | Prompt #3 | yes/alias over task control | `ops/factory_control.py` | `tests/test_prompt3_fabric_api_surface.py` | runtime canary still needed | post-merge canary | no |
| P3-ADMIN | `/v1/admin/exec`, `/service`, `/git`, `/bootstrap-node`, `/rotate-keys` | API-first full-control addendum | deny-by-default safe stubs | `ops/factory_control.py` | `tests/test_prompt3_fabric_api_surface.py` | full admin auth/scope implementation remains future work | dedicated admin API security implementation | no |
| P3-CANONICAL | canonical response envelope fields and fallback taxonomy | Prompt #3 / addendum | yes | `ops/factory_control.py` | `tests/test_prompt3_fabric_api_surface.py` | none identified | none | no |
| P3-DOCS-WHITESPACE | docs pass `git diff --check` | release hygiene | no | `docs/superfactory/*.md` | `git diff --check origin/main...HEAD` | doc-only whitespace | `P0_PR85_MINOR_DOCS_WHITESPACE_FIX_2026_07_01` | yes, minor |
