# Skill Security Policy

Status: active
Generated: 2026-07-02

## Principle

No skill may execute on any Kolibri node without passing security review.
Discover broadly, install selectively. Every skill is untrusted until proven safe.

## Security Gates

| Gate | Requirement | Enforced By |
| --- | --- | --- |
| License check | OSI-approved or owner-approved license | Skill Librarian |
| Source audit | No obfuscated code, no hidden network calls | Security Reviewer |
| Dependency scan | No known CVEs above threshold | CI Doctor |
| Permission scope | Minimum required permissions declared | Skill Librarian |
| Secret handling | No hardcoded secrets, no env leakage | Security Reviewer |
| Network policy | Outbound connections documented and scoped | Security Reviewer |
| File system scope | Read/write paths declared and limited | Skill Librarian |
| Execution sandbox | Skills run with restricted permissions where possible | Agent Host |

## Prohibited Patterns

- Skills that print secrets, tokens, env vars, or private keys.
- Skills that modify production infrastructure without owner approval.
- Skills that push to `main` branch directly.
- Skills that execute unreviewed internet code.
- Skills that access bank/financial APIs autonomously.
- Skills that bypass authentication or authorization gates.
- Skills that disable logging or audit trails.

## Quarantine Process

1. Skill is isolated in a sandboxed environment.
2. Network traffic is monitored and logged.
3. File system access is tracked.
4. Dependencies are scanned for vulnerabilities.
5. License compatibility is verified.
6. Code is reviewed by Security Reviewer.
7. Decision: approve, adapt, or reject with documented rationale.

## Review Cadence

- New skills: review within 48 hours of submission.
- Existing skills: quarterly security re-audit.
- Emergency patches: expedited review with owner approval.

## Escalation

Any skill that triggers a security alert during runtime is immediately
quarantined and the owner is notified through Telegram.
