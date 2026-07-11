# Mac project census: Kolibri AI OS

Дата среза: 2026-07-10, Europe/Moscow
Режим: read-only discovery; единственное изменение — этот отчёт.
Назначение: входные данные для master plan Kolibri AI OS, а не заявление «компьютер полностью изучен».

## Краткий вывод

На Mac уже существует не одна идея, а несколько поколений одной продуктовой системы:

1. действующий FastAPI/React/Fabric/Superfactory runtime;
2. отдельный почти готовый компонентный shell в стиле настоящей desktop OS;
3. Rust-first Control Plane и actor/swarm foundation;
4. чистый продуктовый срез «чат → смета/документы → файлы/проекты → фабрика»;
5. старшие поколения Vista/Fone/Kolibri OS;
6. богатые вертикали: строительство/сметы, hotel, content factory, VPN/mesh, automotive/status;
7. большой слой экспериментов, дубликатов, восстановленных копий, архивов и task-specific worktree.

Наиболее устойчиво повторяющееся намерение владельца подтверждается несколькими независимыми источниками: **один минимальный интерфейс, похожий на macOS; один canvas с настоящими окнами; чат/птичка как вход в намерение; файлы, проекты, история и артефакты как долговечные объекты; скрытая агентная фабрика; фраза пользователя превращается не в ответ-текст, а в проверяемый пакет документов/сайтов/приложений**. Вертикали должны быть capability/component packs внутри одной OS, а не десятки разрозненных приложений.

Главный актив уже есть: `/Users/kolibri/Documents/Codex/worktrees/kolibri-os-implementation-20260710/frontend/` реализует маленький `App.jsx`, отдельные `shell/`, `windows/`, `workbench/`, `control/`, `runtime/` и тест, запрещающий снова превращать `App.jsx` в портянку. Но эта работа находится в сильно грязном worktree и ещё не является безопасно интегрированным каноном.

## Метод и границы

### Что обследовано

- Git-маркеры, worktree, branch/HEAD/date, безопасно нормализованный origin basename и manifest-маркеры в:
  - `/Users/kolibri/Documents`;
  - `/Users/kolibri/Desktop`;
  - `/Users/kolibri/Downloads`;
  - `/Users/kolibri/Projects`;
  - `/Users/kolibri/.codex/worktrees`;
  - очевидных project roots непосредственно в `/Users/kolibri`.
- README, architecture, roadmap, PRD, source-of-truth, release и status-документы у наиболее сильных семейств.
- Имена и размеры ключевых архивов без распаковки/хэширования больших бинарников.
- Структура активных frontend/backend/runtime, component boundaries и evidence directories.
- Исторические локальные intelligence/audit-отчёты как вторичный источник; их выводы не считались текущей истиной без сверки.

### Что сознательно исключено

- `Library`, Mail, Messages, browser profiles/cookies, Keychain-подобные хранилища, `.ssh`, photo/music libraries и личные файлы вне project contour;
- `.env*`, private keys, credential/token/cookie-файлы и `ops/telegram.env`;
- содержимое зашифрованного operator kit;
- содержимое личных фотоархивов;
- большие binaries/models/build outputs; они не хэшировались и не дизассемблировались;
- live servers, production endpoints, DNS, firewall и deploy/bootstrap;
- network fetch, `git fetch`, GitHub API и актуальность remote refs.

### Измеренное покрытие

| Область | Наблюдение |
| --- | --- |
| Git-маркеры в пяти основных roots | Documents 16; Desktop 18; Downloads 5; Projects 60; `.codex/worktrees` 28 |
| Уникальные Git-маркеры с shallow home scan | 137 |
| Структурно распознанные Git worktree/repo | 133 |
| Повреждённые `.git` markers | 4 |
| Уникальные `git-common-dir` | 89 |
| Уникальные наблюдаемые HEAD | 92, включая многочисленные дубликаты и divergent clones |
| Нормализованные origin basenames | 25; много локальных репозиториев без remote |
| Marker-bearing immediate roots | Desktop 14; Downloads 46; home-level project roots 19 |
| `Projects` depth-2 marker nodes | 109; это верхняя оценка, в неё входят subpackages/apps, а не только продукты |
| Главный `kolibri-ai-platform` family | 40 worktree, 75 local branches, 303 сохранённых remote refs, 2 prunable entries |
| Главный checkout | 627 tracked files; 23 tracked changes; 158 untracked files; рабочая папка около 4.0 GiB при tracked footprint около 4.2 MiB |
| Runtime/evidence в главном checkout | 19 `.factory/runs` (около 19 MiB), 438 файлов `docs/agent` (около 2.7 MiB), 40 release files, 6 artifact files |

