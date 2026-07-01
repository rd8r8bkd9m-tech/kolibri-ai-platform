# Локальная карта рабочей копии

Task ID: `2026-06-30-project-intelligence-all-branches`

Этот файл дополняет серверный handoff. Он описывает текущую локальную рабочую копию на Mac в read-only режиме. Это не заменяет полный серверный all-branches intelligence pack: ветки не переключались, remote refs не fetchились, зависимости не ставились, CI/GitHub API не опрашивались.

## Границы локального анализа

- Среда: macOS thin client, `MacBook-Air-Vladislav.local`.
- Git: detached `HEAD`, commit `6d0317c52a96`.
- До создания intelligence docs рабочее дерево выглядело чистым.
- После создания handoff/local docs dirty tree состоит из `?? docs/`.
- Локально выполнены только безопасные чтения структуры, ключевых файлов и конфигов.
- Секреты и значения токенов не публикуются.

## Быстрый вывод

Локальная копия содержит компактный, но уже многослойный Kolibri AI Platform:

- `backend/` — FastAPI gateway, чат, WebSocket, SQLite-кеш/история, TTS/STT/search, unified pipeline, factory status adapter, сметный калькулятор, документы и PDF.
- `frontend/` — React/Vite интерфейс: чат, вкладки документов/поиска/сети, статус фабрики, визуальный Kolibri bird.
- `ops/` — новый factory runtime: Control Plane sidecar, Agent Host, Telegram gateway, mesh-to-control bridge, dispatch CLI, systemd units.
- `infra/network/` — legacy/mesh organism API, nginx, network config.
- `scripts/training/` — Qwen2.5-1.5B LoRA pipeline: synthetic data, dataset prep, finetune, adapter merge.
- `tests/` и `backend/tests/` — контрактные тесты factory runtime, Telegram redaction, image generation, factory status, deterministic estimates/PDF.
- `.github/workflows/ci.yml` — CI с Python compile, pytest, frontend build, JSON/YAML validation, secret scan и secret-path guard.
- `SERVER_INVENTORY_LOCAL.md` — локальная карта всех серверов/узлов, известных из repo, без live-аудита.

Главный архитектурный разрыв: `README.md` описывает Kolibri как mesh из 5 серверов и быстрый запуск, а код в `ops/` уже добавляет Control Plane / Agent Host / Telegram owner gateway / review lifecycle. Документацию нужно синхронизировать с фактическим factory runtime.

## Файловая форма проекта

По локальному видимому дереву без `.git`, `node_modules`, virtualenv, build/dist:

| Зона | Примерный смысл |
| --- | --- |
| `README.md` | Верхнеуровневое описание 5-серверной mesh-платформы. |
| `backend/` | FastAPI backend/gateway и доменные движки. |
| `frontend/` | React/Vite UI. |
| `ops/` | Factory runtime, agent host, Telegram, mesh bridge, systemd. |
| `infra/network/` | Mesh organism API, nginx, network inventory/config. |
| `scripts/training/` | LoRA training pipeline. |
| `tests/` | Основные pytest-контракты factory/runtime. |
| `backend/tests/` | Backend domain tests. |
| `.github/workflows/ci.yml` | GitHub Actions CI. |
| `docs/agent/intelligence/...` | Сгенерированные handoff/local intelligence docs. |

Приблизительное распределение локальных файлов: Python доминирует, затем frontend JS/TSX/CSS, systemd units, shell scripts, markdown docs и JSON configs.

## Git / локальное состояние

- Текущий checkout: detached `HEAD`.
- Commit: `6d0317c52a9694448ee2c352dc196ce7a27b9487`.
- Commit subject: `Merge pull request #45 from rd8r8bkd9m-tech/codex/version-mesh-control-bridge`.
- Author: `Владислав Кочуров`.
- Author date: `2026-06-28T03:15:03+03:00`.
- Текущий dirty tree после локального анализа: новые untracked docs в `docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/`.

Локально нельзя делать выводы о `main`, `primary-candidate`, `qjns` и других ветках без серверного all-branches анализа.

## Servers / Nodes

Отдельная локальная карта серверов создана в `SERVER_INVENTORY_LOCAL.md`. По статическим данным repo известны:

- `home` / `10.99.0.1` — training hub, Redis, mesh coordinator/chat, proxy jump;
- `main` / `10.99.0.2` — API gateway, frontend, likely Control Plane and owner gateway;
- `uiap` / `10.99.0.3` — RAG/knowledge;
- `qjns` / `10.99.0.4` — agent executor, но roster помечает как reserve/quarantined;
- `9fts` / `10.99.0.5` — inference and implementation worker;
- `new` — independent reviewer node from dispatcher/roster;
- `primary-candidate` — director/default Telegram target, needs remote clarification;
- `home-live` and `mesh-*` — mesh/default executor and bridge shadow nodes, need live Control Plane inventory.

