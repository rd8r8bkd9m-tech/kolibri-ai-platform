# Skill Evaluation Plan

Status: active
Generated: 2026-07-02

## Purpose

Define how candidate skills are evaluated before promotion to approved state.
Every skill passes through structured evaluation before deployment.

## Evaluation Dimensions

| Dimension | Weight | Pass Threshold |
| --- | --- | --- |
| Security | 30% | No critical/high findings |
| Relevance | 25% | Direct Kolibri use case identified |
| License | 15% | OSI-approved or owner-approved |
| Quality | 15% | Code reviewed, tests present |
| Maintenance | 10% | Active maintenance or simple enough to fork |
| Performance | 5% | No unacceptable overhead |

## Evaluation Steps

1. **Source Analysis**: Verify repository, license, maintainers, stars/forks.
2. **Code Review**: Manual or automated review of source code.
3. **Dependency Audit**: Scan dependencies for vulnerabilities and bloat.
4. **Security Scan**: Run SAST, secret detection, and network analysis.
5. **Contract Fit**: Verify skill fits Kolibri agent contracts and permission model.
6. **Prototype Test**: Install in sandbox and run basic smoke test.
7. **Documentation Check**: Verify skill has adequate documentation.
8. **Decision**: Approve, adapt, quarantine, or reject.

## Evaluation Record Format

For each evaluated skill:

```yaml
skill_id: <name>
source_url: <url>
license: <license>
evaluated_by: <agent_role>
evaluated_at: <timestamp>
security_score: <1-5>
relevance_score: <1-5>
quality_score: <1-5>
decision: <approved|adapted|quarantine|rejected>
rationale: <text>
next_action: <text>
```

## Escalation Criteria

Skills requiring owner decision:
- License ambiguity
- Security findings above threshold
- Cross-scope promotion (dev -> server -> all_agents)
- Conflicts with existing skills
- Cost implications

## Review Cycle

- New skill evaluation: within 48 hours.
- Existing skill re-evaluation: quarterly.
- Emergency evaluation: within 4 hours with owner approval.
