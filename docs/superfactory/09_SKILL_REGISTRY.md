# Kolibri Skill Registry

Status: active
Owner: Skill Librarian agent role
Generated: 2026-07-02

## Purpose

The Skill Registry is the canonical index of all approved agent skills available
in Kolibri Factory. Every skill must be registered here before it can be deployed
to any server node. The registry is the single source of truth for skill
lifecycle, approval state, and deployment scope.

## Skill Lifecycle

```
discover -> quarantine -> inspect -> license/security check -> adapt
  -> register -> test -> approve -> install -> sync -> measure
```

Each skill must pass through every stage before reaching `approve`. Skills
that fail any stage are marked `rejected` with documented rationale.

## Approval States

| State | Meaning |
| --- | --- |
| `discovered` | Found but not yet inspected |
| `quarantined` | Under security/license review |
| `inspected` | Code reviewed, dependencies audited |
| `adapted` | Modified to fit Kolibri contracts |
| `registered` | Listed in this registry |
| `tested` | Passing smoke/safety tests |
| `approved_dev` | Safe for development workstations only |
| `approved_server` | Safe for server node deployment |
| `approved_all_agents` | Safe for all agent nodes |
| `rejected` | Failed security, license, or quality check |

## Internal Skills (Kolibri-authored)

| Skill ID | Description | Approval | Scope |
| --- | --- | --- | --- |
| `kolibri-runner-hardening` | Hardens AI runner contracts and auth checks | `registered` | server |
| `kolibri-github-curator` | Manages PRs, branches, CI state, releases | `registered` | server |
| `kolibri-ci-doctor` | Diagnoses CI failures and proposes fixes | `registered` | server |
| `kolibri-fleet-inventory` | Read-only fleet health and capability audit | `registered` | all_agents |
| `kolibri-server-recovery` | Structured node repair without secret exposure | `registered` | server |
| `kolibri-pr-splitter` | Splits large mixed PRs into focused changes | `registered` | server |
| `kolibri-formulalm-planner` | FormulaLM research task planning | `registered` | dev |
| `kolibri-model-factory` | Local LLM/model pipeline orchestration | `registered` | server |
| `kolibri-business-builder` | Business/revenue task drafting | `registered` | dev |
| `kolibri-finance-reporter` | Financial reporting and cost tracking | `registered` | dev |

## External Candidate Skills

See `docs/superfactory/10_SKILL_INTERNET_DISCOVERY.md` for the full discovery
catalog. See `docs/superfactory/SKILL_DISCOVERY_REPORT.md` for source analysis.

## Deployment Scope

| Scope | Nodes | Use |
| --- | --- | --- |
| `dev` | Mac thin client only | Development-time planning and drafting |
| `server` | Any healthy server node | Implementation, CI, fleet operations |
| `all_agents` | All agent nodes including mesh | Read-only probes, inventory, monitoring |

## Registry Update Rules

1. New skills enter as `discovered` with a source URL and license.
2. Security review is mandatory before `approved_server` or `approved_all_agents`.
3. No unaudited scripts execute on any node.
4. Skills are synced only to nodes matching their deployment scope.
5. Skill versions are tracked; rollback is required on regression.
6. Owner approval is required for `approved_all_agents` promotion.

## Related Documents

- `docs/superfactory/SKILL_SECURITY_POLICY.md`
- `docs/superfactory/SKILL_INSTALLATION_POLICY.md`
- `docs/superfactory/SKILL_EVAL_PLAN.md`
- `docs/superfactory/SKILL_DISCOVERY_REPORT.md`
- `docs/superfactory/10_SKILL_INTERNET_DISCOVERY.md`
- `.agents/skills/README.md`