Live состояние всех серверов не проверялось на Mac. Его должен собрать server-side Control Plane task.

## Backend / API

Ключевые файлы:

- `backend/main.py`
- `backend/routes_v1.py`
- `backend/adapter.py`
- `backend/pipeline.py`
- `backend/factory_status.py`
- `backend/providers.py`
- `backend/tts.py`
- `backend/stt.py`
- `backend/websearch.py`

Фактические API в `backend/main.py`:

- `GET /api/health`
- `GET /api/providers`
- `GET /api/models`
- `POST /api/chat`
- `WebSocket /ws/chat`
- `POST /api/conversations`
- `GET /api/conversations`
- `GET /api/conversations/{conv_id}/messages`
- `DELETE /api/conversations/{conv_id}`
- `POST /api/tts`
- `GET /api/tts/voices`
- `POST /api/search`
- `POST /api/tools`
- `POST /api/pipeline`
- `GET /api/pipeline/health`
- `GET /api/factory/status`
- `GET /cluster/status`
- wildcard proxy to `/api/knowledge`, `/api/agent`, `/api/inference`, `/cluster`

`backend/routes_v1.py` добавляет v1-заглушки и совместимость:

- `/api/v1/ai/models`
- `/api/v1/model/stats`
- `/api/v1/ai/chat`
- `/api/v1/ai/chat/stream`
- `/api/v1/ai/imagine`
- `/api/v1/ai/vision/analyze`
- `/api/v1/ai/demo/learn/text`
- `/api/v1/ai/quality/benchmark/history`
- `/api/v1/swarm/runtime/status`
- `/api/v1/ai/training/queue/status`
- `/api/v1/swarm/runtime/start|refresh|run`
- `/api/v1/swarm/runtime/ingest/text|url`
- `/api/v1/swarm/runtime/kpack/export|import`

Наблюдения:

- SQLite DB путь захардкожен как `/opt/kolibri-ai/data/kolibri.db`.
- CORS разрешен для всех origins.
- Rate limit реализован через SQLite таблицу `rate_limits`.
- `providers.py` сейчас фактически завязан на `mimo` CLI и возвращает остальные провайдеры как offline.
- `tool_call` не реализован.
- v1 image/vision/learning endpoints являются заглушками.

## Unified Pipeline / RAG / Agent / Inference

`backend/pipeline.py` маршрутизирует intent:

- `chat` — прямой inference path;
- `rag` — RAG search плюс inference;
- `agent` — agent chat;
- `auto` — эвристика по ключевым словам.

Захардкоженные mesh targets:

- RAG: `10.99.0.3:8002`
- Agent: `10.99.0.4:8003`
- Inference: `10.99.0.5:8001`

Риск: URL-ы сервисов и роли живут в коде, а не в едином service discovery/config contract. Для production readiness лучше вынести в env/config и синхронизировать с Control Plane node registry.

## Control Plane

Ключевой файл: `ops/factory_control.py`.

Назначение: минимальный Control Plane sidecar на standard library, Redis через собственный RESP-клиент.

Модель:

- namespace: `FACTORY_NAMESPACE`;
- Redis: `FACTORY_REDIS_HOST`, `FACTORY_REDIS_PORT`;
- lease duration: `FACTORY_LEASE_DURATION`;
- retry budget: `FACTORY_MAX_RETRIES`;
- task states: `queued`, `leased`, `running`, `waiting_review`, `review`, `completed`, `failed`, `cancelled`, `retry_scheduled`, `dead_letter`.

API:

- `GET /health`, `GET /v1/health`
- `GET /v1/nodes`
- `GET /v1/tasks`
- `GET /v1/tasks/<task_id>`
- `POST /v1/nodes/register`
- `POST /v1/nodes/<node_id>/heartbeat`
- `POST /v1/nodes/<node_id>/drain`
- `POST /v1/tasks`
- `POST /v1/tasks/lease`
- `POST /v1/tasks/<task_id>/heartbeat`
- `POST /v1/tasks/<task_id>/complete`
- `POST /v1/tasks/<task_id>/annotate`
- `POST /v1/tasks/<task_id>/fail`
- `POST /v1/tasks/<task_id>/cancel`

Важные свойства:

