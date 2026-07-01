# Risk register

| ID | Risk | Severity | Evidence | Mitigation |
|---|---|---:|---|---|
| R1 | PR #46 is too broad | P0 | PWA, billing, autonomy, estimates, FormulaLM in one draft | split into focused PRs |
| R2 | Agent runner artifact path drift | P0 | P0 audit/repair tasks failed with missing expected files | harden runner contract |
| R3 | No-push/read-only enforcement suspect | P0 | prior scan branch was pushed despite no-push style request | enforce envelope constraints in runner |
| R4 | `uiap` disk free 0 GB | P0 | CP node card | free disk, add reserve monitor |
| R5 | `qjns` disk free 0 GB | P0 | CP node card plus clone/auth issue memory | free disk, fix clone path |
| R6 | Server GitHub auth broken | P0 | noninteractive HTTPS fetch failed | configure safe machine auth without printing secrets |
| R7 | Direct SSH to most servers times out | P1 | 18/20 unreachable from Mac route | fix jump/VPN/firewall docs |
| R8 | Runtime repos dirty | P1 | main and primary-candidate dirty | preserve diffs, audit, decide keep/drop |
| R9 | Queue/backlog degraded | P1 | `/v1/tasks` queue truncated, P0 issues | improve dispatchability and stale lease handling |
| R10 | FormulaLM boundary unclear | P1 | no standalone module in main, large research branch | write contract and remote-only guard |
| R11 | Billing mixed with frontend/autonomy | P1 | PR #46 body and scope | isolate billing scaffold PR |
| R12 | Branch/worktree sprawl | P2 | 126 matrix rows, 30 worktrees | archive after artifact preservation |
| R13 | GitHub branch protection unknown | P2 | API limitation response | document manual protection/rulesets |
| R14 | Mac disk low for heavy work | P2 | 22 GiB free | keep heavy tasks server-side |
