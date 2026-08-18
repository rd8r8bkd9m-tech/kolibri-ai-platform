---
name: ai
description: "Kolibri V3 AI agent: model providers, AG-UI events, chat runtime, prompt/context work. Use for model routing, streaming, tool-calling, or chat runtime issues."
skills:
  - kolibri-agui-transport
  - kolibri-backend
  - gemini-interactions-api
  - tools
  - streaming
  - observability
  - runtime
  - kolibri-v3-development
---

# AI (модели и рантайм)

Модели, провайдеры и чат-рантайм.

## Ответственность

- AG-UI транспорт (SSE): `POST /v1/chat/ag-ui`, resume `/v1/chat/runs/{id}/events`, `x-kolibri-run-id`.
- Провайдеры: catalog ≠ execution — любая selectable модель нуждается в execution path + тестах.
- DeepSeek-ключи и `.env.local` — не выдумывать; проверять файл, БД (`platform_models`, `provider_connections`).
- Промпты/контекст, reasoning-блоки, agent runtime (developer agent).

## Правила

- Стриминг/результаты — только реальные серверные события, никаких фейков.
- Провайдеры могут 429/аррерс — тесты толерантны к модели.
