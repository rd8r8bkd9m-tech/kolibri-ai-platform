# Kolibri V3 R1: семидневная дорожная карта до production

- Статус: active
- Дата фиксации: 30 июля 2026 года
- Целевой запуск: 6 августа 2026 года, 18:00 МСК
- Production: `https://kolibriai.ru/app`
- Корневой маршрут: `https://kolibriai.ru/` перенаправляет в приложение
- Исходная точка: приложение уже работает в production; R1 является
  контролируемым обновлением, а не greenfield-запуском
- Машинный план: `release/r1-2026-08-06/release-plan.yaml`
- Текущий release control board:
  `release/r1-2026-08-06/STATUS.md`
- Финальное решение о переключении production: владелец продукта

## 0. Правило непрерывности

После любой остановки разработка возобновляется не по последней случайной
реплике, а по `release/r1-2026-08-06/STATUS.md`: там зафиксированы активные
потоки, владельцы, доказательства, блокеры и следующий gate. Любая новая
вводная пользователя уточняет продукт, но не отменяет незавершённые P0/P1,
если пользователь явно не меняет цель релиза.

Все относящиеся к текущему продукту исходники и долговечные артефакты хранятся
внутри `kolibri-v3`. На 30 июля уже консолидированы:

- `apps/kolibri-mobile` — Expo/React Native клиент;
- `packages/estimate-kernel-rs` — Rust conformance foundation;
- `docs/design-evidence` — долговечные визуальные исследования;
- `release/r1-2026-08-06` — машинный план, status и будущие release evidence.

Старые V1/V2, архивы и runtime-кэши не переносятся автоматически и не являются
источником истины R1.

## 1. Цель релиза

За семь календарных дней безопасно обновить уже работающий production до
ограниченного, но законченного Kolibri V3 R1:
универсальное AI-first рабочее место с первым активированным коммерческим
vertical pack `construction.estimates`. Пользователь с desktop или мобильного
Safari может зарегистрироваться, вести долговечный диалог с агентом, создать и
отредактировать предварительную смету, проверить источники, сохранить версию и
выгрузить согласованный документ.

Релиз является первым промышленным вертикальным срезом будущего конкурента
`1С:Смета` и `ГРАНД-Смета`, но не заявляет полный функциональный паритет с ними.
Полный паритет требует нормативных лицензий, нескольких методов расчёта,
машиночитаемых форматов экспертизы, актов, учёта факта и интеграций. Эти
направления зафиксированы после недельного плана и не должны разрушать R1.

## 2. Жёсткие принципы недели

1. Один V3 frontend, один Product/Data backend и одна production release lane.
2. `kolibri-v3/backend` становится единственным Product/Data Authority R1.
   `kolibri-backend` не может быть скрытым вторым API, хранилищем истории или
   fallback. Нужные runtime-компоненты подключаются через явно описанный
   Logical Home/A2A boundary.
3. Desktop не меняется функционально или визуально из-за мобильной работы.
4. Mobile Safari получает тот же продукт и данные через responsive web.
   Нативный Expo-клиент проходит truth spike, но публикация в App Store и
   Google Play не блокирует web-production.
5. Никакой новой функции без работающего backend-контракта, ошибок,
   наблюдаемости и acceptance-теста.
6. Никаких декоративных кнопок. Недоступная возможность скрывается либо
   показывает честную причину недоступности.
7. Сметные итоги считает только server-authoritative движок. UI и модель не
   являются источниками истины.
8. Все цены и нормативные утверждения имеют происхождение, дату, регион,
   единицу измерения, налоговый статус и уровень подтверждения.
9. После freeze разрешены только исправления P0/P1, тесты, документация релиза
   и безопасные операционные изменения.
10. Production переключается только после canary, резервной копии, проверки
    восстановления и явного подтверждения владельца.
11. Rust-ready граница расчёта фиксируется до R1: versioned JSON contract,
    отдельный side-effect-free crate и общий golden corpus обязательны. Сам
    production cutover остаётся запрещён до доказанного паритета.
12. Универсальный Core не импортирует строительные сущности. Строительство
    включается как trusted, versioned и tenant-entitled vertical pack через
    capability/renderer registry.
13. Рабочий `kolibriai.ru/app` не заменяется новым клиентским экспериментом.
    Expo, Tauri и device SDK подключаются к тем же контрактам и проходят
    отдельные gates; production обновляется атомарно с canary и rollback.
