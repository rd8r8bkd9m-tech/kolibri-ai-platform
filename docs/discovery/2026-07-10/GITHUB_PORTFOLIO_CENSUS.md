# GitHub portfolio census: Kolibri AI / AI OS / verticals

Дата снимка: 2026-07-10.

Режим: read-only discovery. Репозитории, ветки, PR, issues, Actions, настройки и runtime не изменялись. Секреты и содержимое env-файлов не читались и не выводились.

## 1. Итог

GitHub-портфель подтверждает цель владельца: не отдельный чат-бот, а единая AI OS, которая принимает обычную задачу, планирует её, распределяет между агентами и инструментами, проверяет результат и возвращает работающий продукт или комплект документов в одном интерфейсе.

Но кодовая база сейчас фрагментирована:

- один репозиторий является реальным центром текущей разработки — [rd8r8bkd9m-tech/kolibri-ai-platform](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform);
- несколько репозиториев содержат сильные технологические доноры: FormulaLM, C/Rust core, детерминированные сметы, документы, provider gateway, mesh и фабричные контракты;
- значительная часть портфеля — повторные генерации одного продукта, шаблоны, пустые репозитории или исторические эксперименты;
- README часто заявляют production-ready, AGI или рекордные показатели, но CI, тесты и release evidence эти широкие claims не доказывают;
- branch/PR hygiene является системной проблемой: 447 веток и 147 открытых PR, из них 296 веток и 91 PR находятся только в kolibri-ai-platform.

Рекомендация: не собирать новый репозиторий и не объединять всё wholesale. Сохранить kolibri-ai-platform как единственный product/runtime source of truth, а полезные возможности переносить туда через проверяемый capability-import pipeline: контракт → тесты → минимальный код → provenance → canary → release.

## 2. Coverage и метод

Проверено через авторизованный GitHub API/GraphQL и gh CLI:

- GitHub identity: rd8r8bkd9m-tech, имя профиля — Владислав Кочуров;
- 37 из 37 собственных репозиториев;
- 21 public и 16 private;
- GitHub API не показывает членства в организациях;
- default branch, visibility, activity date, primary language, root tree и README каждого непустого репозитория;
- branch, open PR и open issue counts;
- HEAD status check rollup;
- активные Actions workflows и последние runs, где они существуют;
- выборочный PR triage активного platform-репозитория;
- GitHub code search по FormulaLM, Mimo, Vista OS и GoMesh;
- локальные Git remotes/worktrees на Mac в доступной части home-каталога.

Снимок агрегатов:

| Метрика | Значение |
| --- | ---: |
| Owner repositories | 37 |
| Public / private | 21 / 16 |
| Archived | 0 |
| Empty или без default branch | 4 |
| Веток всего | 447 |
| Open PR всего | 147 |
| Open issues всего | 32 |
| Default HEAD rollup success / failure / absent | 7 / 9 / 21 |
| Git worktrees/checkouts на Mac в охваченном scan | 172 |
| Worktrees, связанные с owner repos | 70 |
| Уникальные owner repos с локальным checkout | 18 из 37 |

### Ограничения coverage

- Это полный census owner-репозиториев текущего GitHub-аккаунта, но не content-diff всех 447 веток и 147 PR.
- Для каждой репозитории подробно анализировался default branch; non-default branches покрыты метаданными, активным PR triage и существующими branch-intelligence artifacts.
- GitHub code search индексирует репозиторный код, но не локальные ZIP/Downloads и не серверные директории вне GitHub.
- CI rollup означает только состояние checks конкретного commit. Отсутствие failure не означает production readiness.
- Активные Actions workflows нашлись только в шести репозиториях. В kolibri-project, t-bank-style-booking и motor-doctor-auto-se последние runs связаны преимущественно с Dependabot/Copilot, а не с полным product test gate.
- README и committed report-файлы считались описанием намерений, а не доказательством работоспособности.
- Локальный поиск исключал Library, Trash, dependency/cache/venv trees и внешние диски. Он охватил обычные рабочие каталоги, Downloads, Desktop, Projects, Documents и Codex worktrees.
- Серверный runtime, сетевой доступ и production deployment этим GitHub census не проверялись.

