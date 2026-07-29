# Owner developer agent

Kolibri V3 exposes an optional developer mode in the product chat. The toggle
is rendered only for an authenticated `owner`. Enabling it sends
`executionMode: "developer"` as a request hint; the backend independently
checks the HttpOnly session role, the server feature gate, and the configured
workspace before accepting the run.

## Local development

Set these server-side variables:

```dotenv
KOLIBRI_V3_DIRECT_MODEL_RUNTIME=true
KOLIBRI_V3_DEVELOPER_AGENT_ENABLED=true
KOLIBRI_V3_DEVELOPER_WORKSPACE_ROOT=/absolute/path/to/kolibri-ai-platform
KOLIBRI_V3_DEVELOPER_AGENT_TIMEOUT_SECONDS=1800
```

The machine running the backend must already be logged in through Codex CLI.
No OpenAI API key is stored in the application. A developer turn starts an
ephemeral Codex thread with:

- the default local Codex environment enabled, including shell/filesystem
  tools;
- `cwd` and runtime workspace roots fixed to the configured repository;
- `danger-full-access` sandboxing in local development after explicit owner
  approval;
- non-interactive `never` approval policy;
- repository `AGENTS.md` instructions;
- command and file-change activity projected into bounded AG-UI tool cards.

Each accepted run records its owner authority, workspace reference, sandbox
profile, and approval policy in `chat_run_execution_contexts`.

## Deliberate boundaries

Developer mode has unrestricted local shell access in the explicitly approved
development runtime. Its command and file activity remains audited in Product
Chat. The agent must not print secret values into chat responses.

The local adapter is rejected when `KOLIBRI_V3_ENV=production`. Production
must preserve Logical Home as the sole control authority and route Codex work
to the Provider Execution Authority through a versioned, authenticated,
audited command contract.

## Verification

```bash
cd kolibri-v3
npm run typecheck
npm test
PYTHONPATH=backend ../backend/venv/bin/python -m pytest -q \
  backend/tests/test_codex_app_server.py \
  backend/tests/test_identity_api.py
```
