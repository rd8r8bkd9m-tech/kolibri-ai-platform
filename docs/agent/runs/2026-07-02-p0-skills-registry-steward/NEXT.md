# Next Tasks

Task: `P0_SKILLS_REGISTRY_STEWARD_2026_07_02`

## Next Recommended Tasks

### 1. `P1_SERVER_SKILL_SYNC_APPROVED_SKILLS_ONLY`

**Priority**: P1
**Scope**: Sync approved skills to healthy server nodes.
**Prerequisite**: This task (skill registry created).
**Target nodes**: `mesh-agent-01`, `mesh-agent-02`, `mesh-agent-03`, `main`,
`new` (fresh online nodes with runner capability).
**Scope restriction**: Only `approved_server` and `approved_all_agents` skills.
**Expected artifacts**:
- `docs/superfactory/SERVER_SKILL_SYNC_REPORT.md`
- `docs/superfactory/SERVER_SKILL_STATUS.md`
- `docs/superfactory/SKILL_ROLLOUT_MATRIX.md`

### 2. `P1_QUARANTINED_SKILL_SECURITY_REVIEW`

**Priority**: P1
**Scope**: Complete security review for 5 quarantined skills.
**Target**: ChromaDB, sentence-transformers, uvicorn-gunicorn-docker,
Grafana, Playwright.
**Expected artifacts**: Security review report per skill.

### 3. `P1_SKILL_EVAL_PILOT_TEST`

**Priority**: P1
**Scope**: Run prototype tests for top 3 approved server-scope skills.
**Target**: ruff, trivy, semgrep.
**Expected artifacts**: Evaluation records per skill.

## Blockers

1. **No live Control Plane access from this worktree**: Skills cannot be
   synced to servers without Control Plane task dispatch. The sync task
   must be dispatched through the Fabric API.
2. **Quarantined skills need owner decision**: 5 skills are pending security
   review. Owner must approve quarantine resolution before promotion.
3. **Server node freshness**: Some target nodes (home, primary-candidate) have
   stale heartbeat cards. Sync should target only fresh online nodes.
4. **GitHub/MIMO credentials on qjns**: `qjns` cannot execute GitHub push
   or MIMO tasks until credentials are repaired. Skill sync to `qjns`
   should be deferred.

## Risks

- Skill sync without proper versioning could cause inconsistent skill state
  across nodes.
- Quarantined skills may have hidden security issues if reviewed superficially.
- Internal skills are v0.1.0 drafts and may need refinement before production use.
