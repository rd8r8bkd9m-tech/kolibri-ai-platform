# Mac local state

Snapshot date: 2026-06-30.

## Host

- hostname: `MacBook-Air-Vladislav.local`
- OS: Darwin/macOS, arm64.
- user: `kolibri`
- repo root: `/Users/kolibri/.codex/worktrees/065e/kolibri-ai-platform`
- current shell: `zsh`
- disk on current filesystem: 228 GiB total, 178 GiB used, 22 GiB available, 89% used.

## Tooling

- git: available, version 2.53.0.
- node: `v25.2.0`.
- npm: `11.6.2`.
- python3: `3.9.6`.
- python3.12: `3.12.13`.
- rustc/cargo: `1.91.1`.
- docker: `29.3.1`.
- GitHub CLI: available at `/opt/homebrew/bin/gh`, not in default PATH during scan.
- ssh: available.

## Git state

- current branch: detached `HEAD`.
- current head: `6d0317c52a9694448ee2c352dc196ce7a27b9487`.
- head subject: `Merge pull request #45 from rd8r8bkd9m-tech/codex/version-mesh-control-bridge`.
- status: only untracked `docs/`.
- tracked diff: empty.
- staged diff: empty.
- remote: `origin` points to GitHub repo `rd8r8bkd9m-tech/kolibri-ai-platform`.

## Mac role

For this task, Mac is a permitted development/analysis workstation and command center. Heavy runtime validation, remote-only model work, server deploys, and multi-node tasks should still run through server Control Plane.

## Readiness

Mac is ready for:

- docs and intelligence artifacts.
- branch/PR analysis.
- frontend build/light checks when needed.
- backend unit test selection when dependencies are available.
- safe PR preparation.
- Control Plane task dispatch.

Mac is not ideal for:

- FormulaLM/GPU/inference benchmarks.
- full cluster validation.
- tasks requiring all 20 servers by direct SSH, because most configured routes timed out from Mac.
