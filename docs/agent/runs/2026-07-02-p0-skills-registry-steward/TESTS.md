# Tests

Task: `P0_SKILLS_REGISTRY_STEWARD_2026_07_02`

## Verification Commands

1. Verify all required docs files exist:

```bash
ls -la docs/superfactory/09_SKILL_REGISTRY.md docs/superfactory/10_SKILL_INTERNET_DISCOVERY.md docs/superfactory/SKILL_SECURITY_POLICY.md docs/superfactory/SKILL_INSTALLATION_POLICY.md docs/superfactory/SKILL_EVAL_PLAN.md docs/superfactory/SKILL_DISCOVERY_REPORT.md
```

2. Verify agents skills directory structure:

```bash
ls -la .agents/skills/README.md .agents/skills/kolibri-*/SKILL.md
```

3. Verify canonical run artifacts:

```bash
ls -la docs/agent/runs/2026-07-02-p0-skills-registry-steward/
```

4. Verify no product code was modified:

```bash
git diff --name-only HEAD -- backend/ frontend/ ops/ scripts/ tests/
```

Expected: no output (no product code changes).

5. Verify no secrets in created files:

```bash
grep -ri "password\|secret\|token\|api_key\|bearer" docs/superfactory/09_SKILL_REGISTRY.md docs/superfactory/SKILL_SECURITY_POLICY.md .agents/skills/*/SKILL.md || echo "CLEAN"
```

Expected: only policy references, no actual secrets.

## Acceptance Criteria Met

- [x] Skill registry exists at `docs/superfactory/09_SKILL_REGISTRY.md`
- [x] 25+ skill candidates cataloged in internet discovery
- [x] 10 Kolibri internal skills drafted in `.agents/skills/`
- [x] No unaudited scripts executed
- [x] Next fleet sync task identified
- [x] No product code changed
- [x] No secrets printed
- [x] Remote execution on server/control node
