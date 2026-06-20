# Kolibri Agent Factory

Codex is the chief reviewer/release agent. Mimo/OpenClaw workers are bounded executors.

## Control Plane

Local state:

```text
.factory/runs/agent_factory_state.json
.factory/runs/last_report.json
logs/agent-factory/state.json  # legacy fallback only
```

Commands:

```bash
python3 scripts/agent_factory.py init
python3 scripts/agent_factory.py enqueue-wave --wave bootstrap --mode read_only
python3 scripts/agent_factory.py dispatch --limit 8 --max-workers 6
python3 scripts/agent_factory.py collect
python3 scripts/agent_factory.py report
python3 .factory/scripts/factory_status.py
```

Long-running loop:

```bash
nohup python3 scripts/agent_factory.py loop --interval 300 --limit 8 --max-workers 6 \
  > .factory/logs/factory.log 2>&1 &
```

Systemd unit template:

```bash
sudo cp infra/systemd/kolibri-agent-factory.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kolibri-agent-factory
```

## Operating Rules

- Agents do not push, merge, or deploy.
- Read-only tasks are allowed by default.
- Controlled mutations require a specific task and Codex review of diff/tests.
- Secrets are forbidden in prompts and logs: `.env`, `.ssh`, auth files, tokens, browser profiles, `.mimocode`.
- Codex collects `result.json`, reviews changed files and checks, then decides merge/deploy.

## Current Bootstrap Wave

Do not start the full bootstrap wave until the two canary envelopes under
`.factory/tasks/ready/` pass dry-run and live read-only review.

Each enabled server receives one role-specific read-only task:

- Backend: FormulaLM provider contract, cache key, RAG/API, `Intent.AUTO`.
- Frontend/design: provider selection, cluster status, chat QA.
- Infra: VPN/nginx/systemd/routing, worker completion endpoint.
- QA/security: shell injection, no-secrets, browser smoke.
- Docs: runbook drift and status docs.
- FormulaLM: Proof v1 readiness and evaluator contract.

## Status Meaning

- `queued`: task is waiting for dispatch.
- `running`: remote detached runner started.
- `completed`: worker returned exit code 0.
- `failed`: worker returned non-zero or invalid result.
- `timeout`: task exceeded timeout.
- `dispatch_failed`: SSH/upload/start failed.
- `collect_failed`: result retrieval failed.

## Reviewer Loop

Codex should run:

```bash
python3 scripts/agent_factory.py collect
python3 scripts/agent_factory.py report
```

Then inspect any completed worker artifacts before merge/deploy.