`mtime` каталогов использовался только как ориентир последнего локального изменения. Для Git-проектов предпочтение отдавалось commit date. Ни то, ни другое не доказывает дату рождения идеи.

## Фактическое намерение продукта

Ниже — не психологическая догадка, а пересечение нескольких проектных контрактов.

### 1. Настоящая single-window OS

- Первый экран тихий и минимальный: живая птичка/персонаж и фон-состояние.
- Пользователь не ходит по странице с длинным лендингом, формой, цитатой и футером.
- После намерения появляются Stage Canvas, окна, Dock/Tool Dock, floating composer и overlay history.
- На desktop окна перемещаются, меняют размер, сворачиваются, разворачиваются; на mobile становятся sheets/single focused surface.
- Нужны отдельные Files, Projects, History и task-result windows, чтобы результаты не терялись.

Evidence:

- `docs/en/KOLIBRI_OS_ARCHITECTURE.md`;
- `/Users/kolibri/Downloads/vista_os_unicorn_work/README.ru.md`;
- `/Users/kolibri/Downloads/vista_os_unicorn_work/docs/architecture/FONE_OS_PRODUCTION_ARCHITECTURE.ru.md`;
- `/Users/kolibri/Documents/Codex/worktrees/kolibri-os-implementation-20260710/frontend/src/workbench/Workbench.jsx`.

### 2. Одна фраза → набор полезных артефактов

Пользователь формулирует цель обычной фразой. OS строит plan/DAG, распределяет работу, а затем открывает типизированные результаты: смету, договор, КП, акт, PDF/DOCX/XLSX, сайт, приложение, код/diff, логи или план. Текст чата — лишь управление; durable object и artifact являются результатом.

Evidence:

- `docs/en/KOLIBRI_OS_ARCHITECTURE.md`;
- `/Users/kolibri/Documents/Codex/worktrees/kolibri-os-implementation-20260710/frontend/src/runtime/rendererRegistry.js`;
- `/Users/kolibri/Documents/Codex/worktrees/kolibri-platform-home-gateway-20260710/README.md`;
- `/Users/kolibri/Downloads/vista_os_unicorn_work/docs/product/ESTIMATES_MARKET_MVP.ru.md`.

### 3. Вертикали — capabilities/components, а не отдельные продукты

Повторяется одна формула: estimates, documents, CRM, factory operator, developer/API, accounting, knowledge, hotel, VPN и другие режимы должны быть projection/profile packs единой OS. Отдельные накопленные приложения — сырьё для извлечения domain engines, contracts и UI components, но не будущая навигационная модель.

Evidence:

- `docs/en/KOLIBRI_OS_ARCHITECTURE.md`, раздел Morphable Frontend;
- `/Users/kolibri/Downloads/vista_os_unicorn_work/docs/product/PRODUCT_LINE_VERTICALS.ru.md`;
- `/Users/kolibri/construction-estimator/docs/agents/CONSTRUCTION_OS_CHARTER.md`.

### 4. Скрытая фабрика с доказуемым выполнением

Публичная модель называется `kolibri`; Mimo/Codex/другие провайдеры остаются внутренней provenance. `home` — единственная authority Control Plane. Worker действует через API task/lease/attempt, не через UI или свободный SSH. Завершение требует непустого результата, artifact/evidence и verifier gate; опасные действия требуют owner approval.

Evidence:

- `docs/CONTROL_PLANE_AGENT_MODEL.md`;
- `/Users/kolibri/Documents/Codex/worktrees/kolibri-os-implementation-20260710/docs/KOLIBRI_OS_V1_CONTRACT_FREEZE.md`;
- `/Users/kolibri/Documents/Codex/worktrees/kolibri-os-implementation-20260710/docs/CONTROL_PLANE_HOME_CANONICAL.md`;
- `ops/factory_control.py`, `ops/agent_host.py`.