14. Общая стратегия устройств является protocol-first: browser/PWA,
    Expo/React Native, Tauri Edge Shell и headless adapters используют
    server-authoritative device/vertical capabilities и переносимые Rust crates.
15. Клиентский личный кабинет и control plane владельца — разные поверхности
    одной identity/tenancy-модели. Единственный platform owner получает
    глобальное управление, но обычный владелец данных клиента не выводится из
    локального UI-флага и не получает platform authority.

## 3. Что входит в R1

### 3.1. Обязательный пользовательский путь

1. Открыть `kolibriai.ru` по домашнему или мобильному интернету.
2. Зарегистрироваться или войти.
3. Создать новый чат/проект.
4. Отправить обычный вопрос и увидеть начало работы без запуска нового
   runtime-процесса на каждый запрос.
5. Закрыть или обновить страницу и продолжить тот же долговечный диалог.
6. Задать вопрос «Какая погода в Москве?» и получить текущий ответ с
   источником и временем данных.
7. Попросить создать изображение и получить сохранённый artifact с preview и
   скачиванием. Если этот путь не проходит end-to-end, релиз не показывает
   действие «Создать изображение».
8. Приложить поддерживаемый файл и получить видимый статус загрузки,
   обработки или ошибки.
9. Создать предварительную смету из чата, открыть её в редакторе, изменить
   позицию и вернуться в чат без потери черновика и позиции прокрутки.
10. Сохранить новую версию сметы, увидеть итог и статус достоверности.
11. Выгрузить одну и ту же сохранённую версию в PDF, XLSX и DOCX.
12. Выйти из аккаунта; закрытая информация после выхода недоступна.

### 3.2. Mobile web

- iPhone Safari: 375×812, 390×844 и 430×932;
- Android Chrome: 360×800 и 412×915;
- светлая, тёмная и системная темы;
- safe-area, экранная клавиатура, ориентация portrait;
- hamburger, drawer, проекты, библиотека, настройки, профиль, выбор модели;
- long press беседы с существующими действиями;
- composer, вложения, отправка, остановка и повтор;
- карточный редактор сметы без горизонтального переполнения;
- возврат из редактора на основной экран с сохранением состояния;
- отсутствие изменений desktop на ширине 960 px и выше.

### 3.3. Chat и агенты

- один постоянно работающий runtime на соответствующем execution node;
- standard и developer используют один provider-neutral runtime adapter;
- physical execution plane выбирается серверной capability matrix, а не
  переданным браузером именем plane: standard может работать через direct
  model runtime, production developer всегда идёт во внешний
  Home/Provider Agent Host, а embedded developer допустим только локально;
- durable user message, run, assistant message и artifact;
- AG-UI stream с упорядоченными событиями;
- reconnect/resume по server cursor;
- явная отмена server run, а не только локального `fetch`;
- A2A остаётся внутренним транспортом и не становится историей чата;
- нет автоматической подмены выбранного runtime другим провайдером;
- ошибки провайдера показываются безопасно и позволяют повторить запрос;
- модель, effort и service tier валидируются сервером.

#### 3.3.1. Control plane владельца

Существующий личный кабинет остаётся пользовательской поверхностью. Только
единственный, повышенный trusted server operation platform owner видит
отдельный раздел управления платформой:

- bounded список организаций/клиентов и пользователей без секретов;
- статус организации, план и явные количественные лимиты;
- server-authoritative включение или блокировка dev-режима;
- разрешённые runtime profiles и catalog-approved модели;
- отзыв активных web/mobile сессий;
- аудит каждой административной мутации;
- блокировка организации без удаления её канонических данных.

В том же owner-only control plane существует отдельная поверхность
«Агенты и эксплуатация», не смешанная с управлением клиентами:

- реестр агентских service identities, execution nodes и их состояния;
- назначенные репозитории и mutable workspaces;
- очередь целей/задач, текущие runs, этапы, логи и уведомления;
- diff файлов, результаты тестов и артефакты до и после изменения;
- deploy/restart/rollback как наблюдаемые durable операции;
- отмена задачи, отзыв делегированной authority и общий kill switch;
- история действий агента прямо в связанном Product Chat.

Любая административная запись требует owner authority, CSRF для browser
mutation, транзакцию и audit event. Dev-режим дополнительно требует глобального
server gate, tenant policy, developer-capable runtime и отдельный явно
настроенный workspace. Клиентский grant действует только вместе с
tenant/user-bound привязкой к изолированному workspace; общий операторский
workspace не удовлетворяет этому условию. При отсутствии такой привязки запуск
закрывается безопасно, даже если переключатель политики включён. Dev-runtime не
получает доступ к каталогу активного immutable production release.

