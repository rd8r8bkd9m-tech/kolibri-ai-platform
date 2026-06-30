# Дайджест проекта Kolibri Factory для ChatGPT

```yaml
project: Kolibri Factory
server_execution_required: true
task_id: 2026-06-30-full-project-scan-for-chatgpt
thin_client_invariant: true
```

## Статус скана

- Статус: выполнен read-only скан репозитория и Control Plane контекста.
- Узел выполнения: `primary-candidate`, hostname `kolibri`, lease owner `primary-candidate:agent-host-primary`.
- Проверка ОС до скана: `Linux kolibri 6.8.0-36-generic ... x86_64 GNU/Linux`; это не macOS.
- Worktree: `/var/lib/kolibri-agent/worktrees/2026-06-30-full-project-scan-for-chatgpt/2026-06-30-full-project-scan-for-chatgpt-attempt-1/repo`.
- Ветка скана: `agent/2026-06-30-full-project-scan-for-chatgpt/read-only-scan`.
- Продуктовый код не изменялся; записаны только документы в `docs/agent/intelligence/2026-06-30-full-project-scan-for-chatgpt/`.
- Деструктивные git-команды не запускались; checkout веток не выполнялся.
- Анализ веток выполнен через `git ls-remote` и временный mirror clone в директории скана; fallback на локальные refs был готов, но не потребовался.
- Секреты и env values не печатались; совпадения по словам `secret/token/key/cookie/credential` зафиксированы только на уровне путей.

## Быстрая карта проекта

Kolibri AI Platform сейчас выглядит как монорепозиторий для AI-платформы и фабрики удаленных агентов. В нем есть FastAPI backend, React/Vite frontend, Control Plane sidecar, persistent Agent Host, Telegram gateway, mesh bridge, training scripts и сетевой Organism API. README описывает 5-серверную WireGuard mesh архитектуру: Home, Main, UIAP, QJNS, 9FTS.

## 30 пунктов контекста

1. Репозиторий небольшой по размеру: 66 tracked files, около 11.7k строк в просканированных текстовых файлах.
2. Основной backend расположен в `backend/`; главный FastAPI entrypoint: `backend/main.py`.
3. Backend хранит cache/conversations/messages/rate_limits в SQLite по пути `/opt/kolibri-ai/data/kolibri.db`.
4. Backend предоставляет `/api/chat`, `/ws/chat`, conversation CRUD, TTS/STT/search/tools, `/api/pipeline`, `/api/pipeline/health`, `/api/factory/status`, `/cluster/status`.
5. `backend/providers.py` содержит менеджер AI-провайдеров; полная оценка провайдеров требует отдельного секрет-безопасного скана конфигурации окружения на сервере.
6. `backend/pipeline.py` реализует intent routing между chat/RAG/agent, с hardcoded mesh endpoints `10.99.0.3:8002`, `10.99.0.4:8003`, `10.99.0.5:8001`.
7. RAG/inference/agent вызовы сделаны через `httpx.AsyncClient`; fallback в RAG/agent цепочках частично деградирует ответ без падения всей цепочки.
8. `backend/factory_status.py` нормализует Control Plane nodes/tasks/health в формат для UI.
9. `backend/estimate_engine.py`, `backend/document_engine.py`, `backend/pdf_engine.py` дают deterministic estimate/document/PDF контур с кириллицей.
10. `backend/routes_v1.py` и `backend/adapter.py` дублируют OpenAI-like/legacy v1 endpoints; стоит проверить, какой entrypoint реально деплоится.
11. Frontend расположен в `frontend/`, React 19 + Vite + Framer Motion + ReactMarkdown.
12. `frontend/src/App.jsx` объединяет чат, WebSocket streaming, документы, поиск и factory/cluster view.
13. UI дергает `/api/providers`, `/api/chat`, `/ws/chat`, `/api/factory/status`, `/api/knowledge`, `/rag/search`.
14. В backend scan не найдено реализаций `/api/knowledge` и `/rag/search` в основном приложении, кроме proxy/fallback ожиданий; это важный интеграционный разрыв.
15. `frontend/src/components/MessageBubble.tsx` выглядит как более новый компонент с document mode, copy/download/edit flows, но текущий `App.jsx` его явно не использует.
16. `ops/factory_control.py` - стандартно-библиотечный Control Plane sidecar поверх Redis RESP, с task queue, leases, heartbeat, retry/dead-letter и review task creation.
17. `ops/agent_host.py` - persistent remote executor: регистрирует node heartbeat, leases tasks, готовит worktree/artifact dirs, запускает generic tasks, image generation, telegram chat и factory smoke handlers.
18. Agent Host поддерживает failover по нескольким Control Plane URLs.
19. `ops/kolibri-dispatch` - CLI к Control Plane: doctor/nodes/submit/status/collect/cancel/drain плюс legacy SSH launch mode.
20. `ops/telegram_gateway.py` - длинный Telegram long-polling gateway: owner routing, task/chat/image envelopes, human-safe summaries, state memory, image delivery.
21. `ops/mesh_control_bridge.py` синхронизирует mesh node shadows и создает Control Plane tasks из mesh messages.
22. `infra/network/api.py` и `infra/network/organism.py` почти зеркальны и реализуют Redis-backed organism/job/state/node API; дублирование требует отдельного решения.
23. Systemd units есть для factory control, telegram gateway, agent host, mesh bridge.
24. Training scripts лежат в `scripts/training/` и покрывают dataset generation/preparation, finetune, adapter merge; это не основной production path.
25. Тесты есть на factory runtime contracts, Control Plane states, Telegram gateway behavior, Agent Host chat/image, mesh bridge, factory status, estimate/document/PDF engines.
26. CI workflow есть в `.github/workflows/ci.yml`; отдельный GitHub Actions API scan не выполнялся, потому что задача не требовала печати auth/env и достаточно было read-only refs.
27. Remote heads доступны: `git ls-remote --heads origin` успешен, mirror clone успешен.
28. Количество remote heads в mirror: 93; много веток `agent/*`, `codex/*`, `factory/*`, плюс `main` и `p0/telegram-miniapp-kolibriai-deploy`.
29. Control Plane `/v1/nodes` показывает активный server lease на `primary-candidate`; это подтверждает, что скан исполнялся не на Mac thin client.
30. Главные blockers: несогласованность frontend endpoints с backend routes, hardcoded mesh endpoints, дублирование organism API, перегруженный Telegram gateway, и необходимость отдельной секрет-безопасной проверки provider/env конфигурации.

