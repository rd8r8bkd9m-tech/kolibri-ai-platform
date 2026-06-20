# OpenClaw Frontend Agent Runbook

Kolibri uses OpenClaw as an optional frontend/design agent, not as a release authority. Codex remains the reviewer and release gate.

## Official Setup Notes

- OpenClaw should be installed from the official installer: `curl -fsSL https://openclaw.ai/install.sh | bash`.
- Xiaomi MiMo provider setup should use the official provider ids:
  - `xiaomi` for pay-as-you-go keys.
  - `xiaomi-token-plan` for Token Plan keys.
- Token Plan keys use `XIAOMI_TOKEN_PLAN_API_KEY` or OpenClaw's Token Plan auth choices. Do not store API keys in manifests, prompts, logs, or repo files.
- Preferred model for the frontend agent is `xiaomi-token-plan/mimo-v2.5-pro`.

References:

- https://docs.openclaw.ai/providers/xiaomi
- https://mimo.mi.com/docs/en-US/tokenplan/integration/openclaw
- https://docs.openclaw.ai/cli/agent

## Runtime Contract

OpenClaw tasks must go through `scripts/mimo_task_runner.py` with:

- `agent_backend: "openclaw"`
- `openclaw_agent: "kolibri-frontend"`
- `mode: "read_only"` for audit/QA, or `mode: "controlled_mutation"` for draft patches.
- Explicit `budget` with max cost/token/runtime guard.
- `allowed_paths` limited to frontend, docs, reports, and browser QA artifacts.

The runner invokes OpenClaw through argv, never shell interpolation:

```bash
python3 scripts/mimo_task_runner.py validate --manifest ops/tasks/frontend-ux-audit-openclaw.json
python3 scripts/mimo_task_runner.py run-ssh --manifest ops/tasks/frontend-ux-audit-openclaw.json
```

## Safety Rules

- Claw may draft frontend patches, but cannot merge, deploy, restart services, buy servers, or change HostVDS state.
- Claw must not read or write `.env`, `.ssh`, `.mimocode`, auth files, private keys, tokens, or raw logs with secrets.
- Every result must include `status`, `summary`, `changed_files`, `checks`, `risks`, and `artifacts`.
- Codex must inspect diff and checks before accepting any Claw output.

## Frontend Quality Lane

1. `frontend-ux-audit-openclaw`: read-only UX audit and bounded backlog.
2. `frontend-design-patch-openclaw`: controlled draft patch for Agent Ops SaaS UI.
3. `frontend-browser-qa`: QA review across desktop/mobile and console errors.
4. `frontend-polish-pass-openclaw`: only fixes Codex/QA-listed issues.

Acceptance gates:

- `npm --prefix frontend run lint`
- `npm --prefix frontend run build`
- Browser smoke for Overview, Agents, Tasks, Servers, Reports, Chat, Docs, and Search.
- No secret leakage in prompts, logs, reports, or artifacts.