- idempotency через `idempotency_key`;
- lease renewal через task heartbeat;
- expired lease requeue/dead-letter;
- node draining;
- review task creation if result has PR URL and envelope requests review.

Ограничения/риски:

- Нет явной auth/authz на Control Plane endpoints в локальном коде.
- Нет отдельного persistent audit log, кроме Redis state.
- Control Plane хранит worktree/log paths в task state; owner-facing каналы должны редактировать это перед показом.
- Нет OpenAPI/schema docs для task envelope.

## Agent Host

Ключевой файл: `ops/agent_host.py`.

Назначение: постоянный worker, который регистрируется в Control Plane, heartbeat-ится, берет lease, создает node-local worktree/artifacts и исполняет task kind.

Найденные task kinds/пути:

- `read_only_probe`
- Telegram chat response через `mimo` или `codex`
- Telegram image generation через configured command или OpenAI Images API
- factory smoke implementation task
- retry error clearance task
- PR review task через local clone/fetch/checkout and optional `gh pr review`

Важные свойства:

- work root по умолчанию: `/var/lib/kolibri-agent/worktrees`;
- artifact root по умолчанию: `/var/lib/kolibri-agent/artifacts`;
- repo URL по умолчанию: GitHub repo `rd8r8bkd9m-tech/kolibri-ai-platform`;
- per-task artifacts include `result.json`, stdout/stderr logs and artifact manifest.

Риски:

- В implementation task paths Agent Host умеет `git clone`, `fetch`, `checkout`, `commit`, `push`. Это нормально для server worker с lease discipline, но недопустимо для Mac thin client.
- В старых/legacy местах встречается `mimo run --dangerously-skip-permissions`.
- Image generation требует `KOLIBRI_IMAGE_GENERATOR_CMD` или `OPENAI_API_KEY`; значения не должны попадать в результаты.
- `run_review_pr` может отправлять GitHub review через `gh`, если доступен.

## Telegram Gateway

Ключевой файл: `ops/telegram_gateway.py`.

Назначение: owner-facing long-polling gateway к Control Plane.

Важные функции:

- распознает обычный чат, factory task intent и image intent;
- строит task envelopes для Control Plane;
- ведет memory через `ops/orchestrator_memory.py`;
- показывает владельцу человеческие статусы task lifecycle;
- чистит owner-facing ответы от `task_id`, node/agent/worktree/log/artifact/path/secret markers;
- умеет отправлять изображения из `image_b64`, URL или local artifact path.

Риск/сила:

- Хорошо, что redaction явно покрыт тестами.
- Нужно держать Telegram как owner UX слой, а не как место фактического выполнения.
- Значения `TELEGRAM_BOT_TOKEN` и owner ids должны жить только в env/secret files.

## Mesh Bridge

Ключевой файл: `ops/mesh_control_bridge.py`.

Назначение: bridge между legacy mesh chat/coord API и новым Control Plane.

Поток:

- читает nodes из mesh coordinator;
- регистрирует shadow nodes в Control Plane;
- читает messages из mesh chat;
- преобразует task-like messages в Control Plane task envelopes;
- отвечает в mesh chat статусом accepted/failed.

Риск:

- Default executor `home-live`, default branch `codex/factory-ha-spool-20260627`, default project path `/home/ladik/kolibri-ai-platform` захардкожены/env-driven; это надо сверить с текущими ветками и реальным server inventory.

## Estimates / Billing / Documents

Ключевые файлы:

- `backend/estimate_engine.py`
- `backend/document_engine.py`
- `backend/pdf_engine.py`
- `backend/tests/test_estimate_document_pdf_engines.py`

Что есть:

- deterministic `Decimal` calculator;
- `Estimate`, `EstimateSection`, `EstimateItem`, `EstimateTotals`;
- overhead/tax calculation;
- calculation audit with fingerprint;
- prompt-to-estimate seed generator;
- payload normalization;
- business document pack: КП, договор подряда, акт, счет;
- PDF generation with Cyrillic font candidates;
- tests for deterministic totals, document pack and PDF generation.

Что не видно локально:

- отдельного billing service;
- database schema/migrations for billing;
- payment/invoice lifecycle beyond generated business document model;
- API routes для estimate/document/PDF generation in `backend/main.py`.

Принцип для будущих задач: LLM может объяснять и черновить, но деньги, НДС/налоги, коэффициенты, округления и totals должны идти только через deterministic calculator.

## Frontend / PWA

Ключевые файлы:

