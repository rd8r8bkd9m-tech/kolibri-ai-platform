# Security Policy

## Reporting

Do not open public issues containing secrets, tokens, cookies, passwords, private keys, production env values, bank/payment credentials, or personal security data.

For security-sensitive findings, create a minimal redacted issue or owner task that describes:

- affected area;
- impact;
- reproduction without secrets;
- task_id or artifact link if available;
- required owner approval.

## Secrets

- Never commit `.env`, key files, cookies, database dumps, production credentials or raw tokens.
- Never print secret values in CI logs, PRs, issues, docs or Control Plane artifacts.
- Rotate/revoke any credential that may have been exposed.

## Privileged Actions

Branch protection changes, admin endpoints, deploy keys, payment actions, destructive infrastructure commands and production restarts require explicit owner approval.
