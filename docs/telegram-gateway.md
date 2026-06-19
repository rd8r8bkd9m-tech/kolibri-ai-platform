# Telegram Task Gateway

`scripts/telegram_task_gateway.py` is the first safe Telegram intake layer for
Kolibri agent tasks. It does not launch Mimo, SSH, browsers, deploys, email, or
paid services. It only accepts allowlisted Telegram users, creates a task
manifest, and validates that manifest through `scripts/mimo_task_runner.py`.

## Safety Model

- Tokens and user allowlists come from environment variables only.
- Telegram user IDs are restricted by `KOLIBRI_TELEGRAM_ALLOWED_USER_IDS`.
- `/submit` writes a manifest into `ops/tasks/telegram-queue` by default.
- Validation uses `subprocess.run([...], shell=False)` with argv lists.
- The gateway calls runner `validate` and `report` only.
- Controlled mutation requires `/submit --controlled --approve-controlled-mutation ...`.
- Deploy requests are rejected in this MVP.
- Queued manifests still require a separate Codex/operator approval before any
  `run-local` or `run-ssh` runner invocation.

## Commands

`/help`

Returns supported commands and safety notes.

`/status`

Returns queue count and a 12-hour runner log summary.

`/submit <task text>`

Creates a read-only draft manifest, validates it, and reports the artifact path.
No agent is started.

`/submit --controlled --approve-controlled-mutation <task text>`

Creates a controlled-mutation draft manifest with required checks, validates it,
and leaves it queued for Codex review. It is not executed automatically.

## Environment

Use `ops/telegram.example.env` as the runtime template. Keep real values out of
git and service files committed to the repository.

Required:

- `TELEGRAM_BOT_TOKEN`
- `KOLIBRI_TELEGRAM_ALLOWED_USER_IDS`

Optional defaults:

- `KOLIBRI_TELEGRAM_QUEUE_DIR=ops/tasks/telegram-queue`
- `KOLIBRI_TELEGRAM_LOG_DIR=logs/agent-runs`
- `KOLIBRI_TELEGRAM_DEFAULT_SERVER=local`
- `KOLIBRI_TELEGRAM_DEFAULT_WORKTREE=.`
- `KOLIBRI_TELEGRAM_READONLY_ALLOWED_PATHS=.`

## Local Smoke Checks

Run compile and self-test without Telegram network access:

```bash
python3 -m py_compile scripts/mimo_task_runner.py scripts/telegram_task_gateway.py
python3 scripts/telegram_task_gateway.py self-test
```

Handle one command locally:

```bash
KOLIBRI_TELEGRAM_ALLOWED_USER_IDS=12345 \
python3 scripts/telegram_task_gateway.py handle \
  --user-id 12345 \
  --text '/submit Review docs for stale agent runbook notes'
```

Validate the sample manifest:

```bash
python3 scripts/mimo_task_runner.py validate \
  --manifest ops/tasks/telegram-gateway-readonly.json
```

## Run The Poller

After exporting real runtime env values:

```bash
python3 scripts/telegram_task_gateway.py run
```

For a future service manager, inject env vars through the manager secret/env
mechanism. Do not write the real bot token into committed files.

## Operational Notes

- Queue artifacts may include user-submitted task text. The script creates the
  queue directory with mode `0700` when possible.
- A validation failure leaves the manifest artifact in queue for inspection but
  reports `status=failed`; do not execute failed manifests.
- The MVP has no automatic dispatcher. A separate reviewed orchestrator step
  must decide whether and how to call `mimo_task_runner.py run-local` or
  `run-ssh`.
