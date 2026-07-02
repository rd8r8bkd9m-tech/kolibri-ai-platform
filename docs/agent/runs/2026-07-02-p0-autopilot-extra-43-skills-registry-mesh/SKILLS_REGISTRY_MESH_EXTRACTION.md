# Skills Registry And Professional Memory Extraction

Source: `docs/superfactory/Kolibri_All_Prompts.md`

## Extracted Work Items

| Canvas item | Priority | Extracted task | Output contract | Primary owner agent |
| --- | --- | --- | --- | --- |
| Execution order item 11 | P1 | Skill registry and discovery | Registry docs, discovery report, security/install/eval policy | `Мария — Skill Librarian` |
| Prompt 14 | P1 | Create Kolibri Skill Registry and discover useful Codex/agent/devops/AI skills | `docs/superfactory/09_SKILL_REGISTRY.md`, discovery/policy docs, `.agents/skills/*` drafts | `Мария — Skill Librarian` |
| Prompt 15 | P1 | Agent team mesh and human language protocol | role definitions, communication protocol, handoff and standup formats | `Ольга — Documentation Curator` with `Дмитрий — Fleet Engineer` |
| Prompt 16 | P1 | Anti-degradation system | quality gates, degradation signals, self-review loop, weekly audit | `Наталья — Anti-Degradation Auditor` |
| Prompt 19 | P1 | Server skill sync for approved skills only | skill rollout/status reports and per-server sync matrix | `Дмитрий — Fleet Engineer` with `Николай — Security Reviewer` |
| Prompt 20 | P2 | Logical agent scheduler design | agent capacity, placement, resource and lifecycle design | `Дмитрий — Fleet Engineer` |
| Prompt 26 | P2/business | Kwork Revenue Manager professional operating artifacts | Kwork profile, service catalog, portfolio plan, risk/rules, daily OS, role file | `Елена — Business Builder` |

## Professional Memory Tasks

The canvas does not define a standalone artifact named "professional memory".
The actionable professional-memory scope is the durable business/role memory
needed for revenue agents and safe owner delegation:

| Memory domain | Source | Durable artifact target | Guardrail |
| --- | --- | --- | --- |
| Owner canonical rules | `docs/agent/dispatcher/OWNER_CANONICAL_INSTRUCTIONS.md` | dispatcher memory and run artifacts | GitHub docs are source of truth, not private model memory |
| Agent role memory | Prompt 15 and `docs/agent/dispatcher/REMOTE_AGENTS.md` | `.agents/roles/`, `docs/superfactory/AGENT_ROLES.md` | owner-facing names in Russian |
| Skill decision memory | Prompt 14 and prompt 19 | skill registry, quarantine, eval and rollout matrices | no install without registry decision |
| Business/Kwork memory | Prompt 26 | `docs/business/kwork/*`, `.agents/roles/kwork-revenue-manager.md` | no payment, security, off-platform, or client-send actions without owner approval |
| RAG/search memory | uiap RAG contract | `uiap_docs_skills_active` future collection alias | GitHub commit SHA is source of truth |

## Required Registry States

Skill lifecycle states extracted from prompt 14:

```text
discover -> quarantine -> inspect -> license/security check -> adapt -> register -> test -> approve -> install -> sync -> measure
```

Registry decisions:
- `reject`
- `quarantine`
- `adapt`
- `approve_dev`
- `approve_server`
- `approve_all_agents`

Server sync may only use `approve_server` or `approve_all_agents`.

## Initial Internal Skills To Draft

Prompt 14 requires at least these internal skill drafts:

1. `kolibri-runner-hardening`
2. `kolibri-github-curator`
3. `kolibri-ci-doctor`
4. `kolibri-fleet-inventory`
5. `kolibri-server-recovery`
6. `kolibri-pr-splitter`
7. `kolibri-formulalm-planner`
8. `kolibri-model-factory`
9. `kolibri-business-builder`
10. `kolibri-finance-reporter`

## Current Readiness

Existing `uiap` readiness artifacts indicate `uiap` is suitable for light,
CPU-only RAG and skills-registry indexing. It should not receive heavy model,
large batch, secret-storage, Git-push, or long-running ad hoc worker tasks.

The registry authoring work should run on a healthy implementation/docs node.
The index/search mirror can later run on `uiap` after resource and security
gates are approved.

