# Home Visibility Recovery Diagnostic Actions

## Actions Performed

- Confirmed execution is on server host `kolibri`, user `root`, kernel `Linux 6.8.0-36-generic x86_64`, branch `agent/P0_HOME_HOME_LIVE_AGENT_HOST_RECOVERY_DIAGNOSTIC_2026_07_02/generic`, head `f7ac32c70406`.
- Confirmed local Git remote is `git@github.com:rd8r8bkd9m-tech/kolibri-ai-platform.git`.
- Confirmed `git ls-remote --exit-code origin HEAD` succeeds from this server worktree and returns `f7ac32c70406432a52752ca45d87e35d9f1facd3`.
- Inspected `home` and `kolibri-home` short SSH aliases with `ssh -G`; both resolve to user `ladik`, host `10.99.0.1`, public-key auth, and redacted identity files.
- Attempted bounded SSH probe to `home` for hostname, user, `kolibri-agent-host.service`, tmux sessions, repo head, and remote GitHub access.
- Attempted bounded SSH probe to `kolibri-main` and bounded multi-alias topology probe.
- Queried Control Plane health and nodes at `http://10.99.0.10:9101`.
- Queried local factory status endpoint at `http://127.0.0.1:8000/api/factory/status`.
- Queried current task envelope and required artifact paths from Control Plane.

## Not Performed

- No production service restart.
- No route, DNS, firewall, or credential mutation.
- No destructive git command.
- No force push.
- No push to `main`.
- No secret material printed or copied into artifacts.

