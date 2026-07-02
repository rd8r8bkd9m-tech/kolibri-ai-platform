# Skills Registry Contract

Task: `P1_SKILLS_REGISTRY_AND_TEAM_HANDOFF_MESH_2026_07_02`

This is a docs-only operating contract. It starts the skills registry and
handoff mesh after P0 canary artifacts became visible. It does not implement a
RAG service, product feature, production endpoint, daemon, scheduler or deploy
change.

## Scope

The first registry version tracks only committed, reviewable knowledge:

| Registry class | Source of truth | Initial status |
| --- | --- | --- |
| Codex skills | `SKILL.md` files committed to the repository or installed under approved Codex skill roots | draft registry |
| Dispatcher agents | `docs/agent/dispatcher/REMOTE_AGENTS.md` | active naming policy |
| Task envelopes | `docs/agent/dispatcher/envelopes/*.json` | auditable task source |
| Run artifacts | `docs/agent/runs/**/{PLAN,ACTIONS,TESTS,RESULT,NEXT}.md` | task evidence |
| Intelligence docs | `docs/agent/intelligence/**` | reusable context |

Excluded from the registry:

- runtime logs;
- local caches;
- credentials, tokens, environment dumps or private key material;
- non-committed operator notes unless explicitly relayed as a safe artifact;
- generated model data and vector collections.

## Registry Record

Every registry row must have these fields:

| Field | Required | Contract |
| --- | --- | --- |
| `registry_id` | yes | Stable slug, unique in the registry |
| `name` | yes | Human readable name |
| `kind` | yes | `skill`, `agent_role`, `task_envelope`, `run_artifact`, `intelligence_doc` |
| `source_path` | yes | Repository-relative source path |
| `owner_display_name` | yes | Russian human display name plus role |
| `status` | yes | `draft`, `active`, `blocked`, `deprecated` |
| `allowed_nodes` | yes | Node or pool names where work may run |
| `capability_tags` | yes | Short tags used for routing |
| `safety_gates` | yes | Required policy checks before use |
| `last_verified_at` | yes | UTC date or `unverified` |
| `next_action` | yes | One concrete next action |

Owner-facing names must follow the existing dispatcher rule:

```text
<Russian name> — <role>
```

The display name is for operator clarity. Technical IDs such as `agent_id`,
node ID, PID, branch and lease ID remain audit metadata.

## Initial Registry Seeds

| Registry ID | Name | Kind | Owner display name | Status | Source path | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| `skill-openai-docs` | OpenAI docs skill | skill | `Мария — библиотекарь skills` | draft | `.codex/skills/.system/openai-docs/SKILL.md` or installed skill source | Include only metadata; do not copy private local state |
| `skill-kolibri-gomesh-gateway` | Kolibri GoMesh gateway skill | skill | `Николай — ревизор GoMesh` | draft | approved installed skill source | Register as restricted networking skill |
| `agent-mariya-skill-librarian` | Skill librarian | agent_role | `Мария — библиотекарь skills` | active | `docs/agent/dispatcher/REMOTE_AGENTS.md` | Assign registry curation tasks only |
| `agent-olga-docs-curator` | Documentation curator | agent_role | `Ольга — куратор документации` | active | `docs/agent/dispatcher/REMOTE_AGENTS.md` | Assign artifact relay and summary tasks |
| `agent-nikolai-security-reviewer` | Security reviewer | agent_role | `Николай — ревизор безопасности` | active | `docs/agent/dispatcher/REMOTE_AGENTS.md` | Review registry gates and secret quarantine |
| `contract-uiap-rag-indexer` | UIAP RAG indexer contract | intelligence_doc | `Ирина — архитектор RAG и skills` | active | `docs/agent/intelligence/2026-07-01-uiap-rag-indexer-contract/UIAP_RAG_INDEXER_CONTRACT.md` | Keep as implementation prerequisite, not live service approval |

## Promotion Gates

A registry item may move from `draft` to `active` only when:

- source path exists in the repository;
- owner display name follows the Russian-name rule;
- safety gates are listed;
- secret-like content scan passes or quarantine is explicit;
- a run artifact records status, artifacts, blockers and next action;
- a reviewer can reproduce the referenced source from Git.

## Runtime Relationship

This registry is compatible with the future `uiap` RAG indexer contract, but it
does not start indexing. The future indexer may consume this registry only after
the contract tests and resource/security gates from
`docs/agent/intelligence/2026-07-01-uiap-rag-indexer-contract/RESOURCE_AND_SECURITY_GATES.md`
are approved.