## Ветки и git

- Текущая ветка: `agent/2026-06-30-full-project-scan-for-chatgpt/read-only-scan`.
- Base ref из envelope: `origin/main`.
- Remote branch count по mirror: 93 (`agent/*`: 41, `codex/*`: 36, `factory/*`: 14, `main`: 1, `p0/*`: 1).
- Локальные heads: `main` и текущая task branch.
- `git ls-remote --heads origin`: успешно, значит GitHub read/auth/network для refs доступен.
- Первая попытка mirror clone с аргументом `origin` классифицирована как локальная command-form ошибка, не как GitHub/network/auth failure; повтор с `git remote get-url origin` успешен.

## Секреты и редактирование

Файлы с совпадениями по секрет-чувствительным словам: `infra/network/config.json`, `scripts/training/finetune.py`, `scripts/training/merge_adapter.py`, `backend/pipeline.py`, `backend/main.py`, `tests/test_agent_host_image_generation.py`, `tests/test_telegram_gateway.py`, `ops/kolibri-dispatch`, `ops/telegram_gateway.py`, `ops/install-telegram-secret.sh`, `ops/agent_host.py`. Значения не копировались и не раскрывались.

## Топ blockers

- Frontend ожидает knowledge/RAG endpoints, которые не очевидны в основном backend app.
- Mesh service URLs в `backend/pipeline.py` hardcoded; это усложняет переносимость и failover.
- `infra/network/api.py` и `infra/network/organism.py` выглядят как полные дубликаты.
- `ops/telegram_gateway.py` очень большой и смешивает routing, formatting, delivery, state, image handling.
- Provider/env матрица не может быть честно завершена без отдельного server-side secret-safe config inventory.

## Следующая рекомендуемая задача

Сделать P0 integration contract audit: сопоставить frontend routes, backend routes, Control Plane routes и deployed systemd units; выпустить минимальный contract matrix и исправить только несовпадающие endpoint contracts с тестами.