Владелец может создать trusted-agent profile с политикой
`danger-full-access + approval=never`. Это штатный автономный режим: после
назначения цели агент не запрашивает подтверждение каждой команды внутри
делегированного workspace/environment scope. Authority выдаётся агентской
service identity, а не копируется из browser session; она связана с задачей или
постоянной owner policy, epoch, workspace, допустимыми средами, бюджетом,
конкурентностью и отзывом. Владелец наблюдает работу и получает уведомления,
но не обязан вручную проводить каждый шаг. Для особо необратимых классов
эффектов владелец отдельно может включить review gate.

Публичный API-процесс никогда не исполняет такой shell локально. Agent Host,
Home/Provider worker и A2A являются внутренней частью Kolibri: пользователь
ставит задачу, видит выполнение и управляет им из приложения, хотя привилегированный
процесс технически изолирован от web-backend и immutable production release.
Команда, результат, authority epoch, diff, deploy и rollback фиксируются
durably.

### 3.4. Смета и документы

- детерминированная арифметика `Decimal`;
- явные правила округления и налога;
- раздельные работы, материалы, оборудование, доставка, накладные расходы,
  резерв, скидка и налог;
- optimistic concurrency по версии;
- immutable history сохранённых версий;
- статусы `needs_input`, `preliminary`, `source_backed`, `verified`;
- источник и свежесть каждой подтверждаемой цены;
- один сохранённый snapshot для Canvas, PDF, XLSX и DOCX;
- отсутствие вымышленных ФЕР, ТЕР, ГЭСН, ФСНБ или коммерческих цен;
- R1 не выдаёт предварительную коммерческую смету за документ, готовый к
  государственной экспертизе.

### 3.5. Production operations

- immutable release archive и manifest с commit SHA и SHA-256;
- systemd supervision frontend, Product API и необходимых workers;
- loopback binding внутренних HTTP-процессов;
- TLS и единый проверенный Nginx-конфиг;
- миграции только вперёд с совместимым canary;
- SQLite online backup до миграции;
- проверенное восстановление backup на отдельном пути;
- canary на новом localhost-порту;
- атомарное переключение и проверенный rollback;
- structured logs, release ID, request/run IDs;
- health, readiness и worker liveness;
- алерт на недоступность приложения, остановку worker и рост ошибок.

### 3.6. Rust foundation

- независимый crate `packages/estimate-kernel-rs`;
- contracts `contracts/v1/estimates`;
- только строковые decimal-величины, без `float`;
- явные категории работ, материалов, оборудования, услуг и доставки;
- единая версия правил и политика округления;
- price status и release fail-closed;
- общий golden fixture для языковых реализаций;
- CLI adapter для shadow/conformance tests;
- запрет сетевого доступа, БД, UI, AG-UI и A2A внутри ядра.

### 3.7. Universal platform foundation

- platform Core: identity, tenancy, projects, threads, runs, agents, artifacts,
  documents, approvals, usage и capability snapshot;
- manifest `contracts/v1/verticals/vertical-pack-manifest.schema.json`;
- первый пакет `construction.estimates`;
- tenant/server-authoritative activation и entitlement;
- allowlisted web/native renderer keys без runtime-загрузки произвольного кода;
- доменные schemas, policies, agent skills и kernels принадлежат пакету;
- будущие regulated verticals получают отдельные data/retention/approval
  policies, а не наследуют строительные настройки.

## 4. Что не входит в недельный релиз

Следующие пункты нельзя незаметно добавить в R1:

- публичный App Store/Google Play release;
- Tauri/WebView как мобильная оболочка;
- production-переход расчётного движка на Rust;
- offline-редактирование с двусторонним merge;
- realtime voice call;
- собственное распознавание речи без отдельного privacy/security gate;
- полный набор ФСНБ-2022, ФЕР, ТЕР, ГЭСН и региональных баз без правового
  основания на распространение;
- гарантированная подготовка XML для государственной экспертизы;
- полный импорт/экспорт `gsfx`, EstML, АРПС, KENML и форматов 1С;
- КС-2, КС-3, М-29 и управленческий учёт факта в production;
- BIM/ТИМ 5D;
- биллинг, подписка и автоматическое списание;
- маркетинговое утверждение «полная замена 1С/ГРАНД-Сметы».

