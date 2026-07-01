# Security And Secrets Policy

## Absolute Rules

- Do not print secrets, tokens, keys, cookies, passwords or env values.
- Do not commit `.env`, key files, database dumps or production secret paths.
- Do not bypass CI secret scan.
- Do not use one eternal shared key.
- Do not put credentials in GitHub issues, PRs, docs, Actions logs or artifacts.

## Sensitive Changes

Changes touching these areas require `risk:high` or `risk:dangerous`:

- auth;
- billing/payments;
- GitHub Actions permissions;
- deploy keys/tokens;
- server bootstrap;
- Control Plane admin endpoints;
- Agent Host privileged exec;
- branch protection/rulesets.

## Incident Response

If a secret appears:

1. stop the task;
2. avoid repeating the value;
3. rotate/revoke out of band;
4. purge logs/artifacts where possible;
5. open a security issue with redacted evidence;
6. document prevention.