- `frontend/src/App.jsx`
- `frontend/src/components/KolibriBird.jsx`
- `frontend/src/components/MessageBubble.tsx`
- `frontend/src/components/KolibriAvatar.tsx`
- `frontend/src/components/ThinkingIndicator.tsx`
- `frontend/package.json`
- `frontend/vite.config.js`
- `frontend/tests/mobile_layout_guard.mjs`

Фреймворк:

- React 19;
- Vite;
- Framer Motion;
- React Markdown;
- CSS-based design.

В UI фактически есть:

- чат;
- WebSocket fallback to HTTP;
- providers select;
- documents tab;
- search tab;
- cluster/network status tab;
- theme switch;
- Kolibri bird/avatar visual identity;
- frontend API base for local dev points to `http://<hostname>:8000`.

PWA:

- В локальных файлах не видно `manifest.webmanifest`, service worker или явного PWA gate. README говорит frontend, но PWA maturity локально не подтверждена.

Риски:

- `MessageBubble.tsx` и `ThinkingIndicator.tsx` выглядят как фрагменты более богатой UI-архитектуры, но импортируют зависимости/aliases, которые не видны в текущем локальном дереве или `package.json` (`@/...`, `lucide-react`, `react-textarea-autosize`, `class-variance-authority`). Если эти компоненты попадут в build graph, frontend build сломается.
- В `MessageBubble.tsx` есть `dangerouslySetInnerHTML` через markdown rendering; нужен sanitizer contract.

## FormulaLM / Training

Локально имени `FormulaLM` как отдельного модуля не видно. Вместо этого есть `scripts/training/`:

- `generate_data.py`;
- `prepare_dataset.py`;
- `finetune.py`;
- `merge_adapter.py`;
- `run_pipeline.sh`;
- `README.md`.

Фактический pipeline:

1. synthetic QA JSONL generation;
2. chat-format conversion;
3. Qwen2.5-1.5B LoRA fine-tuning with PEFT/TRL;
4. adapter merge into standalone model.

Риски:

- `run_pipeline.sh install` создает venv и ставит heavy ML deps; это запрещено на Mac thin client и должно выполняться только на server/training node.
- README training notes already mention blocked outbound 443 on one server; remote intelligence pack должен проверить актуальность.
- Нужны eval scripts/model registry/adapters policy, если это должно стать FormulaLM.

## DevOps / Bootstrap

Ключевые файлы:

- `scripts/deploy.sh`
- `infra/network/nginx.conf`
- `infra/network/config.json`
- `ops/systemd/*.service`
- `ops/install-telegram-secret.sh`

Что есть:

- scp/ssh deploy script for `main`, `uiap`, `qjns`, `9fts`, `home`;
- nginx proxy config for frontend, `/api`, `/ws`, `/cluster`;
- systemd units for Control Plane, Agent Host, Telegram Gateway, Mesh Bridge;
- Telegram secret installer writes env file on target server;
- network inventory for 5 nodes.

Критический риск:

- `infra/network/config.json` содержит секретоподобное поле пароля в открытом виде. Значение не публикуется здесь. Если это реальный пароль, его нужно считать скомпрометированным, удалить из git history/working tree policy, заменить на secret reference и ротировать.

Thin Client Compliance:

- README quick start предлагает запуск backend/frontend локально; это конфликтует с текущим принципом Mac-thin-client.
- `scripts/deploy.sh` запускает scp/ssh с локальной машины; для новой модели это должно быть server-side/Control Plane task, а не ручной Mac deploy.
- Training install/fine-tune на Mac запрещены.
- Agent Host уже имеет server-side execution model; это правильное направление.

## CI / GitHub

Файл: `.github/workflows/ci.yml`.

CI делает:

- checkout with full history;
- Python 3.12 setup;
- `compileall` по `backend`, `infra`, `scripts`;
- installs backend requirements + pytest and runs all pytest files;
- Node 22 setup and frontend build;
- optional lint/typecheck/test if configs/scripts exist;
- JSON/YAML validation;
- secret scan by regex;
- production secret path guard for changed secret-like paths.

Возможная проблема:

- CI secret scan may not catch short plaintext passwords in JSON if they do not match length/pattern threshold. Нужна policy check for keys like `password`, `sudo_password`, `token`, `secret` regardless of value length.

## Документация

Локально видны:

- `README.md`;
- `scripts/training/README.md`;
- generated intelligence docs in `docs/agent/intelligence/...`.

Пробелы:

- нет полноценного architecture doc для Control Plane / Agent Host;
- нет task envelope schema doc;
- нет deployment runbook для server-only workflow;
- нет secrets policy;
- нет rollback/backup runbook;
- нет docs index;
- нет явного owner-facing Telegram UX spec;
- нет FormulaLM spec, если этот термин стратегически важен.