## 3. Единственный актуальный source of truth

### Product/runtime source of truth

[kolibri-ai-platform](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform) — единственный репозиторий, который одновременно содержит:

- FastAPI backend и React/Vite frontend;
- Home-only Control Plane, Agent Host, leases, task queue и Telegram gateway;
- mesh bridge и fleet contracts;
- provider integration, artifacts, release scripts и regression tests;
- текущие FormulaLM/Swarm/AI OS планы и evidence;
- реальную текущую веточную активность.

Remote default branch на момент снимка:

- branch: main;
- HEAD: 4675748fb1a8;
- default-branch Kolibri CI: success;
- GitHub Pages run: success;
- 296 веток, 91 open PR, 32 open issues.

Локальная canonical implementation ветка находится в:

- /Users/kolibri/Documents/Codex/worktrees/kolibri-os-implementation-20260710
- branch codex/kolibri-os-implementation-20260710
- captured HEAD 91a9b0003

Она содержит большой shared dirty implementation state и ещё не равна remote main. Поэтому source of truth означает место консолидации и release authority, а не claim, что текущая незакоммиченная ветка уже production-ready.

### Важное противоречие

Текущий GitHub API сообщает, что kolibri-ai-platform — PUBLIC. Старый локальный GITHUB_STATE_REPORT.md называл его private. Это необходимо считать security/documentation drift:

1. обновить документацию видимости;
2. провести full history secret/topology exposure audit;
3. не полагаться на прежнее предположение о приватности;
4. не публиковать новые operational artifacts до классификации public/private.

## 4. Роли репозиториев

### A. Canonical production line

