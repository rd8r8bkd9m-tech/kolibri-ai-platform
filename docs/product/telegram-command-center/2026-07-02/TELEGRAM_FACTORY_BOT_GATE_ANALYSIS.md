# Telegram Factory Bot Gate Analysis

Task: `P0_AUTOPILOT_EXTRA_41_TELEGRAM_FACTORY_BOT_GATE_2026_07_02`
Date: 2026-07-02
Node: `kolibri`
Agent: `autonomous_engineer`
Scope: repository-only analysis of current Telegram factory bot behavior, command menu cleanup needs, AI/factory integration gaps, and PR-sized next tasks.

This artifact does not authorize live Telegram mutation. No Bot API method was called, no token value was read or printed, and no product runtime was changed.

## Current Behavior

The checked-in gateway is `ops/telegram_gateway.py`.

- Receiver model: long polling through `TelegramClient.get_updates`, guarded by `telegram_superfactory.plan_update_receiver`. Startup refuses ordinary polling when webhook configuration is present unless the receiver mode explicitly allows polling.
- Safety gate: delivery-state mutation methods `deleteWebhook`, `setWebhook`, `logOut`, and `close` are denied by default in `TelegramClient.call`. Owner-approved webhook deletion is isolated in `ops/telegram_webhook_migration.py`.
- Auth gate: private chat only, with configured owner Telegram IDs. Unauthorized users receive a short denial message.
- Natural language routing:
  - image requests produce `telegram_image_generation` envelopes through `build_image_envelope`;
  - work requests produce `owner_remote_task` envelopes through `build_task_envelope`;
  - chat messages produce `owner_remote_task` chat envelopes through `build_chat_envelope`.
- Factory integration: envelopes are submitted to Factory Control via `/v1/tasks`; node and task snapshots are read from `/v1/nodes` and `/v1/tasks`; transitions are tracked in gateway state.
- Owner-facing hygiene: status and completion formatting removes task ids, nodes, agent ids, internal paths, token-like strings, and noisy runtime failures before sending replies.
- Memory: `StateStore` persists owner conversation context and work-task expectations so follow-up messages can reference prior requests.

## Command Menu Cleanup Need

The live menu should stay minimal and owner-facing:

- `/start`
- `/status`
- `/help`

The current code still implements operational slash commands in `Gateway.handle_command`:

- `/task <text>`
- `/status <task_id>`
- `/cancel <task_id>`
- `/retry <task_id>`
- `/nodes`
- `/agents`
- `/queue`

This is acceptable as internal parser compatibility, but it is not acceptable as a public BotFather/menu surface. The command menu cleanup task should separate "advertised commands" from "legacy accepted commands":

- advertise only `/start`, `/status`, and `/help`;
- keep unadvertised operational commands only if owner-only and covered by tests;
- avoid calling `setMyCommands` from CI, tests, or ordinary startup;
- make any real menu update a separate owner-approved runtime operation with a dry-run artifact first.

## AI And Factory Integration Gaps

- Chat answers depend on factory task execution. There is no direct, short-lived AI response API for simple owner Q&A except deterministic shortcuts behind `TELEGRAM_DETERMINISTIC_SHORTCUTS`.
- Runner choice is mostly environment-driven. Chat defaults to `codex`; image defaults to `image`; generic work defaults to `generic_implementation`.
- Mini App owner auth is partially available as a pure helper in `ops/telegram_superfactory.py`, but backend session issuance and protected command-center APIs are not implemented.
- The bot and Mini App do not share a normalized task report model. Bot output is plain text/photo/edit-message, while the Mini App reads only normalized factory status.
- PR/CI/artifact data is not exposed as a unified sanitized read model for owner task details.
- Task mutation safety exists at the bot command level only through owner chat authorization. It lacks a richer session confirmation model for cancel, retry, drain, deploy, merge, and live bot mutations.
- Rich messages and streaming are future work. The gateway can stream partial text by editing/sending messages, but it has no Bot API rich-message adapter.

## PR Task Queue

1. Menu contract PR: add an explicit static advertised command contract for `/start`, `/status`, `/help`, tests proving legacy operational commands are not part of the advertised menu, and a no-live-`setMyCommands` guard.
2. Owner auth backend PR: add Mini App `initData` verification endpoint, short-lived session issuance, role mapping, replay/staleness tests, and redaction fixtures.
3. Read-only command-center API PR: add protected bootstrap/task/fleet read models from the existing control plane, with sanitized task detail and artifact summaries.
4. Bot report model PR: introduce a normalized internal report object shared by bot text rendering and future Mini App task detail rendering.
5. Safe task action PR: add explicit confirmation/audit contracts for cancel and retry before exposing them in Mini App UI.
6. PR/CI/artifact read PR: standardize sanitized artifact manifests and PR/CI links without merge/deploy actions.
7. Rich message adapter PR: add capability-gated rich report rendering with plain text fallback; do not include draft streaming yet.

## Blockers

- Live Telegram menu state was not inspected because that can require token use or Bot API calls.
- GitHub PR queue state was not inspected from this node because the current task is repository-only and no `gh`-authenticated workflow is guaranteed.
- Runtime service state was not changed. Starting or restarting the gateway could consume Telegram updates and must be a separate owner-approved receiver operation.

## Russian Owner Summary

Текущий Telegram-бот уже умеет принимать приватные сообщения владельца, отличать разговор от задач и генерации картинок, отправлять задачи в фабрику и возвращать очищенные статусы без служебных путей, node/agent/id и секретоподобных строк. Главный долг: меню бота должно быть простым и безопасным для владельца (`/start`, `/status`, `/help`), а старые команды `/task`, `/cancel`, `/retry`, `/nodes`, `/agents`, `/queue` нельзя рекламировать в меню. Следующая точная задача: сделать PR с контрактом меню и тестами, без живого вызова `setMyCommands` и без изменения Telegram runtime.