## Тесты

Локально обнаружены:

- `tests/test_factory_runtime.py`
- `tests/test_factory_runtime_contracts.py`
- `tests/test_factory_runtime_queue_contracts.py`
- `tests/test_factory_status.py`
- `tests/test_mesh_control_bridge.py`
- `tests/test_telegram_gateway.py`
- `tests/test_agent_host_image_generation.py`
- `tests/test_agent_host_telegram_chat.py`
- `backend/tests/test_estimate_document_pdf_engines.py`
- `backend/tests/test_factory_status_fast_health.py`
- `frontend/tests/mobile_layout_guard.mjs`

Тесты не запускались на Mac, чтобы не превращать тонкий клиент в development machine и не ставить зависимости.

## Основные риски локальной копии

| Риск | Evidence | Severity | Next action |
| --- | --- | --- | --- |
| Секретоподобное значение в tracked config | `infra/network/config.json` содержит password-like field | high | Ротировать, заменить на secret reference, усилить CI secret policy. |
| Mac thin-client drift | README/scripts предлагают local start/deploy/training | high | Переписать docs под Control Plane/server execution. |
| Direct provider coupling | `backend/providers.py` вызывает `mimo` CLI напрямую | medium | Вынести LLM Gateway/provider abstraction. |
| Dangerous execution flag | `mimo run --dangerously-skip-permissions` встречается в provider/organism legacy paths | high | Ограничить capabilities, sandbox, server-only policy. |
| Hardcoded mesh endpoints | `10.99.0.x` в backend/pipeline/proxy/systemd | medium | Вынести в config/service registry. |
| Factory Control auth unclear | endpoints local code without auth layer | high | Добавить ingress/auth boundary или явно задокументировать private network constraint. |
| Frontend stale components | TSX components import missing aliases/deps | medium | Проверить build graph на сервере, удалить/дособрать компонентную систему. |
| Estimate engine not exposed by API | domain code/tests есть, routes не видно | medium | Добавить server task to map API gap; implementation separately. |
| FormulaLM unclear | есть Qwen LoRA scripts, нет FormulaLM contract | medium | Описать FormulaLM spec/model registry/evals. |
| Branch truth unknown locally | detached HEAD, no all-branches analysis | high | Выполнить server-side intelligence pack. |
| Server truth unknown locally | live состояние серверов не проверялось на Mac | high | Собрать `SERVER_INVENTORY.md` и `servers/<node>.md` через Control Plane. |

## Рекомендованные следующие действия

1. На сервере через Control Plane выполнить полный all-branches + all-servers intelligence pack из `HANDOFF_TO_CONTROL_PLANE.md`.
2. Собрать `SERVER_INVENTORY.md` и `servers/<node>.md` для `home`, `main`, `uiap`, `qjns`, `9fts`, `new`, `primary-candidate`, `home-live`, `mesh-*`.
3. Срочно проверить `infra/network/config.json`: если password-like field настоящий, ротировать секрет и заменить tracked config на template без значений.
4. Обновить `README.md`: убрать Mac-local quick start как основной путь, добавить server-only/Control Plane workflow.
5. Создать `docs/architecture/factory-runtime.md`: Control Plane, Agent Host, Telegram Gateway, Mesh Bridge, task lifecycle, lease/retry/review.
6. Создать `docs/security/secrets-policy.md` и усилить CI secret scan на любые `password|secret|token|key` поля, даже короткие.
7. На server runner проверить frontend build и отдельно решить судьбу TSX components with missing aliases.
8. Зафиксировать LLM Gateway contract: MiMo/OpenAI/etc через единый интерфейс, без прямого вызова provider CLI из API routes.
9. Описать FormulaLM как отдельный контур или переименовать training docs, чтобы не было двух терминов для одного процесса.
10. Добавить API surface для estimates/documents/PDF только после отдельной задачи, не в рамках intelligence pack.

## Что будущему агенту читать первым

- `docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/HANDOFF_TO_CONTROL_PLANE.md`
- `docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/LOCAL_WORKTREE_INTELLIGENCE.md`
- `docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/SERVER_INVENTORY_LOCAL.md`
- `README.md`
- `ops/factory_control.py`
- `ops/agent_host.py`
- `ops/telegram_gateway.py`
- `ops/mesh_control_bridge.py`
- `backend/main.py`
- `backend/pipeline.py`
- `backend/estimate_engine.py`
- `frontend/src/App.jsx`
- `.github/workflows/ci.yml`
- `scripts/training/README.md`
