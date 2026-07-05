# Bootstrap Truth

Bootstrap/deploy/install files are protected. This branch may contain real operational history and local generated output.

| Path | Purpose | Safe Actions | Dangerous Actions | Approval |
| --- | --- | --- | --- | --- |
| `scripts/deploy.sh` | deploy script | read, review, lint | production deploy/restart | required |
| `ops/install-telegram-secret.sh` | Telegram secret installer | read, review | write/rotate secret | required |
| `docs/superfactory/NEW_SERVER_API_BOOTSTRAP.md` | server API bootstrap docs | read, document | live bootstrap | required |
| `.factory/runs/*bootstrap*` | historical run evidence | read non-secret metadata | rerun/mutate server | required |
| `bootstrap.js` | bundled/runtime bootstrap-like JS | avoid editing unless scoped | executing unknown bootstrap | required |
| `artifacts/*/05_deployment_notes.json` | release/deploy notes | read/review | production action | required |

If a file contains or appears to contain a secret, record only `SECRET_RISK_FOUND_REDACTED` and do not print the value.