### 5. «Собственный ИИ» — асинхронная безопасная эволюция

FormulaLM в зрелом контракте — не синхронное самоизменение весов во время ответа. Verified traces проходят consent/license/PII/secret gates, попадают в отдельную очередь, затем training/evaluation/canary/owner approval. Старые numeric-formula/AGI эксперименты полезны как R&D lineage, но не доказывают готовую собственную модель.

Evidence:

- `/Users/kolibri/Documents/Codex/worktrees/kolibri-os-implementation-20260710/docs/FORMULALM_LEARNING_BOUNDARY.md`;
- `/Users/kolibri/Projects/kolibri-ecosystem/docs/kolibri_ai_prd.md`;
- `/Users/kolibri/Projects/kolibri-project/docs/reports/KOLIBRI_REAL_STATE.md`.

## Канонические семейства проектов

| Семейство | Период по evidence | Стек | Лучший текущий источник | Что реально ценно | Статус/ограничение |
| --- | --- | --- | --- | --- | --- |
| Active Kolibri AI Platform | Git history 2026-06-17…2026-07-10 | FastAPI, React/Vite, Redis, Python ops, Telegram, Tauri scaffold | `/Users/kolibri/Documents/Codex/kolibri-ai-platform` | работающие Fabric/Superfactory contracts, task/node state, Agent Host, provider/backend, evidence history | фактическая ветка/HEAD расходится с handoff; дерево сильно dirty |
| Component Kolibri OS shell | 2026-07-10 | React/Vite, reducer-based window manager, typed gateway | `/Users/kolibri/Documents/Codex/worktrees/kolibri-os-implementation-20260710` | shell/windows/workbench/control/runtime, renderer registry, V1 contracts, FormulaLM boundary | 60 tracked changes + 87 untracked; широкая сборка/регрессия этим census не выполнялась |
| Rust Control Station / swarm core | 2026-07-05…2026-07-10 | Rust/Tokio/Axum, React/Tauri, planned NATS/Postgres | `/Users/kolibri/Documents/Codex/worktrees/kolibri-rust-swarm-core-20260710` и `/Users/kolibri/.codex/worktrees/b56d/kolibri-ai-platform` | durable events, actor/task types, Rust-first ADR, Tauri/NATS/sandbox decisions | интеграционные control-plane/agent/scheduler компоненты описаны как scaffold/build-out |
| Kolibri Platform 1.0 product slice | Git root 2026-06-25; clean worktree updated 2026-07-10 | React/TS/PWA, FastAPI, SQLite WAL, Tauri 2 | `/Users/kolibri/Documents/Codex/worktrees/kolibri-platform-home-gateway-20260710` | чистый vertical slice: chat, library, projects, estimates, documents, exports, factory UI | локальный/single-user pilot; нужны auth, tenant isolation, Postgres, object storage и expert validation |
| Vista/Fone OS lineage | local packages 2026-07-08…2026-07-10 | Rust crates, FastAPI, React, Tauri/PWA | `/Users/kolibri/Downloads/vista_os_unicorn_work` | наиболее ясная product thesis single-window OS и estimates-first market wedge | нет Git provenance; версии 3/5/7/8/unicorn именованы непоследовательно; controlled demo, не production |
| Legacy Kolibri OS / brain / archiver | 2025-09…2026-05 | C23/CMake, Python/FastAPI, React/WASM, Swift, custom archive tools | `/Users/kolibri/Projects/kolibri-project` и `/Users/kolibri/Projects/kolibri/kolibri-project-main` | C core, knowledge graph, task experiments, portable archive/seed tooling, many benchmarks/docs | множество divergent clones; старые optimistic claims конфликтуют с honest reports; не использовать как production truth |
| Construction / estimates | 2025-11…2026-07 | React/TS, Node/FastAPI, SQLite/Postgres plans, Rust/WASM/C23, PWA | `construction-estimator`, `smeta-ai-app-v21-full-docs`, clean Home gateway estimate module | самый богатый domain corpus: takeoff, estimate, prices, approvals, documents, КС-2/КС-3, field workflow | раздроблен на десятки поколений; authoritative schema/catalog/golden dataset не выбран |
| Hotel / revenue | 2026-01…2026-02 | NestJS, Prisma/Postgres, Redis/BullMQ, React, PWA | `/Users/kolibri/Projects/hotel` | tenant/RLS/RBAC, outbox, idempotency, plugin-kit, guest/staff/admin surfaces, legal UI | это отдельный SaaS; следует извлекать patterns/domain pack, а не встраивать целое приложение |
| Content factory | 2026-01…2026-04 | NestJS, Prisma, BullMQ, React, Postgres/Redis/MinIO | `/Users/kolibri/Downloads/content-factory-24_7` и `/Users/kolibri/Desktop/фабрик` | queue/DLQ, BudgetOps/PromptOps, approval, connectors, n8n-style workflow ideas | один readiness report прямо говорит: tests skipped и full worker business logic ещё предстоит |
| Mesh/VPN/native clients | Git 2025-12…2026-06 | Go, Rust, Swift/SwiftUI, Xcode, Tauri | `/Users/kolibri/kolibri-mesh`, `/Users/kolibri/kolibriai-vpn`, untracked `apps/` в active repo | coordinator/agent patterns, native clients, local proxy, tunnel/UI scaffolds | crypto/network claims не проверялись; trusted 21-server bootstrap нельзя переписывать; operator kit encrypted |
| Sites/brand | 2026-07-10 | React/Vite, Next/vinext, worker | `sites/kolibri-launch` и OS `sites-preview` | чистый launch site и изолированный minimal-shell visual prototype | отдельные Git roots; deployment намеренно отсутствует |
| Other vertical prototypes | 2025-07…2026-01 | Go, C/WASM, React/PWA, Python | motor-doctor, statusprod, budget/inventory/bot/tool projects | UI kits, offline/P2P, booking/work-order patterns, small utilities | низкая связь с current core; переносить только конкретные проверенные modules/patterns |