Системная диктовка клавиатуры iOS/Android доступна как функция ОС. Отдельная
кнопка микрофона появляется только после реальной транскрипции, permission UX,
privacy disclosure и теста на физическом устройстве. До этого мёртвая кнопка
запрещена.

## 5. Фактический baseline на 30 июля

| Область | Статус | Доказательство / проблема |
|---|---|---|
| Текущий production `/app` | GREEN | 30.07.2026: HTTP 200; корень домена переводит на `/app`; unauthenticated shell загружается |
| Публичная release identity/readiness | RED | `/api/health` и `/v1/health` публично дают 404; `X-Kolibri-Product-Release` в текущем ответе отсутствует |
| Mobile web 320/375/390, light/dark | GREEN | ручной QA и contract tests выполнены |
| Desktop regression 1440 | GREEN | внешний вид и layout проверены |
| Web typecheck/tests/build | GREEN | typecheck, 89 тестов и production build прошли на текущем source snapshot |
| Полный backend suite | GREEN | 199 тестов прошли одним прогоном |
| Native mobile auth | GREEN, not integrated | 19 focused tests прошли, токены хранятся hash-only |
| Provider/A2A execution | GREEN | 13/13 тестов; Agent Card содержит и строго проверяет точный `runtime.profile` |
| Standard/dev routing | RED in production | 30.07.2026: standard идёт direct, developer принудительно попадает в Home outbox; 14 outbox-записей blocked и 3 developer run остались running |
| Owner control plane | YELLOW | Реализованы tenant/user/plan/dev policy/session/audit, trusted Agent Host bindings/profiles create+revoke и read-only реальные runs/runtime/queue; A2A v1.3 lease, live notifications, diff/test artifacts и deploy/rollback controls ещё не завершены |
| Trusted-agent execution binding | YELLOW | Профиль `full/danger-full-access/never` замораживается в run; revoke/epochs проверяются до Product dispatch и commit. A2A v1.2 ещё не переносит tuple внешнему Agent Host и не прерывает уже работающий процесс |
| Единственный backend authority | RED | локальная V3 работа и production script указывают на разные backend-каталоги |
| CI для `kolibri-v3` | RED | текущий GitHub workflow не запускает полный V3 gate |
| Чистый immutable release source | RED | рабочее дерево содержит незакоммиченные изменения |
| Portable smoke | YELLOW | скрипт есть, но не доказан на текущем release candidate |
| Home/Primary canary | RED | текущий candidate ещё не собран и не проверен |
| Backup restore rehearsal | RED | backup реализован, доказательства восстановления R1 нет |
| Наблюдаемость и SLO | RED | production dashboards/alerts не подтверждены |
| Expo native truth spike | YELLOW | Expo 57 scaffold создан, simulator gate ещё выполняется |

GREEN означает лишь наличие указанного доказательства. Он не переносится на
следующий candidate автоматически.

## 6. Критический путь

```text
один Product/Data Authority
  → исправленный Agent Card / A2A contract
  → полный зелёный backend suite
  → V3 CI на clean checkout
  → release candidate commit
  → immutable build + local production smoke
  → staging/canary с реальным provider
  → backup/restore + rollback rehearsal
  → mobile/desktop owner acceptance
  → production switch
  → публичный smoke и усиленный мониторинг
```

Любой красный узел останавливает следующие mutating production-шаги.

## 7. План по дням

### День 1 — четверг, 30 июля: freeze и устранение split-brain

Цель: получить один собираемый продукт и честный список блокеров.

- [ ] Зафиксировать этот R1 scope и запретить незапланированное расширение.
- [ ] Принять ADR: `kolibri-v3/backend` — единственный Product/Data Authority.
- [ ] Принять архитектуру Universal Core + Vertical Packs и валидировать
  manifest `construction.estimates`.
- [ ] Составить таблицу каждого production-процесса:
  frontend, Product API, run worker, enrollment worker, Logical Home bridge,
  Provider Execution Authority.
- [ ] Удалить из release lane скрытый fallback на `kolibri-backend`.
- [ ] Перенаправить build manifest, systemd units и smoke на один V3 backend.
- [x] Исправить регистрацию/выбор runtime Agent Card; закрыть все 13
  `test_provider_execution.py`.
- [ ] Добавить отдельный GitHub CI job для:
  V3 backend, V3 web, migration, contract и release-script tests.
