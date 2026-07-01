# PR Template Policy

The repository PR template is installed at `.github/PULL_REQUEST_TEMPLATE.md`.

## Required Fields

- Summary
- Scope
- Explicitly not included
- Linked issue/task_id
- Files changed by subsystem
- Tests run
- Tests unavailable and why
- CI status
- Risk level
- Rollback plan
- Screenshots/artifacts if UI
- Migration notes if backend/infra
- Secrets touched yes/no
- Owner approval required yes/no
- Agent final report link

## Ready-To-Review Gate

A PR is not ready if:

- CI failed;
- tests are absent without explanation;
- unrelated subsystems are mixed;
- required artifacts are missing;
- product code was modified in a docs-only task;
- secrets appear;
- risky infra changes have no rollback plan;
- owner approval is required but missing.