## Главная Git-реальность

### Handoff drift

`AGENTS.md` и `docs/SOURCE_OF_TRUTH.md` называют активной веткой `p0/codex-sidebar-thread-bootstrap-20260704` и старый initial HEAD. Фактически на момент census canonical path находился на:

- branch `codex/vista-full-os-integration-2026-07-08`;
- HEAD `19ef90142754`;
- latest commit `2026-07-10T06:44:13+03:00`;
- 23 tracked modifications и 158 untracked files.

Это не косметика: master plan должен сначала зафиксировать, какой branch/worktree является integration authority. Иначе «активный продукт», component OS и Rust core будут продолжать расходиться.

### Один большой common-git family

Главный repository имеет 40 зарегистрированных worktree. В него входят:

- current integration checkout;
- component OS implementation;
- Rust swarm core;
- provider registry;
- Mimo runner contract;
- canonical fleet status и main audit;
- Agent Host/control-plane hardening;
- Telegram/Superfactory/PR relay/canary branches;
- исторические `.factory/runs/*` worktree;
- два prunable `/private/tmp` entries.

Полезный смысл: большая часть июньско-июльской agent work уже не «разные проекты», а ветви одного репозитория. Их нужно сводить ledger-ом по capability/contract, а не копированием папок.

### Важные свежие ветви

| Branch/worktree | HEAD/date | Наблюдение |
| --- | --- | --- |
| current `codex/vista-full-os-integration-2026-07-08` | `19ef90142754`, 2026-07-10 | активная смешанная интеграция, dirty |
| `codex/kolibri-os-implementation-20260710` | `91a9b000379c`, 2026-07-10 | component shell + V1 contracts, очень dirty |
| `codex/kolibri-rust-swarm-core-20260710` | `69f3b844f206`, 2026-07-10 | свежий Rust event/core slice; 1 tracked change, generated `target/` |
| `codex/mimo-auto25-runner-contract-20260710` | `78c0e4549e1d`, 2026-07-10 | execution-provider contract |
| Home gateway `codex/kolibri-platform-home-gateway-20260710` | `68a3f34c1e0b`, 2026-07-10 | clean product slice |
| Sites brand `codex/kolibri-sites-brand-20260710` | `2f7f305962c9`, 2026-07-10 | clean brand/site slice |
| Rust foundation `p0/free-low-cost-model-provider-registry-20260704` | `bbeeec49a0ed`, 2026-07-05 | useful foundation, но 16 tracked + 78 untracked |