- [ ] Зафиксировать текущие тестовые команды и версии Python/Node/npm.
- [ ] Создать release evidence directory и начать журнал решений.
- [ ] Собрать и протестировать Rust contract kernel; добавить его в CI как
  обязательную архитектурную проверку, но не включать в authoritative path.
- [x] Зафиксировать protocol-first device architecture и первый versioned
  capability manifest для экранных и headless устройств.

Gate D1:

- один API отвечает за identity/chat/projects/estimates;
- строительная возможность выключается capability snapshot без поломки
  универсального chat/project shell;
- полный backend suite не исключает provider execution;
- production manifest не содержит второго Product API;
- CI-конфигурация видит `kolibri-v3`.

### День 2 — пятница, 31 июля: durable chat, auth и latency

Цель: закончить ядро входа и агентного ответа.

- [x] Убрать выбор transport plane по `executionMode`; standard/dev проходят
  один adapter, а runtime/mode/model и physical plane проверяются и
  замораживаются серверной capability matrix. Browser не передаёт plane.
- [x] Добавить owner control plane для tenant/user/status/plan/limits/dev
  policy/session revoke/audit, не смешивая его с клиентским кабинетом.
- [ ] Связать каждый клиентский dev grant с отдельным tenant/user-bound
  workspace placement; запретить fallback на общий workspace владельца.
- [ ] Реализовать owner-configured trusted-agent
  `danger-full-access + approval=never` через внутренний Agent Host:
  service identity, task/persistent delegated authority, workspace/environment
  scope, authority epoch, revoke/kill switch, limits и полный durable audit.
  Durable profile, frozen epochs и revoke checks уже реализованы; task lease,
  A2A v1.3 enforcement и preemptive cancellation остаются.
- [ ] Добавить в owner control plane реестр агентов/nodes/workspaces, очередь
  задач, live status, notifications, diff/test artifacts и deploy/rollback.
  Реестр bindings/profiles и реальная read-only проекция runs/runtime/queue уже
  есть; notifications, diff/test artifacts и mutating operations остаются.
- [ ] Запретить auto developer на случайно первом connected provider:
  требуется явный или детерминированный developer-capable runtime.
- [ ] Проверить restart recovery: ни direct run, ни outbox run не остаётся
  бессрочно в `running` после рестарта процесса.
- [ ] Интегрировать native bearer contract в канонический Product API без
  изменения cookie+CSRF browser flow.
- [ ] Добавить bearer integration test для AG-UI send/resume/cancel.
- [ ] Проверить tenant isolation, logout, token rotation/replay revocation.
- [ ] Доказать, что runtime поднимается один раз при старте, а не на сообщение.
- [ ] Выполнить реальный тест простого вопроса, погоды и длинной агентной задачи.
- [ ] Измерить acknowledgement, first lifecycle event, first text и completion.
- [ ] Проверить restart во время run: запись не теряется и не дублируется.
- [ ] Устранить duplicate effects и небезопасные provider fallbacks.
- [ ] Пройти Expo truth spike: typecheck, iOS simulator, Android emulator или
  физическое устройство; решение не блокирует web R1.
- [ ] Запустить Python → normalized calculation contract → Rust shadow на
  golden fixtures; расхождения сделать видимыми, но не менять production result.

Gate D2:

- браузерный и native auth не ослабляют друг друга;
- повтор refresh token отзывает одну device family;
- warm runtime не создаёт процесс на каждый запрос;
- AG-UI восстанавливается после reconnect;
- реальный agent probe сохранён как evidence.

Цели производительности R1:

| Метрика | Gate |
|---|---:|
| p95 обычного API без AI | ≤ 500 ms |
| server acknowledgement durable run | ≤ 1 s |
| первое видимое lifecycle-событие | ≤ 2 s |
| p95 первого текста простого warm-запроса | ≤ 8 s |
| прогресс долгой агентной работы | не реже 15 s |

Если модель не успевает дать текст, интерфейс обязан показать правдивый
durable статус, а не зависший spinner.

### День 3 — суббота, 1 августа: полный пользовательский vertical slice

Цель: пройти R1 от регистрации до документа на реальных данных.

- [ ] Weather end-to-end с датой, местом и источником данных.
- [ ] Image generation end-to-end с persisted artifact, preview и download.
- [ ] Вложения: успех, неподдерживаемый тип, превышение размера, network retry.
- [ ] Смета: создать из чата, редактировать, сохранить, открыть версию.
- [ ] Version conflict: сохранить локальный draft и показать различия.
- [ ] Экспорт одной версии в PDF/XLSX/DOCX и сравнение totals/hash metadata.
- [ ] Все неподдерживаемые starter actions и controls сделать честными.
- [ ] Проверить статус/provenance цен и запретить «verified» без источника.
- [ ] Проверить возврат редактор → чат с сохранением draft и scroll.

