# Docs-Only Registry And Handoff Tasks

Task: `P1_SKILLS_REGISTRY_AND_TEAM_HANDOFF_MESH_2026_07_02`

These tasks may be dispatched after P0 artifacts are visible. They must wait or
remain prepared if runner/fleet blockers prevent remote Agent Host execution.

## Task Matrix

| Task ID | Display owner | Status | Lease owner | Required artifacts | Blockers | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| `P1_SKILLS_REGISTRY_BOOTSTRAP_2026_07_02` | `Мария — библиотекарь skills` | prepared | `none_not_submitted` | `SKILLS_REGISTRY.md`, exact five run docs | P0 runtime repair still active; no remote lease yet | Submit to healthy docs node after current P0 runtime lane clears or if docs-only capacity is available |
| `P1_RUSSIAN_AGENT_HANDOFF_PROTOCOL_2026_07_02` | `Ольга — куратор документации` | prepared | `none_not_submitted` | `HANDOFF_PROTOCOL.md`, exact five run docs | no remote lease yet | Submit as docs-only artifact task; forbid product code |
| `P1_REGISTRY_SECURITY_GATE_REVIEW_2026_07_02` | `Николай — ревизор безопасности` | prepared | `none_not_submitted` | `REGISTRY_SECURITY_REVIEW.md`, `SECRET_QUARANTINE_RULES.md`, exact five run docs | waits on bootstrap artifact | Dispatch after registry bootstrap exists |
| `P1_UIAP_REGISTRY_INDEXER_TEST_CONTRACT_2026_07_02` | `Ирина — архитектор RAG и skills` | blocked_pending_prior_contract_tests | `none_not_submitted` | future test contract docs only | predecessor `P0_UIAP_RAG_INDEXER_CONTRACT_TESTS_2026_07_01` not completed | Keep blocked until indexer contract tests are accepted |

## Shared Constraints

- Run on Agent Host/server nodes, not Mac.
- Do not print secrets.
- Do not push to `main`.
- Do not force push.
- Do not use destructive git commands.
- Write docs only.
- Keep product feature work out of this lane.
- Use Russian display names for owner-facing agents.
- Record `task_id`, `status`, `lease_owner`, artifacts, blockers and next
  action in every result.

## Suggested Target Pools

| Pool | Preferred nodes | Use |
| --- | --- | --- |
| `healthy_documentation_nodes` | `primary-candidate`, `home`, `mesh-agent-01` | Bootstrap docs and exact artifacts |
| `rag_knowledge_nodes` | `uiap`, fallback `primary-candidate` | RAG/indexer compatibility review |
| `security_review_nodes` | `primary-candidate`, `home` | Secret and permission review |

## Completion Rule

A task remains `prepared`, `running`, `failed_useful_artifacts`, or
`blocked_missing_artifact` until required artifacts exist. A status may be
`completed_artifacts_exist` only when the exact artifacts are present or the
missing artifact is explicitly recorded as the blocker.