Remote refs не обновлялись. Число `303` означает локально сохранённые refs, а не 303 актуальные GitHub-ветки.

## Дубликаты, поколения и восстановленные копии

### Явные duplicate groups

- **Hotel simple repo:** Desktop `hotel`, десять `hotel_multi/copy_*` и две вложенные копии в legacy vault имеют один HEAD `85712d5daa02`. Это 13 наблюдаемых одинаковых Git snapshots; хранить как 13 продуктов бессмысленно.
- **SmartInventory:** `SmartInventory` и `SmartInventory-2` имеют одинаковый HEAD; рядом есть ещё marker copies `-3/-4` без такого же Git evidence.
- **Said bot:** четыре `Said_bot*` имеют один HEAD; `said` и `said-2` образуют ещё одну пару.
- **Restored legacy:** `RESTORED_BY_KOLIBRI_AGI` и `TEST_PROJECT_RESTORED` имеют идентичные `README.md`, `CMakeLists.txt`, `requirements.txt`, frontend package и compose; file counts около 8.6k. Их `.git` повреждены, а не являются рабочими repositories.
- **Legacy production variants:** `kolibri_final_project`, `kolibri_production_with_invention*`, `kolibri_production_with_improvements` содержат повторяющиеся HEAD-группы; `leontov-kolibriai-*` — последовательные divergent clones одного origin family.

### Iteration dumps, а не канонические ветви

- Downloads содержит более двадцати Qwen bridge/launcher directories с именами `broken`, `fixed`, `v2`, `v3`, `v4`, а также повторные копии. Это полезная история adapter experiments, но не provider architecture.
- Vista/Fone лежит как `vista_os_3_real_product`, `5_fleet_ready`, две `7_ideal_workbench`, `8_real_workbench`, `unicorn_work` и несколько reset ZIP. Номер каталога не равен архитектурной зрелости: некоторые README внутри называют другую версию.
- Smeta имеет standalone generations, v8, v21, `smetaprom`, `smetaqwen`, design kit, enterprise addons, miniapp, Construction OS и отдельные agent scripts.
- Hotel имеет как минимум simple Docker repo, advanced `Projects/hotel`, `Projects/kolibri-hotel`, UI system, prototype и `ishotel`.
- Content factory существует в home root, Downloads, Desktop `завод`, Desktop `фабрик` и внутри legacy `kolibri-project`.

### Архивы

Наблюдаемые важные packages без чтения содержимого:

- `/Users/kolibri/Documents/Codex/kolibri-ai-platform.zip` — около 987 MiB, 2026-06-30;
- `/Users/kolibri/Documents/Codex/worktrees.zip` — около 46 MiB, 2026-06-30;
- серии Vista/Fone ZIP от 2026-07-08…10;
- `kolibri-platform-v1.0.0.zip`, Kimi estimate/finance packages, Smeta v8/v21 packages;
- Qwen bridge ZIP series;
- content-factory, hotel, motor-doctor и old Kolibri packages;
- encrypted `/Users/kolibri/KolibriOperatorKit/...tar.gz.enc` — не открывался.

Архивы следует считать cold evidence/salvage source, а не source of truth. Большие binaries, `.klb/.kar`, restored blobs и apps не хэшировались.

## Компонентная архитектура: конкретный результат

Запрос владельца «повторяющееся — компонентами, основная страница только собирает компоненты, окна отдельно» уже материализован в OS worktree.

| Показатель | Current integration frontend | Component OS worktree |
| --- | ---: | ---: |
| `App.jsx` | 488 строк | 15 строк |
| `App.css` | 773 строки | 1502 строки |
| Основной composition | logic/UI смешаны в `App.jsx` | `PublicShell` / `ControlShell` |
| Window layer | частично внутри main app | `windows/*` + `WindowContent` |
| Window manager | локальная surface logic | `workbench/Workbench.jsx` + reducer |
| Runtime/API | несколько preview runtime files | `runtime/kolibriApi.js`, renderer registry |
| Architecture guard | отсутствует | `frontend/tests/component_architecture.mjs` |

Проверено read-only запуском:

```text
node frontend/tests/component_architecture.mjs
Kolibri component architecture contracts passed
```

Тест требует:

