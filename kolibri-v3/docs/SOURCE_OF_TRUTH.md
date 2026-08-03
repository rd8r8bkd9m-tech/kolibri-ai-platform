# Источники истины Kolibri V3

Одна сущность имеет одного канонического владельца. Кэши, UI-state,
сгенерированные файлы и provider execution state не становятся вторым
источником истины.

| Данные/контракт | Канонический владелец | Производные представления |
| --- | --- | --- |
| пользователи, роли, проекты, чаты, артефакты | V3 backend + его миграции | web/mobile state |
| оценки и версии смет | V3 backend; детерминированные вычисления Rust kernel там, где подключены | widgets, exports |
| browser/backend API contracts | backend schemas/routes | TypeScript adapters и generated contracts |
| runtime health и instance identity | V3 backend process, запущенный supervisor | Next health proxy, UI |
| provider credentials/execution | Provider Execution Authority | V3 хранит только безопасный статус и intent |
| тарифы, payment intents, подписки и проверенные T-Банк события | V3 backend billing domain + append-only migrations | web/mobile payment state, redacted platform-admin read models |
| production release artifact | чистый Git commit + `deploy/portable` builder | tarball, manifest, evidence |
| development database | `var/kolibri-v3.db`, которой владеет `scripts/dev-backend.sh` | backup files |
| история чата для agent runtime | V3 backend: `chat_messages` и связанные run records | `agent_runtime_session_cache` и provider threads — только disposable acceleration cache |
| durable-генерация сметы, checkpoints, evidence и построчная lineage | V3 backend, append-only migration 051; exact `ProjectCase` и project `technology_cards` revision | provider tasks/threads, AG-UI progress и QA reports — только производные представления |
| каталог смет, кандидаты и technology cards | V3 backend: `catalog_entries`, `catalog_candidates`, `technology_card_*` и EstimateVersion snapshots | autocomplete/UI state и AI proposal — только производные кандидаты |
| официальные сметные документы | V3 backend migration 050: immutable `estimate_document_issues.snapshot_json` and final-byte `estimate_document_artifacts` in tenant CAS | PDF/DOCX/XLSX/ZIP downloads and Assistant UI card |
| личные ценовые наблюдения и market aggregates | V3 backend: расширенная `price_observations`, consent events и `market_price_aggregates` | aggregate API/UI показывает только обезличенную статистику |
| общие генерируемые контракты | генераторы/validators в `server/` | `generated/` (не редактировать вручную) |

## Правила изменения

- Схема backend меняется новой миграцией; существующая выпущенная миграция не
  переписывается.
- Клиент не изобретает fallback-данные, если authority недоступен. Ошибка
  показывается явно и fail-closed там, где этого требует безопасность.
- Межконтурный контракт меняется authority-first: schema/producer, contract
  tests, затем consumers.
- Runtime state (`var/`, caches, build output) никогда не используется как
  исходник продукта и не коммитится.
- Legacy-каталоги выше `kolibri-v3/` не являются fallback или источником кода.

Изменение владельца любой строки таблицы требует ADR.
