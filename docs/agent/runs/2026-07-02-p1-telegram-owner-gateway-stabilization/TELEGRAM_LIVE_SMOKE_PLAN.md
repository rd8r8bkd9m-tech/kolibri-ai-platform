# Telegram Live Smoke Plan

Task id: P1_TELEGRAM_OWNER_GATEWAY_STABILIZATION_2026_07_02
Date: 2026-07-02
Scope: future owner-approved non-mutating live smoke only.
Status: not executed by this task.

## Current Task Decision

This run does not call live Telegram APIs, does not consume updates, does not change webhook or poller state, and does not restart services. Validation for this artifact gate is fake Telegram/fake Control Plane only.

## Preconditions For Any Future Live Smoke

- Explicit owner approval for the exact time window.
- Confirm the active production receiver and delivery mode out of band.
- Confirm no competing webhook/poller mutation task is active.
- Confirm no credential rotation, BotFather mutation, deploy, restart, or service file change is bundled into the smoke.
- Use only an owner private chat.
- Have a rollback/stop plan that does not require deleting webhooks or resetting offsets unless separately approved.

## Allowed Non-Mutating Smoke Checks

Only after approval:

- Send `/help` from the owner private chat and verify concise Russian help.
- Send `/nodes` and verify a summarized fleet answer without raw node IDs.
- Send `/agents` and verify a summarized agent answer without agent IDs/PIDs.
- Send `/queue` and verify summarized queue counts without task IDs or prompts.
- Ask a simple chat/status question and verify no paths, IDs, prompts, logs, or secrets appear.

## Forbidden During Smoke

- `setWebhook`
- `deleteWebhook`
- `getUpdates` from any ad hoc process that could steal production updates
- `setMyCommands`
- `setChatMenuButton`
- Bot token rotation or BotFather changes
- Service restart, deploy, systemd change, or poller offset reset
- `/task`, `/cancel`, `/retry`, or any command that creates, cancels, retries, deploys, merges, bills, or contacts external users
- Web/frontend, Mini App, billing, FormulaLM, model gateway, Control Plane P0, lease storm, PR #119, or PR #121 actions

## Evidence To Capture

- Timestamped owner-approved window.
- Exact command list.
- Sanitized screenshots or copied owner-visible text with private details removed.
- Confirmation that no forbidden Bot API methods or service mutations were run.
- Post-smoke decision: pass, fail, or blocked.

## Pass Criteria

- Replies are Russian and owner-readable.
- No raw internal IDs, paths, logs, env values, credentials, prompts, webhook/poller state, or queue records appear.
- No production delivery-state mutation occurs.
- No unrelated subsystem is touched.