- `App.jsx` не больше 20 строк;
- `PublicShell` остаётся composition module;
- ErrorBoundary, Brand, SystemBar, ToolDock, Composer, HistoryDrawer, окна и shared StatusBadge живут отдельно;
- estimate/projects/files/task result рендерятся через `WindowContent`;
- orchestration не возвращается в main component.

Это сильнейшая точка повторного использования. Одновременно остаётся долг: общий `App.css` вырос до 1502 строк, `runtime/kolibriApi.js` — до 552 строк, `usePublicShell.js` — до 257 строк. Следующая компонентная граница должна включать style tokens/surface styles, typed API clients и domain hooks, а не только JSX-файлы.

## Сильные reusable assets

| Asset | Evidence | Рекомендованное использование |
| --- | --- | --- |
| Stage Canvas + real window manager | OS worktree `frontend/src/workbench/*` | базовый desktop/mobile window runtime |
| Shell component contract | OS worktree `frontend/src/shell/*`, component test | обязательный guard от монолитного `App` |
| Artifact renderer registry | OS worktree `frontend/src/runtime/rendererRegistry.js` | единый registry для PDF/DOCX/XLSX/image/video/code/log/plan/estimate |
| V1 domain/OpenAPI contract | OS worktree `contracts/kolibri-os-v1/*`, contract freeze | стабильная граница Python compatibility ↔ Rust authority |
| Fabric/Superfactory runtime | active `ops/factory_control.py`, `ops/agent_host.py`, tests | migration adapter и работающий execution evidence layer |
| Home product slice | clean Home gateway worktree | reference implementation Files/Projects/Estimates/Documents/Factory |
| Deterministic estimate/document engines | active backend + Home gateway + Smeta v21 | первый market vertical; LLM не считает деньги |
| Smeta v21 domain pack | `docs/domain`, `docs/architecture`, `docs/qa`, roadmap | authoritative candidate для takeoff/catalog/doc/export/offline requirements |
| Construction OS charter | `construction-estimator/docs/agents/CONSTRUCTION_OS_CHARTER.md` | product/module/approval taxonomy для construction pack |
| Hotel enterprise patterns | `Projects/hotel` | tenant isolation, RLS/RBAC, outbox, idempotency, plugin contracts |
| Content factory patterns | Downloads/Desktop content-factory families | queues, DLQ, approval, BudgetOps/PromptOps; после отделения от n8n UI |
| Task graph + inventions intake | `Projects/kolibri-ecosystem/docs/TASK_GRAPH.md`, `inventions/README.md` | reusable schema для decomposition и controlled idea intake |
| Rust foundation ADR | Rust worktree `docs/adr/*`, `docs/architecture.md` | Rust-first core, Tauri, JetStream, sandbox, low-complexity orchestration |
| Sites preview/launch | `sites-preview`, `sites/kolibri-launch` | shareable previews и public launch surface отдельно от OS runtime |
| Go/native experiments | active untracked `apps/kolibri-go-mesh-proxy`, `apps/kolibri-ios-client` | candidate clients после version-control salvage и security review |
| Evidence corpus | `.factory/runs`, `docs/agent/runs`, `release/` | regression fixtures, incident history и acceptance patterns |
| Legacy archiver | `kolibri-archiver-v85-compressc`, honest reports | content packaging/dedup research; не использовать AGI claims как факт |

## Незавершённые продуктовые линии

### P0: канон и сохранность

1. **Integration authority не зафиксирована.** Handoff указывает одну ветку, фактический checkout — другую.
2. **Component OS находится вне безопасного commit slice.** 60 tracked и 87 untracked элементов нельзя считать готовым merge unit.
3. **Current checkout содержит 158 untracked files.** Среди них runtime, apps, fleet/UI и release evidence; это реальный риск потери.
4. **89 Git-common families и множество archives не имеют asset ledger.** Один и тот же продукт многократно существует как repo, folder, ZIP и restored copy.

### P0: runtime truth

1. Contract freeze прямо говорит, что production rollout и 21-node capability verification не доказаны.
2. Bootstrap connectivity, fresh Agent Host membership и real task execution должны измеряться раздельно.
3. `home` как единственная Control Plane authority описан и частично реализуется, но census не проверял live routing.
4. Existing `/v1/fabric/*` и target `/v1/responses|projects|artifacts|runtime` ещё требуют compatibility migration и release waves.
5. Renderer registry перечисляет двенадцать типов, но наличие записи не доказывает production renderer каждого типа.

