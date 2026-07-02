# Server And Agent Map

## Assignment Matrix

| Workstream | Preferred node/server | Agent name | Agent role | Execution mode | Reason |
| --- | --- | --- | --- | --- | --- |
| Skill registry docs and internal skill drafts | `primary-candidate`, fallback `main` | `Мария — Skill Librarian` | skill registry owner | remote docs implementation | Needs repo write access and small focused docs changes |
| Skill security/install/eval policy | `primary-candidate`, fallback `main` | `Николай — Security Reviewer` | policy review | remote review | Blocks server sync until approved |
| Team mesh and human protocol | `primary-candidate` or any healthy docs node | `Ольга — Documentation Curator` | docs/protocol owner | remote docs implementation | Creates role and handoff artifacts |
| Fleet skill rollout matrix | `main`, `primary-candidate`, `Home` | `Дмитрий — Fleet Engineer` | fleet/control owner | remote read-only inventory, then gated sync | Needs node status and rollout classification |
| Skills/RAG index mirror | `uiap` | `Ирина — RAG и skills архитектор` | RAG/knowledge owner | remote light CPU-only indexing contract | Existing readiness says `uiap` fits docs/skills indexing |
| Anti-degradation and skill usefulness review | independent healthy review node | `Наталья — Anti-Degradation Auditor` | QA/review owner | remote review | Keeps registry and sync from drifting |
| Professional business memory/Kwork artifacts | healthy docs node; no browser/client action without owner approval | `Елена — Business Builder` | business artifact owner | remote docs implementation | Produces durable profile/service/portfolio memory |

## Node Policy

- Use `primary-candidate`, `main`, and `Home` first if healthy.
- Use `uiap` only for light RAG/skills-indexing tasks until resource gates are
  approved.
- Skip degraded nodes during sync; classify them with a skipped reason.
- Do not run scripts from discovered internet skills on any node until the
  security policy and registry decision explicitly approve them.

## Owner-Facing Naming

All owner-facing reports should use Russian display names:

| Agent id/function | Owner-facing name |
| --- | --- |
| skills registry | `Мария — Skill Librarian` |
| docs/protocol | `Ольга — Documentation Curator` |
| fleet/sync | `Дмитрий — Fleet Engineer` |
| security | `Николай — Security Reviewer` |
| RAG/knowledge | `Ирина — RAG и skills архитектор` |
| anti-degradation | `Наталья — Anti-Degradation Auditor` |
| business/Kwork | `Елена — Business Builder` |