Gate D3:

- 12-шаговый обязательный пользовательский путь проходит без ручной правки БД;
- ни одна видимая основная кнопка не является декорацией;
- три формата документа используют одну estimate version;
- предварительные данные явно обозначены.

### День 4 — воскресенье, 2 августа: production package и observability

Цель: получить воспроизводимый immutable candidate.

- [ ] Привести release lane к каноническому V3 backend.
- [ ] Установить отдельные systemd units и liveness для обязательных workers.
- [ ] Добавить readiness, который проверяет БД и обязательный runtime boundary.
- [ ] Добавить `X-Kolibri-Release` и release ID во все логи.
- [ ] Настроить structured logs без токенов, cookies, prompt secrets и PII.
- [ ] Зафиксировать latency/error/run queue metrics.
- [ ] Добавить минимальные alerts:
  public down, backend not ready, worker stopped, error-rate spike,
  stuck runs, disk/DB backup failure, TLS expiry.
- [ ] Проверить Nginx для SSE, uploads, timeouts, TLS и cellular IPv4/IPv6.
- [ ] Собрать archive из clean commit и проверить SHA-256.
- [ ] Выполнить clean local production smoke.

Gate D4:

- одна команда из clean checkout строит один immutable archive;
- secrets отсутствуют в archive и manifest;
- frontend, backend и workers имеют один release ID;
- локальный production smoke проходит без dev server;
- restart policy реально поднимает остановленный процесс.

### День 5 — понедельник, 3 августа: staging/canary и устройства

Цель: доказать продукт в окружении, максимально близком к production.

- [ ] Развернуть candidate на отдельном localhost-порту Home.
- [ ] Подключить точный Primary/bootcamp runtime только через утверждённый A2A
  identity и Agent Card.
- [ ] Выполнить end-to-end smoke через настоящий provider.
- [ ] Проверить iPhone Safari по Wi‑Fi и мобильной сети.
- [ ] Проверить Android Chrome по Wi‑Fi и мобильной сети.
- [ ] Проверить desktop Safari/Chrome на 1440 px.
- [ ] Проверить тёмную/светлую темы и системное переключение.
- [ ] Провести 10 одновременных активных чатов и 3 долгих agent runs.
- [ ] Проверить upload 1 MB, 20 MB и отказ сверх лимита.
- [ ] Зафиксировать screenshots, timings, console/server logs и release ID.
- [ ] После 12:00 МСК закрыть feature development.

Gate D5:

- публичный production ещё не изменён;
- canary проходит обязательный путь на физических телефонах;
- agent runtime/bootcamp однозначно связан с release;
- нет cross-tenant утечки, duplicate run или потерянного сообщения;
- P0 = 0, P1 имеет владельца и deadline не позднее D6.

### День 6 — вторник, 4 августа: security, migration, restore, rollback

Цель: доказать, что запуск обратим и данные защищены.

- [ ] Проверить auth, CSRF, CORS, bearer separation, cookie flags и rate limits.
- [ ] Проверить IDOR/cross-tenant для thread/project/estimate/export/artifact.
- [ ] Проверить upload content type, имя файла, размер и безопасную выдачу.
- [ ] Выполнить secret scan release archive и production env references.
- [ ] Сделать backup копии staging/production-like БД.
- [ ] Применить migration 0 → current и current-1 → current.
- [ ] Восстановить backup в отдельную БД и пройти read/write smoke.
- [ ] Выполнить canary rollback на предыдущий release.
- [ ] Проверить, что rollback кода не уничтожает уже применённые данные.
- [ ] Подготовить incident runbook и контакт владельца.
- [ ] Закрыть все P0/P1; незакрытый P1 требует явного переноса запуска.

Gate D6:

- critical/high security findings = 0;
- backup создан, восстановлен и проверен;
- rollback занимает не более 10 минут;
- audit trail фиксирует release, migration и owner decision;
- candidate не изменяется после прохождения gate.

### День 7 — среда, 5 августа: RC freeze и go/no-go

Цель: подготовить неизменяемый релиз к переключению 6 августа.