### P0: пользовательский продукт

1. Component shell существует, но не доказан как интегрированный build текущей ветки.
2. Files/Projects/History должны стать durable backend entities, а не только window payload/local state.
3. Home product slice честно остаётся single-user/local pilot: нет production auth/tenant isolation/object storage/security review.
4. Construction vertical не имеет одного утверждённого schema/catalog/golden dataset и юридически проверенного document pack.
5. Простая форма/страница не должна вернуться как основной UX; OS должна открывать typed workspace window после intent.

### P1: собственный AI

1. FormulaLM имеет безопасную intake/promotion boundary, но trainer, independent eval council, signed canary и production weights не развёрнуты.
2. Legacy numeric formula/knowledge/archiver experiments — R&D evidence, не готовая LLM и не доказанная AGI.
3. Нужны benchmark datasets по capabilities, cost/quality telemetry и shadow/canary promotion; self-reported README недостаточно.

### P1: вертикали

- `construction-estimator` status report оценивал production completeness примерно в 15%; auth, DB, RAG, prices, workflow и hardening оставались впереди.
- Smeta v21 имеет хорошую offline foundation, но требует manual QA, document polish, catalog expansion, storage hardening и desktop packaging.
- Content Factory readiness проверял build/smoke, но пропускал tests и оставлял full worker logic как next step.
- Hotel наиболее зрел по enterprise patterns, но всё ещё отдельный multi-app SaaS, не capability pack Kolibri OS.
- VPN full TUN/e2e и network security claims требуют отдельного стенда и review; в этом census не проверялись.

### P2: R&D/архивы

Restored/AGI directories содержат повреждённые `.git`, тысячи recovered files и self-claims. Honest legacy report называет работающую часть dictionary-based lossless archiver/PoC и прямо говорит, что это не magic hash restoration, не всегда сжимает и не production. Эту честную оценку следует считать выше рекламных `LEVEL 4`/«бесконечное сжатие» заявлений.

## Evidence и исторические артефакты

### Active runtime evidence

- `.factory/runs/` — 19 top-level runs, включая bootstrap, network convergence, Telegram Mini App, canary, stress и waves;
- `docs/agent/runs/` — десятки task/run dossiers;
- `docs/agent/intelligence/` и `docs/agent/global-intelligence/` — audits 2026-06-30…07-01;
- `release/` — 40 файлов plan/status/evidence;
- `artifacts/P0_TELEGRAM_SUPERFACTORY_BOT_AND_MINIAPP_2026_07_01`;
- `artifacts/PROJECT_AUDIT_2026_07_06/PROJECT_SUMMARY.md`;
- `/Users/kolibri/Documents/Codex/snapshots/kolibri-ai-platform-20260710T0518Z`.

Исторические отчёты полезны как event log, но их branch counts/status устарели. Например, audit от 2026-07-06 видел другое HEAD и меньше свежих worktree, чем текущий census.

### Evidence paths по семействам

Active OS/factory:

- `/Users/kolibri/Documents/Codex/kolibri-ai-platform/.kolibri/AGENT_START_HERE.md`;
- `/Users/kolibri/Documents/Codex/kolibri-ai-platform/docs/SOURCE_OF_TRUTH.md`;
- `/Users/kolibri/Documents/Codex/kolibri-ai-platform/docs/PROJECT_MAP.md`;
- `/Users/kolibri/Documents/Codex/kolibri-ai-platform/docs/en/KOLIBRI_OS_ARCHITECTURE.md`;
- `/Users/kolibri/Documents/Codex/kolibri-ai-platform/docs/CONTROL_PLANE_AGENT_MODEL.md`.

OS implementation/Rust:

- `/Users/kolibri/Documents/Codex/worktrees/kolibri-os-implementation-20260710/docs/KOLIBRI_OS_V1_CONTRACT_FREEZE.md`;
- `/Users/kolibri/Documents/Codex/worktrees/kolibri-os-implementation-20260710/docs/CAPABILITY_TOOL_GATEWAY.md`;
- `/Users/kolibri/Documents/Codex/worktrees/kolibri-os-implementation-20260710/docs/FORMULALM_LEARNING_BOUNDARY.md`;
- `/Users/kolibri/.codex/worktrees/b56d/kolibri-ai-platform/docs/architecture.md`;
- `/Users/kolibri/.codex/worktrees/b56d/kolibri-ai-platform/docs/adr/`.

