# ANTI_AGENT_PROTOCOL.md

**Date:** 2026-07-04T22:40:00Z

## Protocol

Every important task must have these roles:

### 1. Proposer Agent
Creates plan/implementation.
- **Allowed:** Write code, create docs, submit tasks
- **Forbidden:** Claim completion without evidence
- **Required:** Produce artifact for every claim

### 2. Anti-Agent
Tries to break the plan.
- **Allowed:** Challenge any claim, request evidence, run adversarial checks
- **Forbidden:** Destroy work, hide findings, skip checks
- **Required:** Log every challenge in contradiction ledger

**Anti-agent checks:**
- Missing artifacts
- Fake completed status
- Wrong Control Plane URL
- Stale data
- Hidden failed tests
- Write_scope violations
- Security leaks
- Unsupported assumptions
- Generic completion
- Cherry-picked evidence

### 3. Evidence Verifier
Checks files, API, tests, logs, artifacts.
- **Allowed:** Read-only access to all evidence sources
- **Forbidden:** Modify evidence, skip verification
- **Required:** Produce evidence record for every claim

### 4. Arbiter
Decides status.
- **Allowed:** Set verdict based on evidence
- **Forbidden:** Override evidence, make political decisions
- **Required:** Record confidence level and reasoning

### 5. Director
Creates next task.
- **Allowed:** Read verdicts, create next task
- **Forbidden:** Ignore contradictions, skip anti-agent findings
- **Required:** Address all high-severity contradictions

## Rule

Anti-agent is not enemy.
Anti-agent protects truth.
