# Remote Sync Plan

This plan prepares skill sync. It does not authorize installation yet.

## Phase 0: Registry Authoring

Target node: `primary-candidate`; fallback: `main`.

Agent: `Мария — Skill Librarian`.

Create the prompt-14 registry package:
- `docs/superfactory/09_SKILL_REGISTRY.md`
- `docs/superfactory/10_SKILL_INTERNET_DISCOVERY.md`
- `docs/superfactory/SKILL_SECURITY_POLICY.md`
- `docs/superfactory/SKILL_INSTALLATION_POLICY.md`
- `docs/superfactory/SKILL_EVAL_PLAN.md`
- `docs/superfactory/SKILL_DISCOVERY_REPORT.md`
- `.agents/skills/README.md`
- `.agents/skills/*/SKILL.md` for the 10 required Kolibri internal skills

Gate:
- docs-only change;
- no internet code execution;
- at least 20 candidates cataloged;
- at least 10 internal skills drafted.

## Phase 1: Security And Approval Review

Target node: independent healthy review node.

Agents:
- `Николай — Security Reviewer`
- `Наталья — Anti-Degradation Auditor`

Review:
- licenses;
- scripts and dependencies;
- secret/access risk;
- Terms of Service risk;
- install scope;
- registry decision per skill.

Gate:
- no skill can move to sync unless decision is `approve_server` or
  `approve_all_agents`;
- risky discoveries stay in quarantine.

## Phase 2: UIAP Index Preparation

Target node: `uiap`.

Agent: `Ирина — RAG и skills архитектор`.

Use existing contract:
- corpus profile: `docs_skills_minimal_v1`;
- collection alias: `uiap_docs_skills_active`;
- source of truth: GitHub commit SHA;
- include Markdown docs and committed skill metadata only.

Gate:
- no production service exposure;
- no long-running ad hoc workers;
- resource and security gates approved first.

## Phase 3: Approved Server Skill Sync

Target nodes:
- first wave: `main`, `primary-candidate`;
- second wave: `Home` and other healthy reachable nodes;
- excluded/skipped: any degraded node until classified healthy.

Agent: `Дмитрий — Fleet Engineer`.

Create:
- `docs/superfactory/SERVER_SKILL_SYNC_REPORT.md`
- `docs/superfactory/SERVER_SKILL_STATUS.md`
- `docs/superfactory/SKILL_ROLLOUT_MATRIX.md`

For each server record:
- reachable method;
- repo path;
- skill version installed;
- sync status;
- skipped reason if any;
- test command;
- health result.

Rules:
- install only `approve_server` or `approve_all_agents` skills;
- no root/global install unless documented;
- no unaudited scripts;
- no secrets;
- no destructive actions;
- no push to `main`.

## Phase 4: Measure And Improve

Agents:
- `Мария — Skill Librarian`
- `Наталья — Anti-Degradation Auditor`

Measurements:
- skill usage count;
- failed skill loads;
- skipped nodes;
- stale installed versions;
- owner-facing usefulness notes;
- follow-up registry decisions.