- [ ] Создать RC commit/tag и подписанный manifest.
- [ ] Запустить все gate-команды на clean checkout.
- [ ] Повторить canary из финального archive, а не из рабочего дерева.
- [ ] Провести owner acceptance:
  iPhone Safari, desktop, chat, image, weather, estimate, exports.
- [ ] Проверить DNS, TLS, disk capacity, clock, Nginx и systemd status.
- [ ] Подготовить exact switch и exact rollback команды.
- [ ] Зафиксировать go/no-go протокол.
- [ ] После approval не пересобирать archive.

Gate D7:

- CI = GREEN на RC commit;
- checksum canary равен checksum production candidate;
- P0 = 0, P1 = 0;
- owner acceptance = PASS;
- status решения: `GO`, иначе `NO-GO`.

### День запуска — четверг, 6 августа

Порядок неизменяем:

1. Подтвердить `GO` и exact archive SHA-256.
2. Создать production DB и Nginx backup.
3. Развернуть тот же archive на новых loopback-портах.
4. Применить совместимые миграции.
5. Пройти localhost health/readiness и обязательный user smoke.
6. Проверить Provider/A2A/bootcamp binding.
7. Выполнить `nginx -t`.
8. Атомарно переключить route и сделать `reload`, не `restart`.
9. Проверить `/`, `/app`, auth, chat, weather, image, estimate и export.
10. Проверить с телефона через мобильную сеть.
11. Наблюдать не менее четырёх часов в усиленном режиме.
12. Сохранить release evidence и итоговое решение.

Автоматический rollback запускается, если:

- health/readiness не восстанавливается за 3 минуты;
- auth массово недоступен;
- пользовательские сообщения теряются или дублируются;
- агентный контур не создаёт lifecycle event за 30 секунд;
- 5xx превышает 5% в течение 5 минут;
- обнаружена cross-tenant/security проблема;
- новый release портит или не читает существующие данные.

## 8. Обязательные release gates

### Backend

```bash
cd kolibri-v3
uv run --with-requirements backend/requirements-dev.txt \
  env PYTHONPATH=backend \
  python -m pytest -q backend/tests
```

Нельзя исключать `test_provider_execution.py` или помечать его известной
ошибкой: агентный runtime входит в продукт.

### Web

```bash
cd kolibri-v3
npm ci
npm run typecheck
npm test
npm run build
```

### Native truth spike

```bash
cd apps/kolibri-mobile
npm ci
npm run typecheck
npx expo-doctor
```

Дополнительно обязательны реальный launch и screenshot на iOS Simulator и
Android emulator/устройстве. Этот gate подтверждает архитектуру, но не даёт
права рекламировать store-приложение.

### Rust calculation foundation

```bash
cargo fmt --manifest-path packages/estimate-kernel-rs/Cargo.toml --check
cargo clippy --manifest-path packages/estimate-kernel-rs/Cargo.toml \
  --all-targets -- -D warnings
cargo test --manifest-path packages/estimate-kernel-rs/Cargo.toml
```

Успех этих команд означает готовую границу и conformance foundation, а не
разрешение использовать Rust result как canonical production total.

### Release

```bash
cd kolibri-v3
./deploy/portable/smoke-test.sh
```

Production-specific build-only/canary команда утверждается после D1, когда
единственный backend будет отражён в release manifest. До этого старый
`ops/release_kolibri_v3_product.sh` нельзя считать доказательством V3 R1:
сейчас он упаковывает другой backend.

## 9. QA-матрица

| Путь | Safari iPhone | Chrome Android | Desktop | API/contract |
|---|---:|---:|---:|---:|
| register/login/logout | PASS required | PASS required | PASS required | PASS required |
| create/open thread | PASS required | PASS required | PASS required | PASS required |
| stream/resume/cancel | PASS required | PASS required | PASS required | PASS required |
| weather | PASS required | PASS required | PASS required | PASS required |
| image artifact | PASS required | PASS required | PASS required | PASS required |
| attachment | PASS required | PASS required | PASS required | PASS required |
| drawer/long press/settings | PASS required | PASS required | regression | contract |
| estimate create/edit/save | PASS required | PASS required | PASS required | PASS required |
| editor → chat round-trip | PASS required | PASS required | PASS required | state test |
| PDF/XLSX/DOCX | download | download/share | download | hash/version |
| dark/light/system | PASS required | PASS required | regression | token test |
| tenant isolation | N/A | N/A | N/A | PASS required |
| restart/recovery | reconnect | reconnect | reconnect | PASS required |