| Репозиторий | Роль | Решение |
| --- | --- | --- |
| [kolibri-ai-platform](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform) | AI OS Shell, backend, factory, Control Plane, provider/runtime contracts, release evidence | Единственный product/runtime source of truth |
| [kolibri-mesh](https://github.com/rd8r8bkd9m-tech/kolibri-mesh) | Go/AWG mesh component | Оставить отдельным versioned component, но интегрировать только через signed manifest и dynamic membership contract |

kolibri-mesh пока не доказывает требуемую схему 21+ dynamic membership: README описывает coordinator-agent и фиксированную адресную карту. Это полезный сетевой компонент, но не самостоятельная истина о текущем fleet.

### B. Сильные доноры, которые нужно mining/import, а не merge wholesale

| Репозиторий | Сильные части | Почему не source of truth |
| --- | --- | --- |
| [kolibri](https://github.com/rd8r8bkd9m-tech/kolibri) | React 19 workspace, typed API, deterministic Decimal calculator, estimate tests, PDF/WeasyPrint, provider catalog, mobile UX evidence | private prototype; default CI падает на Playwright E2E; в tree есть runtime/probe и screenshot artifacts |
| [vertical](https://github.com/rd8r8bkd9m-tech/vertical) | правильная доменная цепочка заявка → замер → смета → КП → договор → акт → оплата; C23 money core; shared types | всего 5 commits; default CI failure; документы/AI части ещё обозначены placeholder |
| [kolibri-stroy](https://github.com/rd8r8bkd9m-tech/kolibri-stroy) | реальные estimate/document modules и tests, Telegram Mini App flow | standalone construction vertical, не общий AI OS |
| [qwen-kolibri-rust-gateway](https://github.com/rd8r8bkd9m-tech/qwen-kolibri-rust-gateway) | компактный Rust OpenAI-compatible gateway, SSE/tool passthrough, session routing | spike из 2 commits; нет CI/release evidence; нельзя разворачивать рядом со вторым public gateway |
| [kolibri-studio-factory](https://github.com/rd8r8bkd9m-tech/kolibri-studio-factory) | Registrar contract, roles, subagents, gates, ADR, OpenAPI SDK generation, factory portal patterns | ранняя hotel-oriented factory; не текущий runtime; C#/TS/Kotlin/Swift generated surface слишком широк |
| [kolibri-project](https://github.com/rd8r8bkd9m-tech/kolibri-project) | FormulaLM implementation/test, C formula/swarm core, WASM, training/reasoning research, benchmarks | 510 MB research monolith; committed build outputs/corpora/archives; 307 commits; no product CI gate |
| [os-main-8](https://github.com/rd8r8bkd9m-tech/os-main-8) | swarm1000 scheduler concepts, formula evolution, C/Python AI core, test inventory | legacy AI OS line; default HEAD failure; claims и implementation maturity неоднородны |
| [pilot](https://github.com/rd8r8bkd9m-tech/pilot) | decimal VM, fractal KV, compact C node, signed decisions | research milestone; duplicated README sections; default HEAD failure |
| [omega](https://github.com/rd8r8bkd9m-tech/omega) | compact formula DSL, offline-first model, integrity/signature concepts | research prototype, не learning-plane production system |
| [kolibri-ai](https://github.com/rd8r8bkd9m-tech/kolibri-ai) | decimal cognition/formula evolution/fractal hierarchy concept docs | 7 commits; mostly conceptual JS/docs; no CI evidence |

### C. Вертикальные product laboratories

Их задача — давать domain contracts, fixtures и UX patterns, но не становиться отдельным Control Plane:

- construction: kolibri, vertical, kolibri-stroy, smeta, smeta-generator, i-cannot-help-with-t;
- hotel: hotel, ishotel, -book, kolibri-hotel-saas-p, hotel-yelabuga-app, t-bank-style-booking;
- other verticals: motor-doctor-auto-se, zavod/zavodik.

### D. Archive/placeholder candidates

Пока ничего не удалять. После signed backup и provenance inventory можно предложить archive:

- empty/no default branch: rd8r8bkd9m-tech profile repo, vt-client-wasm, kolibri-project-main, smeta_design_kit_v1;
- README-only или почти пустые: shtukatur-smeta, status, servis-os, vpn;
- exact/near duplicates: zavod и zavodik; три поколения kolibri-archiver; несколько hotel SaaS variants;
- stale generated/template products: t-bank-style-booking, motor-doctor-auto-se и ряд hotel clones;
- asset-only: smeta_enterprise_addons_v1.

GitHub сейчас показывает archived=0, то есть исторические и пустые репозитории никак не отделены от актуальных.

## 5. Полный реестр 37/37

Обозначения CI: SUCCESS/FAILURE — default HEAD status rollup; UNKNOWN — нет rollup. Это не заменяет release gate.

| Repository | Vis. | Branches | Open PR | Activity | HEAD CI | Классификация |
| --- | --- | ---: | ---: | --- | --- | --- |
| [kolibri-ai-platform](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform) | public | 296 | 91 | 2026-07-10 | SUCCESS | canonical product/runtime |
| [rd8r8bkd9m-tech](https://github.com/rd8r8bkd9m-tech/rd8r8bkd9m-tech) | public | 0 | 0 | 2026-06-29 | UNKNOWN | empty profile repo |
| [kolibri](https://github.com/rd8r8bkd9m-tech/kolibri) | private | 2 | 0 | 2026-06-29 | FAILURE | premium workspace + estimate donor |
| [kolibri-mesh](https://github.com/rd8r8bkd9m-tech/kolibri-mesh) | public | 2 | 1 | 2026-06-28 | UNKNOWN | network component candidate |
| [t-bank-style-booking](https://github.com/rd8r8bkd9m-tech/t-bank-style-booking) | private | 7 | 6 | 2026-05-21 | SUCCESS | booking/Spark template, not Kolibri core |
| [kolibri-project](https://github.com/rd8r8bkd9m-tech/kolibri-project) | public | 19 | 5 | 2026-05-21 | UNKNOWN | FormulaLM/C/WASM research vault |
| [qwen-kolibri-rust-gateway](https://github.com/rd8r8bkd9m-tech/qwen-kolibri-rust-gateway) | public | 1 | 0 | 2026-05-12 | UNKNOWN | Rust provider-gateway spike |
| [hotel-yelabuga-app](https://github.com/rd8r8bkd9m-tech/hotel-yelabuga-app) | private | 1 | 0 | 2026-05-11 | UNKNOWN | hotel mobile vertical |
| [vertical](https://github.com/rd8r8bkd9m-tech/vertical) | public | 4 | 1 | 2026-04-27 | FAILURE | construction domain/core donor |
| [kolibri-stroy](https://github.com/rd8r8bkd9m-tech/kolibri-stroy) | private | 1 | 0 | 2026-03-21 | UNKNOWN | construction Telegram/docs donor |
| [kolibri-archiver-v85-compressc](https://github.com/rd8r8bkd9m-tech/kolibri-archiver-v85-compressc) | public | 1 | 0 | 2026-02-19 | UNKNOWN | compression experiment v85 |
| [kolibri-archiver-v85](https://github.com/rd8r8bkd9m-tech/kolibri-archiver-v85) | public | 1 | 0 | 2026-02-19 | UNKNOWN | compression experiment v85 |
| [kolibri-archiver](https://github.com/rd8r8bkd9m-tech/kolibri-archiver) | public | 1 | 0 | 2026-02-18 | UNKNOWN | earlier compression experiment |
| [zavodik](https://github.com/rd8r8bkd9m-tech/zavodik) | public | 1 | 0 | 2026-02-04 | UNKNOWN | content factory AI Studio clone |
| [motor-doctor-auto-se](https://github.com/rd8r8bkd9m-tech/motor-doctor-auto-se) | private | 7 | 5 | 2026-02-04 | UNKNOWN | automotive vertical/template |
| [os-main-8](https://github.com/rd8r8bkd9m-tech/os-main-8) | public | 21 | 3 | 2026-02-04 | FAILURE | legacy AI OS/swarm research |
| [zavod](https://github.com/rd8r8bkd9m-tech/zavod) | public | 2 | 1 | 2026-02-02 | UNKNOWN | near-duplicate of zavodik |
| [pilot](https://github.com/rd8r8bkd9m-tech/pilot) | public | 2 | 1 | 2026-01-24 | FAILURE | decimal VM/Omega research |
| [hotel](https://github.com/rd8r8bkd9m-tech/hotel) | public | 1 | 0 | 2026-01-24 | FAILURE | C hotel SaaS prototype |
| [smeta](https://github.com/rd8r8bkd9m-tech/smeta) | public | 17 | 8 | 2026-01-19 | SUCCESS | legacy estimate PWA donor |
| [smeta-generator](https://github.com/rd8r8bkd9m-tech/smeta-generator) | public | 9 | 1 | 2026-01-19 | FAILURE | multi-platform estimate donor |
| [-book](https://github.com/rd8r8bkd9m-tech/-book) | private | 7 | 5 | 2026-01-19 | FAILURE | hotel SaaS duplicate/candidate |
| [shtukatur-smeta](https://github.com/rd8r8bkd9m-tech/shtukatur-smeta) | private | 2 | 1 | 2026-01-14 | UNKNOWN | README-only placeholder |
| [ishotel](https://github.com/rd8r8bkd9m-tech/ishotel) | private | 2 | 0 | 2026-01-14 | FAILURE | hotel monorepo donor |
| [status](https://github.com/rd8r8bkd9m-tech/status) | private | 2 | 1 | 2026-01-14 | UNKNOWN | README-only placeholder |
| [servis-os](https://github.com/rd8r8bkd9m-tech/servis-os) | private | 2 | 1 | 2026-01-14 | UNKNOWN | README-only placeholder |
| [kolibri-studio-factory](https://github.com/rd8r8bkd9m-tech/kolibri-studio-factory) | private | 3 | 0 | 2026-01-10 | SUCCESS | factory contract/process donor |
| [kolibri-hotel-saas-p](https://github.com/rd8r8bkd9m-tech/kolibri-hotel-saas-p) | private | 6 | 5 | 2026-01-05 | SUCCESS | hotel UI/domain donor |
| [kolibriai-vpn](https://github.com/rd8r8bkd9m-tech/kolibriai-vpn) | private | 2 | 0 | 2025-12-15 | SUCCESS | historical Rust VPN product |
| [vt-client-wasm](https://github.com/rd8r8bkd9m-tech/vt-client-wasm) | private | 0 | 0 | 2025-12-08 | UNKNOWN | empty |
| [kolibri-ai](https://github.com/rd8r8bkd9m-tech/kolibri-ai) | public | 3 | 2 | 2025-11-30 | UNKNOWN | formula cognition concept |
| [kolibri-project-main](https://github.com/rd8r8bkd9m-tech/kolibri-project-main) | private | 0 | 0 | 2025-11-29 | UNKNOWN | empty |
| [i-cannot-help-with-t](https://github.com/rd8r8bkd9m-tech/i-cannot-help-with-t) | private | 12 | 5 | 2025-11-24 | FAILURE | broad construction estimator donor |
| [vpn](https://github.com/rd8r8bkd9m-tech/vpn) | public | 2 | 1 | 2025-11-14 | UNKNOWN | README-only placeholder |
| [omega](https://github.com/rd8r8bkd9m-tech/omega) | public | 7 | 3 | 2025-11-13 | SUCCESS | Formula DSL/offline AI research |
| [smeta_design_kit_v1](https://github.com/rd8r8bkd9m-tech/smeta_design_kit_v1) | public | 0 | 0 | 2025-11-09 | UNKNOWN | empty |
| [smeta_enterprise_addons_v1](https://github.com/rd8r8bkd9m-tech/smeta_enterprise_addons_v1) | public | 1 | 0 | 2025-11-09 | UNKNOWN | asset-only |

## 6. Capability map

### Factory / swarm / continuity

Authoritative current implementation surface:

- kolibri-ai-platform: Control Plane, Agent Host, leases, artifacts, Mimo tasks, Telegram, fleet and release evidence.

Useful donors:

- kolibri-studio-factory: Registrar, role assignment, subagent/gate/DoD protocol, ADR discipline;
- os-main-8: swarm1000 planner/scheduler/state/worktree patterns;
- kolibri-project: C swarm core and research implementations.

Правильный перенос: принять contracts и tests, затем переписать/адаптировать под frozen Kolibri OS V1 domain model. Не переносить старый scheduler или второй Control Plane целиком.

### Provider gateway / Mimo / Codex / OpenAI compatibility

- GitHub code search по Mimo возвращает активную концентрацию в kolibri-ai-platform: runner repair, unified API enablement, canary and routing artifacts.
- qwen-kolibri-rust-gateway содержит чистый Rust spike для OpenAI-compatible API, SSE, tool calls и session suffix routing.
- private kolibri описывает каталог из нескольких внешних providers и typed client.

Следствие: Universal Provider Gateway должен жить в kolibri-ai-platform/Rust Core. qwen gateway — донор протокола и tests, а не отдельный production endpoint.

### FormulaLM

GitHub evidence разделяется на три слоя:

1. Реальный старый implementation/test:
   - [backend/service/formula_lm.py](https://github.com/rd8r8bkd9m-tech/kolibri-project/blob/main/backend/service/formula_lm.py)
   - [tests/test_formula_lm.py](https://github.com/rd8r8bkd9m-tech/kolibri-project/blob/main/tests/test_formula_lm.py)
2. Концептуальные линии:
   - kolibri-ai, omega, pilot, os-main-8;
3. Текущий product boundary:
   - kolibri-ai-platform docs/branches и локальный canonical implementation.

Старый formula_lm.py нельзя считать production learning plane. Нужен перенос идей только после:

- LearningCandidate schema;
- secret/PII/license/consent sanitizer;
- immutable provenance hashes;
- async training boundary;
- independent eval/canary/promotion/rollback;
- доказательства, что production weights не мутируют в синхронном customer request.

### Vista OS / Shell

GitHub code search не находит продуктового Vista OS в owner repositories; результаты относятся к случайным corpus entries. Запущенный Vista OS находится как локальный пакет, а не как канонический GitHub source.

Следствие:

- Vista — сильный UX/component donor;
- его нельзя объявлять новой production codebase до импорта в canonical repo;
- импорт должен сохранить лёгкость, desktop/window metaphor и компонентную архитектуру;
- API/demo data должны быть полностью заменены на Kolibri contracts;
- mascot/branding берутся только из canonical Kolibri assets;
- local ZIP provenance и лицензии должны быть зафиксированы.

### GoMesh / mesh

- standalone kolibri-mesh содержит Go/AWG mesh implementation;
- code search GoMesh показывает operational reports, Agent Host и Telegram/dispatcher integration главным образом в kolibri-ai-platform;
- отдельного owner repo, который можно доказательно назвать production GoMesh source, нет.

Следствие: network library и fleet authority нужно развести:

- kolibri-mesh — versioned network component;
- signed dynamic fleet manifest и Home-only Control Plane membership — kolibri-ai-platform;
- static host/IP list в README не является durable identity и не должен попадать в scheduler logic.

### Construction / estimates / documents

Самые сильные источники:

- kolibri: Decimal calculator, 34 golden tests по README, PDF/WeasyPrint и typed UI;
- vertical: C23 money authority и правильный end-to-end domain workflow;
- kolibri-stroy: конкретные estimate/document modules и tests;
- i-cannot-help-with-t: FER/GESN/TER, measurement parsing и document variants;
- smeta-generator: multi-platform packaging and shared packages;
- smeta: простая offline/PWA interaction model.

Целевой перенос:

1. Domain schema и fixtures.
2. Детерминированный calculator как единственный money authority.
3. Provenance каждой нормы/цены/коэффициента.
4. Typed artifacts PDF/PDF-X/XLSX/DOCX.
5. LLM только разбирает ввод, объясняет и предлагает; не считает финальную сумму.
6. Contract tests и golden documents.

### Hotel и другие verticals

Hotel portfolio показывает полезные паттерны multi-tenancy, booking, RBAC, dashboards, payment/Telegram flows и native/mobile surfaces. Но 13 локальных checkout одного hotel repo и несколько параллельных hotel repos показывают повторную генерацию вместо продуктовой эволюции.

Эти проекты нужно использовать как domain benchmark и regression corpus, а не как отдельные архитектурные центры.

## 7. GitHub health

### kolibri-ai-platform

Open PR snapshot:

- 91 open;
- 78 draft;
- 14 BLOCKED или DIRTY;
- 3 с failed checks;
- 11 без checks.

Последние значимые примеры:

- [PR #176](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/176) — Rust swarm/event authority, CI success, но merge state DIRTY;
- [PR #167](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/167) — lease watchdog repair, draft/clean/green, но уже может быть superseded текущей локальной реализацией;
- [PR #166](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/166) — governing chat/Home routing, draft/failed/unstable;
- [PR #156](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/156) — UI redesign, draft/dirty.

Default main CI run:

- [Kolibri CI run 28732801500](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/actions/runs/28732801500) — success для HEAD 4675748fb1a8.

Это доказывает только green default baseline от 2026-07-05. Оно не доказывает текущую local implementation ветку, Home production runtime или новый frontend.

### Другие CI observations

- kolibri: три последних main runs failed; в последнем backend/frontend/docker прошли, Playwright E2E failed.
- vertical: последние main runs failed; js и core-c jobs не завершились успешно, detailed logs API не сохранил.
- t-bank-style-booking и motor-doctor-auto-se: latest workflows — Dependabot startup failures, а не product tests.
- kolibri-project: latest successful runs — Dependabot/Copilot, не интеграционный gate платформы.

### Issue health

Все 32 open issues находятся в kolibri-ai-platform. Значительная часть — повторяющиеся June incidents о stale queue, missing target nodes, uiap/qjns и FormulaLM guard. Они полезны как исторический incident corpus, но не являются текущей runtime truth без повторной проверки.

Нужно:

1. перепроверить каждый P0 против текущего Home-only runtime;
2. объединить duplicates в один incident/root cause;
3. закрывать только с evidence link;
4. не создавать новый issue на каждый watchdog tick или агентный fanout.

## 8. Local Git topology

Read-only scan Mac home нашёл:

- 172 Git worktrees/checkouts;
- 70 worktrees, связанных с owner repos;
- 18 уникальных owner repos имеют локальные checkout.

Главные дубликаты:

| Remote repo | Local worktrees/checkouts |
| --- | ---: |
| kolibri-ai-platform | 38 |
| hotel | 13 |
| kolibri-project | 4 |
| остальные 15 owner repos | по 1 |

Это создаёт риск:

- разные agents редактируют разные поколения одного продукта;
- локальный main может не соответствовать remote main;
- old worktree принимается за production source;
- одинаковый проект клонируется вместо продолжения backlog/checkpoint.

Нужен один signed worktree registry:

- repo;
- absolute path;
- branch;
- HEAD;
- dirty/staged/untracked;
- owner task/workstream;
- status active/frozen/archive-candidate;
- canonical replacement;
- last verified timestamp.

Очистка worktrees и веток должна выполняться только после backup и owner approval.

## 9. Что переносить первым

Порядок основан на полезности для утверждённого Kolibri AI OS plan:

1. kolibri-studio-factory
   - Registrar/gates/roles/ADR patterns;
   - перенести как policy/contracts, не как второй runtime.
2. qwen-kolibri-rust-gateway
   - OpenAI-compatible/SSE/tool-call conformance tests;
   - использовать в Rust Provider Gateway.
3. kolibri + vertical + kolibri-stroy
   - единый construction vertical contract;
   - calculator tests, document fixtures, typed estimate artifact.
4. os-main-8 swarm1000
   - извлечь actor/DAG/checkpoint/worktree tests;
   - сверить с текущим V1 SwarmPlan, не копировать старую оркестрацию.
5. kolibri-project FormulaLM
   - только в quarantined research namespace;
   - сначала sanitizer/eval boundary, затем эксперимент.
6. Vista local package
   - shell/window/component patterns после UI approval;
   - заменить весь demo API и mock state.
7. kolibri-mesh
   - reproducible Go build, signed release, dynamic enrollment tests;
   - убрать static identity из runtime decisions.

## 10. Что не переносить

- committed env, credentials, runtime probe results и local-data logs;
- build-asan/build-fuzz outputs, binaries, archives, screenshots и generated SDK без необходимости;
- corpora без provenance/license/consent;
- README claims без воспроизводимого benchmark;
- вторые Control Plane, Telegram gateway, provider gateway или user database;
- hardcoded hostnames/IP как durable IDs;
- repeated hotel/content/smeta clones целиком;
- generated UI pages, если они не подтверждены current product contract и responsive E2E.

Особый security note: root tree kolibriai-vpn содержит tracked path .env. Файл не читался. Перед любым reuse нужен history secret scan и, если значение было реальным, rotation.

## 11. Repo consolidation plan

### Phase G0 — freeze и evidence

- Временно прекратить создание новых fanout branches, кроме P0 fix/release.
- Экспортировать machine-readable repo/branch/PR/worktree manifest.
- Зафиксировать commit hashes доноров.
- Создать capability import ledger.
- Выполнить public-repo exposure/secret audit для kolibri-ai-platform.

### Phase G1 — source-of-truth governance

- Kolibri AI Platform — canonical product/runtime monorepo.
- Kolibri Mesh — отдельный signed network component.
- Kolibri Project — research vault, read-only по умолчанию.
- Vertical repos — incubators/reference, не production authority.
- Остальные — classify keep/freeze/archive после owner approval.

### Phase G2 — PR backlog reduction

- Сгруппировать 91 platform PR по capability и ancestry.
- Определить superseded/duplicate/contains-unique-evidence.
- Сохранить уникальные artifacts и tests.
- Перенести только focused diffs на свежую canonical branch.
- Не merge giant stale branches.

### Phase G3 — capability mining

Для каждого донора:

1. сформулировать capability contract;
2. импортировать golden fixtures/tests;
3. сделать license/provenance review;
4. реализовать минимальный adapter/core;
5. запустить contract, browser и security tests;
6. добавить evidence в capability ledger;
7. только после этого закрыть старый репозиторий как superseded.

### Phase G4 — release authority

- Signed immutable release строится только из canonical commit.
- CI проверяет source manifest, contracts, secret scan и artifact hashes.
- Home-only canary подтверждает backend/frontend/provider/fleet behavior.
- GitHub status не заменяет runtime evidence.
- Production claim разрешён только после readiness matrix и rollback proof.

## 12. Decision matrix для master plan

| Вопрос | Решение |
| --- | --- |
| Где развивать Kolibri AI OS? | kolibri-ai-platform |
| Где держать network implementation? | kolibri-mesh как versioned component, contracts в platform |
| Где искать FormulaLM идеи/код? | kolibri-project, omega, pilot, os-main-8, kolibri-ai; перенос только через learning boundary |
| Где искать лучший construction UX/core? | kolibri, vertical, kolibri-stroy, затем smeta-generator/i-cannot-help-with-t |
| Где искать factory process patterns? | kolibri-studio-factory и current platform |
| Где искать Rust gateway patterns? | qwen-kolibri-rust-gateway |
| Является ли Vista GitHub source? | нет; локальный UX donor |
| Есть ли отдельный canonical GoMesh repo? | нет; operational evidence в platform, network code в kolibri-mesh |
| Можно ли доверять production-ready в README? | нет без CI, runtime и release evidence |
| Нужно ли удалять старые repos сейчас? | нет; сначала signed backup, provenance и owner approval |

## 13. Доказательные ссылки

- [GitHub profile](https://github.com/rd8r8bkd9m-tech)
- [Canonical platform](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform)
- [Platform Actions](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/actions)
- [Platform pull requests](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pulls)
- [Platform issues](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/issues)
- [FormulaLM implementation donor](https://github.com/rd8r8bkd9m-tech/kolibri-project/blob/main/backend/service/formula_lm.py)
- [Vertical architecture](https://github.com/rd8r8bkd9m-tech/vertical/blob/main/docs/ARCHITECTURE.md)
- [Vertical estimate engine](https://github.com/rd8r8bkd9m-tech/vertical/blob/main/docs/ESTIMATE_ENGINE.md)
- [Factory Registrar contract](https://github.com/rd8r8bkd9m-tech/kolibri-studio-factory/blob/main/factory/REGISTRAR_CONTRACT.md)
- [Mesh component](https://github.com/rd8r8bkd9m-tech/kolibri-mesh)
- [Rust Qwen/Kolibri gateway](https://github.com/rd8r8bkd9m-tech/qwen-kolibri-rust-gateway)

## 14. Bottom line

Портфель содержит достаточно сильных наработок для реализации Kolibri AI OS, но проблема не в нехватке функций. Проблема — отсутствие строгой границы между canonical product, research, generated prototypes и runtime evidence.

Следующий этап должен быть не ещё одной генерацией приложения, а контролируемой консолидацией:

1. один canonical Shell/Control/Factory;
2. один Home-only Control Plane;
3. один provider/tool gateway;
4. versioned mesh component;
5. один FormulaLM learning boundary;
6. vertical capabilities как plugins/contracts;
7. imports только через tests/provenance/evidence;
8. release только из signed canonical commit.

Так Vista, FormulaLM, Mimo, Codex, GoMesh, construction estimates и старые AI OS исследования усиливают одну систему, а не создают новые несовместимые центры.
