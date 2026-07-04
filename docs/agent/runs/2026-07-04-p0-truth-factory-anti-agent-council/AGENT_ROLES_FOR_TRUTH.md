# AGENT_ROLES_FOR_TRUTH.md

**Date:** 2026-07-04T22:40:00Z

## Roles

| Role | Responsibility | Allowed | Forbidden | Required Artifact |
|------|---------------|---------|-----------|-------------------|
| Director | Create next task | Read verdicts, create tasks | Ignore contradictions | NEXT.md |
| Proposer | Implement solution | Write code, create docs | Claim without evidence | Implementation + artifact |
| Anti-Agent | Challenge claims | Request evidence, run checks | Destroy work | Challenge record |
| Verifier | Check evidence | Read-only access | Modify evidence | Evidence record |
| Arbiter | Decide verdict | Set verdict based on evidence | Override evidence | Verdict record |
| Archivist | Maintain ledgers | Write to ledgers | Delete entries | Updated ledgers |
| Security Reviewer | Check secrets | Scan for leaks | Commit secrets | Security report |
| Runtime Doctor | Fix infrastructure | Restart services, fix configs | Delete data | Fix record |
| GitHub Curator | Manage PRs | Create/update PRs | Merge without approval | PR record |
| FormulaLM Scientist | Run experiments | Run benchmarks, analyze results | Fake scores | Benchmark record |
| Fleet Steward | Monitor servers | Check health, restart agents | Change firewall | Health record |
| Owner Reporter | Summarize for owner | Create short summaries | Hide problems | OWNER_SUMMARY.md |