## 10. Definition of Done

R1 считается готовым только при одновременном выполнении:

- один canonical Product/Data backend;
- универсальный Core и `construction.estimates` разделены capability contract;
- один clean RC commit и один immutable archive;
- все обязательные backend/web tests проходят без исключений;
- V3 CI проходит на Linux clean checkout;
- production build не содержит dev server;
- 12-шаговый пользовательский путь проходит на canary;
- физический iPhone Safari и Android Chrome проходят mobile acceptance;
- desktop regression отсутствует;
- реальный агент отвечает через точный A2A/runtime binding;
- сметные расчёты детерминированы и документы совпадают с snapshot;
- backup restore и rollback доказаны;
- critical/high security findings отсутствуют;
- health/readiness/worker liveness/alerts работают;
- P0 = 0 и P1 = 0;
- владелец дал явный `GO`.

«Код написан», «локально открылось» и «health вернул 200» не являются
Definition of Done.

## 11. Роли и ответственность

| Роль | Ответственность | Не может единолично |
|---|---|---|
| Product owner | scope, acceptance, GO/NO-GO | менять archive после approval |
| Release lead | critical path, evidence, canary, switch | скрывать failed gate |
| Product/Data backend | auth, durable chat, estimates, migrations | менять UI semantics |
| Runtime/A2A | Agent Cards, worker, provider, latency | писать Product history напрямую |
| Web/mobile | responsive UI, Safari, accessibility | считать canonical totals |
| QA/security | E2E, isolation, restore, rollback | waive P0/P1 без owner |

Один человек может исполнять несколько ролей, но evidence и запреты ролей
сохраняются.

## 12. После R1: путь к конкуренции с 1С и ГРАНД-Сметой

### 0–30 дней

- каталоги работ/ресурсов и управляемые пользовательские расценки;
- методы commercial resource и базовый resource-index preview;
- import/export XLSX/CSV и валидируемый внутренний XML;
- объектная структура, версии, сравнение, аудит и согласование;
- КС-2, КС-3 и М-29 из одного approved snapshot;
- organization/roles/permissions и журнал изменений;
- пилот с 5–10 практикующими сметчиками.

### 31–60 дней

- легальный source registry ФСНБ-2022/ФГИС ЦС и региональных данных;
- полноценные ресурсный и ресурсно-индексный методы;
- конъюнктурный анализ и коммерческие предложения;
- versioned XSD adapters и проверка XML;
- импорт/экспорт ключевых обменных форматов;
- 1С integration adapter без копирования 1С как Product Authority;
- native TestFlight/Android beta с тем же Product API.

### 61–90 дней

- shadow Rust calculation kernel на общем golden corpus;
- cutover Rust только после byte-for-byte parity и rollback flag;
- сводные/объектные сметы и сводка затрат;
- фактическое выполнение, procurement и change orders;
- BIM/ТИМ quantity takeoff pilot;
- enterprise SSO, audit export, backup policy и SLA;
- доказанный pricing/retention pilot и коммерческий запуск.

Официальная `1С:Смета` поддерживает локальные, объектные и сводные сметы,
М-29, КС-2/КС-3, разные методы расчёта, нормативные базы и форматы обмена.
`ГРАНД-Смета` поддерживает ФСНБ-2022, ресурсно-индексный расчёт, ФГИС ЦС и
XML-обмен. Поэтому конкурентная стратегия Kolibri строится не на копировании
экранов, а на обязательном профессиональном паритете плюс преимуществах:
AI-intake, прозрачном provenance, совместной облачной работе, mobile-first,
durable agents и автоматической согласованности документов.

## 13. Официальные продуктовые и нормативные ориентиры

- 1С:Смета, возможности:
  <https://solutions.1c.ru/catalog/smeta3/features>
- 1С:Смета, состав и лицензирование нормативных баз:
  <https://solutions.1c.ru/catalog/smeta3/structure>
- ГРАНД-Смета, ресурсно-индексный метод:
  <https://help.grandsmeta.ru/resursno-indeksnyj-metod>
- ГРАНД-Смета, экспорт:
  <https://help.grandsmeta.ru/ob-ekty-i-smety/eksport-smet-v-razlichnye-formaty>
- Минстрой России, ценообразование и действующие методики:
  <https://minstroyrf.gov.ru/trades/tsenoobrazovanie/>
- Главгосэкспертиза, проверка XML:
  <https://checkxml.gge.ru/>
