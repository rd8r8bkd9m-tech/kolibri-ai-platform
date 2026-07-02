# Next

Dispatch this direct canary before relying on hostvds-agent-01 for factory work:

```text
Task id: P0_HOSTVDS_AGENT_01_DIRECT_AUTH_AND_RUNNER_CANARY_2026_07_02
Target: mesh-agent-01 only
Scope: read-only diagnostics and run artifacts only
Goal: prove direct lease/execution on mesh-agent-01 and check redacted GitHub auth plus Codex/MIMO runner availability
Verification: exact task status shows worktree/log paths on mesh-agent-01; gh auth status is summarized without secrets; codex/mimo versions or auth blockers are summarized; no code changes; no secrets; no force push; no push to main
```

Do not route implementation, repair, GitHub review, or production mutation work to hostvds-agent-01 until:

- A fresh probe proves execution on `mesh-agent-01`.
- GitHub auth status is checked without printing secrets.
- Codex/MIMO runner auth is checked or explicitly marked blocked.