Product/vertical:

- `/Users/kolibri/Documents/Codex/worktrees/kolibri-platform-home-gateway-20260710/README.md`;
- `/Users/kolibri/Downloads/vista_os_unicorn_work/README.ru.md`;
- `/Users/kolibri/Downloads/smeta-ai-app-v21-full-docs/docs/`;
- `/Users/kolibri/construction-estimator/docs/agents/CONSTRUCTION_OS_CHARTER.md`;
- `/Users/kolibri/Projects/hotel/docs/architecture.md`;
- `/Users/kolibri/Downloads/content-factory-24_7/docs/`;
- `/Users/kolibri/Projects/kolibri-ecosystem/docs/kolibri_ai_prd.md`.

Legacy/honesty:

- `/Users/kolibri/Projects/kolibri-project/docs/reports/KOLIBRI_REAL_STATE.md`;
- `/Users/kolibri/Projects/kolibri-project/docs/reports/ARCHIVER_COMPARISON_HONEST.md`;
- `/Users/kolibri/kolibri-archiver-v85-compressc/README.md`.

## Рекомендация для master plan

До новой большой разработки следует принять не «один старый проект целиком», а каноническую сборку из проверенных слоёв:

1. **Runtime authority:** active `kolibri-ai-platform`, после фиксации правильной integration branch и разборки dirty tree.
2. **OS UX authority:** component OS worktree, разрезанный на reviewable commits и прошедший build/E2E/visual verification.
3. **Core authority:** V1 contracts + Rust swarm/core, без преждевременного удаления Python compatibility.
4. **First market pack:** estimates/documents из clean Home gateway + Smeta v21 domain/QA + Construction OS approval taxonomy.
5. **Enterprise patterns:** selective extraction из Hotel, Content Factory и ecosystem task graph.
6. **Brand/share:** isolated Sites preview и launch repo.
7. **Cold archive:** legacy clones, ZIP, restored/AGI and Qwen iteration dumps; только indexed salvage, без прямого копирования в core.

Предлагаемая component/package boundary для последующего проектирования:

```text
apps/kolibri-shell
apps/control-center
crates/kolibri-core
services/control-plane
services/agent-host
packages/os-shell
packages/window-manager
packages/artifact-renderers
packages/protocol
packages/ui-tokens
packages/project-files-history
verticals/estimates
verticals/documents
verticals/hotel
verticals/content-factory
```

Перед любым удалением/архивацией нужен отдельный owner-approved asset ledger: `family_id`, path, Git common-dir/origin, HEAD, date, canonical status, unique assets, migration target, verification, secret risk и retention. Этот census ничего не удалял и не объявляет безопасными для удаления даже очевидные дубликаты.

## Пробелы и уровень уверенности

Высокая уверенность:

- topology локальных Git/worktree markers на указанных roots;
- текущая branch/HEAD/dirty state основных worktree;
- компонентная структура OS worktree и результат её architecture test;
- содержание выбранных SOT/architecture/roadmap/status docs;
- наличие duplicate families и archive waves.

Средняя уверенность:

- фактическая зрелость non-Git packages в Downloads/Desktop;
- актуальность self-reported build/test/readiness за 2025–2026;
- уникальность assets внутри крупных legacy copies без полного content comparison.

Не проверено:

- live GitHub state, PR/CI, remote-only code и private repositories;
- live servers, fleet freshness, provider execution и production services;
- содержимое encrypted operator kit и binary/archive payloads;
- legal correctness сметных/договорных документов;
- security/cryptographic correctness VPN/mesh;
- качество заявленных моделей/FormulaLM/AGI;
- полная семантика каждого из 133 распознанных repositories/worktree.

Итоговая формулировка покрытия: **проектный контур Mac проиндексирован на уровне Git/manifest topology и семантически обследован по ключевым семействам; компьютер целиком, все файлы, GitHub и серверы этим отчётом не изучены и не должны считаться изученными.**
