# Actions

Read-only commands executed:
- `pwd`
- `hostname`
- `id -un`
- `git status --short`
- `df -h /`
- `git branch --show-current`
- `git rev-parse --short HEAD`
- sanitized `git remote -v`
- `command -v gh`
- `command -v codex`
- `command -v python3`
- `command -v curl`
- `systemctl is-active` / `systemctl is-enabled` for `kolibri-factory-control.service` and `kolibri-agent-host.service`
- status-code-only `curl` probes against local Control Plane/API routes
- `bash scripts/preflight-factory-control-runtime.sh "$PWD"`

Secret handling:
- No credential helper was invoked.
- No environment file contents were read.
- No token, cookie, private key, account name or raw auth output is recorded.
- Git remote output was sanitized before use.

Repository mutation:
- Product code was not modified.
- Only this run artifact directory was created.

