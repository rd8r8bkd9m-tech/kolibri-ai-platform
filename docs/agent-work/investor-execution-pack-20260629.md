# Исполнимый investor/client package Kolibri

Дата: 2026-06-29
Роль: `investor_executive_operator`
Статус: исполнимый пакет для ручного outreach, discovery и подготовки
evidence. Пакет не отправляет сообщения, не создаёт контакты и не запускает
Control Plane tasks.

## 0. Граница честности

Этот материал можно использовать для первого разговора с инвестором или
ранним клиентом только в честной рамке:

- не заявлять traction, MRR, ARR, клиентов, выручку, valuation или terms, если
  они не подтверждены отдельными артефактами владельца;
- не обещать production-ready billing: T-Банк контур имеет кодовый путь и
  тестовый контракт, но требует sandbox/live проверки, публичного HTTPS
  `NotificationURL`, `RebillId`, `Charge` и решения по онлайн-кассе;
- не заявлять, что FormulaLM уже доказал превосходство над LLM. FormulaLM
  остаётся R&D до remote benchmark artifacts;
- не продавать release-ready статус всего продукта: локальный release report
  от 2026-06-29 фиксирует `NO-GO` как единый релизный статус, при этом
  отдельные P0-части уже имеют локальные доказательства;
- не раскрывать секреты, приватные URL, токены, node-local paths, сырые логи и
  персональные данные клиентов.

Основные repo-источники: `README.md`, `docs/investors.md`,
`docs/factory.md`, `docs/formulalm.md`,
`docs/agent-work/product-qa-pack.md`,
`docs/agent-work/formulalm-remote-rd-pack.md`,
`docs/agent-work/tbank-billing-ops.md`,
`docs/agent-work/release-status-20260629.md`,
`backend/billing.py`, `backend/tests/test_billing.py`,
`backend/tests/test_estimate_document_pdf_engines.py`.

## 1. One-pager для инвестора

### Kolibri AI Platform

Kolibri AI Platform — русскоязычная AI-платформа и фабрика автономных агентов.
Проект объединяет пользовательскую SPA/PWA, backend, Control Plane для
удалённых серверов, агентную фабрику, детерминированный сметный движок,
платёжный контур T-Банк и R&D-направление FormulaLM.

Первый коммерческий wedge — строительные сметы и связанные документы:
коммерческие предложения, договоры, акты, счета и PDF-пакеты. В этой области
ценность не в "магическом тексте", а в повторяемом расчёте, audit trail,
human QA и понятной подписочной модели.

### Проблема

Многие AI-продукты остаются чатом поверх модели. Для бизнеса этого мало:
нужны задачи, статусы, артефакты, воспроизводимые расчёты, billing и понятный
путь от демо к рабочему процессу.

В строительных сметах ошибка в объёме, цене, формуле или региональном
коэффициенте быстро становится коммерческим риском. Клиенту и подрядчику
нужно понимать, откуда взялась сумма, что входит в работу и какие допущения
сделаны.

### Решение

Kolibri строит agent runtime, а не только интерфейс:

- SPA/PWA с chat-first UX и Control entrypoint;
- Control Plane, где задачи входят через task envelopes и выдаются агентам
  через leases;
- backend для смет, документов, billing и API;
- deterministic estimate engine, где LLM может помогать с разбором текста, но
  цены и итоги пересчитываются кодом;
- inter-agent feed и GitHub-контур для проверяемых отчётов, PR, CI и
  артефактов;
- FormulaLM как R&D-направление для проверки гипотез о формульном слое поверх
  LLM.

### Что уже подтверждено в репозитории

- Репозиторий содержит `backend`, `frontend`, `ops`, `docs`, `scripts` и
  `.github` слои.
- Billing-код содержит тарифы Solo, Team, Studio: 4 900 ₽, 14 900 ₽ и
  39 900 ₽ в месяц по умолчанию, с env override в копейках.
- Billing unit tests покрывают T-Банк token rules, fallback lead без создания
  active subscription, recurrent `OperationInitiatorType`, safety checks,
  idempotency и recurring order mapping.
- Estimate/PDF tests покрывают deterministic recalculation, prompt estimate,
  golden case `100 м2 штукатурки в Татарстане`, document pack и PDF с
  кириллицей.
- Golden case в тесте стабилен: `EST-A1B5B0B498`, регион
  `Республика Татарстан`, pricebook `kolibri-ru-2026q2-v1`, labor
  `106500.00`, materials `44000.00`, grand total `161035.00`.
- Factory docs описывают remote-first Control Plane: задачи через Control
  Plane, leases, node-local worktrees/artifacts, inter-agent feed и GitHub как
  внешний след.
- FormulaLM docs задают remote-only protocol, гипотезы H1-H5, метрики,
  dataset seed, blocker policy и benchmark envelope.

### Что ещё не закрыто

- Полный продуктовый release пока нельзя называть готовым: release status от
  2026-06-29 фиксирует `NO-GO` до закрытия CI/live QA/server-kfrm/billing
  sandbox/PWA evidence и других блокеров.
- Billing нельзя продавать как production-ready до внешнего T-Банк sandbox
  proof и фискального решения.
- Claim 98-99% по сметам нельзя использовать как доказанный product metric без
  frozen dataset, benchmark, full API/manifest contract и независимого QA.
- FormulaLM нельзя использовать как доказанный moat до воспроизводимых remote
  benchmark artifacts.

### Для кого первый продукт

Первые клиенты: малые и средние подрядчики, ремонтные команды, отделы продаж
строительных компаний, проектные и дизайн-бюро, которым регулярно нужны
сметы, КП, договоры, акты, счета и PDF.

Первые инвесторы: AI-native, B2B SaaS, Vertical AI, ConstructionTech/PropTech,
developer tools/AI infrastructure и operator-angels, которым понятен переход
от AI demo к проверяемому workflow.

### Ask

Investor ask: 30 минут discovery call. Цель — проверить thesis, показать
текущий evidence pack и согласовать, какие метрики нужны для следующего
разговора.

Customer ask: 20 минут demo call на одном реальном обезличенном сценарии
сметы. Цель — проверить, экономит ли Kolibri время подготовки черновика сметы
и пакета документов при обязательном human review.

## 2. 20 целевых категорий клиентов и инвесторов

| # | Категория | Приоритет | Почему релевантно | Первый контакт | Что отправлять первым |
| ---: | --- | --- | --- | --- | --- |
| 1 | Малые и средние ремонтные подрядчики | P0 | Часто готовят сметы, КП и счета; покупатель близко к боли | Тёплое intro, Telegram/WhatsApp после ручной проверки, профильные чаты без спама | RU customer note + ask на обезличенный demo case |
| 2 | Строительные компании с отделом продаж | P0 | Нужно стандартизировать КП и разгрузить сметчика | Intro через владельца, коммерческого директора или sales lead | RU one-pager + demo на одном типовом объекте |
| 3 | Сметчики-фрилансеры и небольшие сметные бюро | P0 | Ценят скорость черновика, структуру строк и audit | Профильные сообщества, личная рекомендация, ручной email | Короткое сообщение + golden-case evidence |
| 4 | Дизайн- и проектные бюро | P0 | Часто готовят первичные предложения и документы | Instagram/Telegram/сайт после ручной проверки канала | RU message for bureau + sample document pack |
| 5 | Fit-out и отделочные команды B2B | P0 | Повторяемые коммерческие помещения, важны сроки и пакет документов | LinkedIn/сайт/intro к руководителю проектов | Customer one-pager + pilot scope |
| 6 | Отделы продаж строительных материалов с услугами | P1 | Смета может помогать продавать материалы и монтаж | Партнёрский intro, коммерческий email | Strategic partner note + no-integration pilot |
| 7 | Маркетплейсы ремонта и строительных услуг | P1 | Им нужен быстрый document workflow для лидов и подрядчиков | BD intro, публичная партнёрская форма | Strategic note + API-ready boundary |
| 8 | Региональные строительные франшизы | P1 | Нужен единый формат расчётов и документов по филиалам | Intro через управляющую компанию | Team/Studio pilot note |
| 9 | Проектные менеджеры ремонтных студий | P1 | Часто собирают черновики для клиента между Excel/Word/PDF | Личный email/Telegram после проверки источника | Demo ask на 1 сценарий |
| 10 | Интеграторы SMB/CRM/документооборота | P1 | Могут встроить AI-document workflow в существующие процессы | Партнёрский outreach по сайту или событию | Integration boundary + Studio pilot |
| 11 | AI-native венчурные фонды | P0 | Понимают agentic systems, infra, runtime и automation | Тёплое intro, fund form, event follow-up | Investor one-pager + evidence table |
| 12 | B2B SaaS фонды | P0 | Оценивают подписки, ICP, retention, CAC/LTV | Тёплое intro или партнёр фонда | Investor one-pager + pricing/billing caveats |
| 13 | Vertical AI инвесторы | P0 | Wedge в сметах и документах понятен как vertical workflow | Intro через portfolio/operator network | One-pager + customer discovery plan |
| 14 | ConstructionTech/PropTech фонды | P0 | Рынок смет, ремонта и проектирования входит в thesis | Fund form, warm intro, отраслевые мероприятия | Construction wedge note |
| 15 | Devtools/AI infrastructure инвесторы | P1 | Control Plane, agents, leases, artifacts, GitHub trace | Warm intro, technical partner email | Runtime thesis + factory docs |
| 16 | Fintech/банки для SMB | P1 | Подписки, счета, SMB-подрядчики и партнёрский канал | BD intro, sandbox partnership route | Strategic note + billing caveats |
| 17 | Marketplace/ecosystem strategics | P1 | Могут дать канал к подрядчикам и спрос на документы | Партнёрская форма или тёплый BD intro | Marketplace pilot note |
| 18 | Angel/operators в AI, infra, devtools | P1 | Могут дать быстрый feedback, интро и первые пилоты | Личное intro, event follow-up | 8-line investor intro |
| 19 | Corporate venture строительных/материальных групп | P2 | Длинный цикл, но возможен стратегический интерес | Только через warm intro или официальный канал | Strategic one-pager, без enterprise promise |
| 20 | Акселераторы B2B/AI/PropTech | P2 | Полезны для customer discovery и investor access | Официальная заявка, alumni intro | One-pager + blocker-aware roadmap |

Правило: в CRM нельзя вносить персональное имя, email, LinkedIn или телефон,
если источник не проверен. Для каждой записи сначала фиксируется категория,
публичный источник, thesis fit, причина контакта и compliance status:
`not_checked`, `ok_to_contact`, `needs_consent`, `do_not_contact` или
`counsel_review`.

## 3. 5 готовых русских outreach-сообщений

### 3.1 Инвестор: agent runtime + vertical wedge

Тема A: Kolibri AI: agent runtime с первым wedge в строительных сметах
Тема B: Вопрос по agentic AI и vertical workflow

Здравствуйте, {first_name}.

Я строю Kolibri AI Platform: русскоязычную AI-платформу и фабрику автономных
агентов. Первый коммерческий wedge — строительные сметы и документы, где
важны повторяемость расчёта, audit trail и human review.

Сейчас у проекта есть repo-evidence по backend/frontend/ops слоям,
детерминированному golden case для сметы, PDF/document pack, T-Банк billing
контракту и Control Plane для удалённых agent tasks. Я отдельно держу честную
рамку: FormulaLM пока R&D, а весь продукт не называю release-ready до закрытия
live QA, billing sandbox и других блокеров.

Будет ли уместен 30-минутный discovery call, чтобы проверить thesis и понять,
какие метрики вам нужны для следующего разговора?

С уважением,
{sender_name}

Если это неактуально, ответьте "не писать", и я не буду продолжать переписку.

### 3.2 Ранний клиент: подрядчик или ремонтная команда

Тема A: Быстрый черновик сметы и документов для подрядчика
Тема B: Проверить AI-сметчика на одном вашем сценарии

Здравствуйте, {first_name}.

Мы готовим Kolibri AI Platform для строительных смет, КП, договоров, актов,
счетов и PDF-пакетов. Идея не в том, чтобы заменить сметчика, а в том, чтобы
быстрее собрать проверяемый черновик: строки, объёмы, материалы, итог,
допущения и audit trail.

Предлагаю короткий demo call на 20 минут: вы даёте один обезличенный пример
сметы или типовой запрос, а мы показываем, где Kolibri может сэкономить время
и где всё равно нужен human review.

Готовы проверить на одном сценарии на следующей неделе?

{sender_name}

### 3.3 Дизайн/проектное бюро

Тема A: Единый формат сметы и КП для проектного бюро
Тема B: AI-черновик КП без обещания "автопилота"

Здравствуйте, {first_name}.

Колибри помогает готовить черновик сметы и пакета документов для ремонта:
смета, КП, договор, акт, счёт и PDF. Для бюро это может быть полезно на
первичных запросах, когда нужно быстро дать клиенту аккуратный и объяснимый
первый расчёт.

Мы не продаём это как полностью автономную отправку клиенту. Правильный режим
на старте: Kolibri собирает структуру и расчёт, человек проверяет допущения,
цены и финальную формулировку.

Можно показать 20-минутное демо на одном типовом сценарии бюро?

{sender_name}

### 3.4 Стратегический партнёр: банк, маркетплейс, интегратор

Тема A: Kolibri AI для сметного и документного workflow подрядчиков
Тема B: Партнёрский pilot вокруг AI-смет и документов

Здравствуйте, {first_name}.

Kolibri AI Platform строит проверяемый workflow для подрядчиков и ремонтных
команд: сметы, КП, договоры, акты, счета, PDF и подписочный billing path.
Технически это не только чат, а Control Plane и агентная фабрика, где задачи
имеют статусы, артефакты и проверяемый след.

Для партнёра это может быть модулем вокруг SMB-подрядчиков, лидов или
документного процесса. На первом шаге я бы не обещал enterprise-интеграцию или
production SLA; корректный формат — ограниченный pilot с одним-двумя
сценариями и явными acceptance criteria.

Кому у вас лучше направить короткую записку для обсуждения pilot fit?

{sender_name}

### 3.5 Follow-up после первого касания

Тема: Re: Kolibri AI

Здравствуйте, {first_name}.

Коротко подниму письмо один раз, чтобы не шуметь. Kolibri может быть
релевантен, если вам интересны agentic AI workflows, vertical AI в строительных
документах или проверяемая автоматизация смет.

Мой текущий ask простой: 20-30 минут discovery, без инвестиционных условий и
без обещаний неподтверждённых метрик. Если тема не в фокусе, я закрою контакт
как no-fit.

Спасибо,
{sender_name}

## 4. Что уже доказано / что пока R&D / блокеры

| Область | Что уже доказано или зафиксировано | Что пока R&D / не доказано | Блокеры перед сильным claim |
| --- | --- | --- | --- |
| Repo/архитектура | Есть backend/frontend/ops/docs структура; README описывает SPA/PWA, Control Plane, agent factory, estimates, T-Банк, FormulaLM R&D | Полная production operating system ещё не доказана внешним customer usage | Release report фиксирует `NO-GO` для единого релиза |
| Детерминированные сметы | Тесты проверяют stable golden case `100 м2 штукатурки в Татарстане`, audit fingerprint и пересчёт totals кодом | Широкая точность 98-99% по рынку не доказана | Нужны frozen dataset, pricebook manifest hash, API contract, independent QA |
| Документы/PDF | Тесты проверяют document pack: КП, договор, акт, счёт; PDF начинается с `%PDF` и поддерживает кириллицу | Юридическая пригодность шаблонов не доказана | Нужен legal/template review и визуальная QA выборки PDF |
| Billing/T-Банк | Код содержит Solo/Team/Studio планы, fallback lead, token verification, notifications, charge-due; unit tests покрывают safety cases | Production billing не доказан | Нужны test terminal credentials, public HTTPS NotificationURL, sandbox Init/notification/Charge/RebillId и фискализация |
| SPA/PWA | В docs зафиксированы локальные build/mobile-layout checks; app имеет chat-first и Control surface как продуктовую цель | Live browser/PWA readiness не закрыт | Нужны screenshots, install/offline evidence, console/network pass |
| Control Plane/factory | Docs и envelopes фиксируют remote-first model: `/v1/tasks`, leases, node-local artifacts, inter-agent feed | 80% utilization и heavy workloads не доказаны как стабильный live режим | Есть stale/queued блокеры по release report, нужен fresh node/probe evidence |
| GitHub/CI контур | Проект использует PR/CI/GitHub Project как операционный след; release report содержит PR #46 context | Нельзя считать текущий PR release-ready по старому срезу | Нужен актуальный зелёный CI и review handoff |
| FormulaLM | Сформулированы гипотезы H1-H5, метрики, dataset seed, remote-only benchmark protocol и envelope | Улучшение над baseline не доказано | Нужны remote Linux preflight, одинаковая модель/runtime/settings, JSON/MD artifacts |
| GoMesh/mobile layer | Документация описывает PWA-first и GoMesh boundary | Владение/готовность GoMesh-кода не заявляется | Нужен handoff/контракт и feature flag evidence |
| Клиенты/traction | Подготовлены ICP, outreach, pipeline и pricing | Платящие клиенты, retention, CAC/LTV, MRR/ARR не подтверждены в repo | Нужны ручные discovery calls, CRM evidence и подписанные пилоты |

## 5. FormulaLM: разрешённая формулировка

Короткая формулировка для инвестора:

> FormulaLM в Kolibri — это R&D-направление: проверяем формульный
> детерминированный слой поверх LLM для задач, где важны валидный JSON,
> точные итоги, стабильность ответа и воспроизводимость. Пока нет remote
> benchmark artifacts, мы не заявляем, что FormulaLM лучше LLM или является
> доказанным moat.

Расширенная формулировка для технического разговора:

FormulaLM не меняет веса базовой модели в первом эксперименте. Baseline и
FormulaLM должны использовать одну и ту же remote модель, один dataset, один
runtime и одинаковые generation settings. Разница только в режиме: baseline
пытается вернуть итог напрямую, а FormulaLM-режим извлекает переменные и
передаёт расчёт deterministic kernel.

Что можно говорить до benchmark:

- "У нас есть R&D protocol, dataset seed, метрики и remote-only envelope".
- "Мы проверяем `valid_json_rate`, `exact_total_rate`,
  `formula_consistency_rate`, `unique_output_hashes`,
  `manual_fix_count` и blocker categories".
- "Если remote runtime, модель или dataset недоступны, результат должен быть
  blocker artifact, а не нарисованная победа".

Что нельзя говорить до benchmark artifacts:

- "FormulaLM уже лучше LLM".
- "FormulaLM доказал 98-99% accuracy".
- "FormulaLM является production-ready моделью".
- "Benchmark можно запустить на Mac".

## 6. Machine next actions для Control Plane

Ниже task envelopes, которые можно отправить через Control Plane после ручной
проверки владельцем. В рамках этого пакета они не отправлены.

### 6.1 Проверить категории и собрать CRM seed без персональных догадок

```json
{
  "task_id": "KOL-INVESTOR-CLIENT-CATEGORY-VERIFY-20260629",
  "idempotency_key": "investor-client-category-verify:2026-06-29",
  "kind": "generic_implementation",
  "required_capability": "generic_implementation",
  "runner": "codex",
  "target_node": "main",
  "base_ref": "origin/main",
  "branch": "agent/KOL-INVESTOR-CLIENT-CATEGORY-VERIFY-20260629/research",
  "goal": "Prepare a Russian CRM seed report for the 20 target categories in docs/agent-work/investor-execution-pack-20260629.md. Do not invent personal contacts, emails, LinkedIn URLs or phone numbers. For each category, list 5-10 organization-level candidates only when a public source exists, include source URL, thesis fit, first-contact route and compliance status. Do not send outreach.",
  "role_slot": "investor_sales_operator",
  "acceptance": [
    "Creates docs/agent-work/investor-client-category-verify-20260629.md",
    "No invented people, emails, phones or private data",
    "Every organization candidate has a public source URL",
    "Each row has category, priority, thesis fit, first-contact route and compliance status",
    "Includes a blocker section for categories where source evidence is insufficient"
  ],
  "verification_commands": [
    "git diff --check -- docs/agent-work/investor-client-category-verify-20260629.md"
  ],
  "source": {
    "kind": "manual_control_plane_candidate",
    "prepared_from": "docs/agent-work/investor-execution-pack-20260629.md",
    "rule": "research only; no outreach; no secret printing"
  },
  "max_retries": 1
}
```

### 6.2 Подготовить клиентский demo pack на golden-case смете

```json
{
  "task_id": "KOL-FIRST-CUSTOMER-DEMO-PACK-20260629",
  "idempotency_key": "first-customer-demo-pack:2026-06-29",
  "kind": "generic_implementation",
  "required_capability": "generic_implementation",
  "runner": "codex",
  "target_node": "main",
  "base_ref": "origin/main",
  "branch": "agent/KOL-FIRST-CUSTOMER-DEMO-PACK-20260629/demo-pack",
  "goal": "Create a customer-safe Russian demo pack for the deterministic estimate golden case. Use only repository tests and generated/sanitized artifacts. Do not use real customer data. Do not claim legal or production accuracy. Show input, deterministic estimate fields, totals, audit/fingerprint explanation, document pack list, human QA caveats and next pilot ask.",
  "role_slot": "qa_lead",
  "acceptance": [
    "Creates docs/agent-work/first-customer-demo-pack-20260629.md",
    "References the golden case 100 м2 штукатурки в Татарстане with current tested fields",
    "States human QA and draft limitations clearly",
    "Includes commands/checks run or a blocker if the local test environment is unavailable",
    "Does not include personal data or secrets"
  ],
  "verification_commands": [
    "PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q backend/tests/test_estimate_document_pdf_engines.py",
    "git diff --check -- docs/agent-work/first-customer-demo-pack-20260629.md"
  ],
  "source": {
    "kind": "manual_control_plane_candidate",
    "prepared_from": "docs/agent-work/investor-execution-pack-20260629.md",
    "rule": "docs/artifact only; no external sending"
  },
  "max_retries": 1
}
```

### 6.3 Закрыть T-Банк readiness checklist без боевого платежа

```json
{
  "task_id": "KOL-TBANK-READINESS-CHECKLIST-20260629",
  "idempotency_key": "tbank-readiness-checklist:2026-06-29",
  "kind": "generic_implementation",
  "required_capability": "generic_implementation",
  "runner": "codex",
  "target_node": "main",
  "base_ref": "origin/main",
  "branch": "agent/KOL-TBANK-READINESS-CHECKLIST-20260629/readiness",
  "goal": "Prepare a Russian billing readiness checklist from docs/agent-work/tbank-billing-ops.md and backend/tests/test_billing.py. Do not print secrets and do not perform real payments. Produce a go/no-go table for fallback lead, sandbox checkout, signed notification, RebillId, Charge, admin token, fiscalization and owner legal texts.",
  "role_slot": "billing_tbank_operator",
  "acceptance": [
    "Creates docs/agent-work/tbank-readiness-checklist-20260629.md",
    "Separates code-level tests from external T-Банк sandbox blockers",
    "Documents exact evidence required before production claim",
    "Does not call real T-Банк APIs unless sandbox credentials and owner approval are explicitly present in task context",
    "Does not print TBANK_PASSWORD, admin token or customer personal data"
  ],
  "verification_commands": [
    "PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q backend/tests/test_billing.py",
    "git diff --check -- docs/agent-work/tbank-readiness-checklist-20260629.md"
  ],
  "source": {
    "kind": "manual_control_plane_candidate",
    "prepared_from": "docs/agent-work/investor-execution-pack-20260629.md",
    "rule": "no secret printing; no real payment without explicit owner approval"
  },
  "max_retries": 1
}
```

### 6.4 Проверить FormulaLM gate, не запускать benchmark до fresh remote proof

```json
{
  "task_id": "KOL-FORMULALM-BENCH-GATE-20260629",
  "idempotency_key": "formulalm-bench-gate:2026-06-29",
  "kind": "generic_implementation",
  "required_capability": "generic_implementation",
  "runner": "codex",
  "target_node": "main",
  "base_ref": "origin/main",
  "branch": "agent/KOL-FORMULALM-BENCH-GATE-20260629/gate",
  "goal": "Review whether ops/envelopes/KOL-FORMULALM-REMOTE-BENCH-6H-20260629.json is safe to submit. Do not submit it. Do not run FormulaLM, Qwen, LLM or model benchmarks on Mac. Check docs/formulalm.md, docs/agent-work/formulalm-remote-rd-pack.md, release blockers, target node freshness requirements and required artifacts. Return a go/no-go gate report.",
  "role_slot": "formulalm_researcher",
  "acceptance": [
    "Creates docs/agent-work/formulalm-bench-gate-20260629.md",
    "Explicitly states submit or do-not-submit recommendation",
    "Requires remote Linux preflight before any benchmark",
    "Requires same model/runtime/settings for baseline and FormulaLM",
    "Lists blockers instead of inventing benchmark results"
  ],
  "verification_commands": [
    "python3 -m json.tool ops/envelopes/KOL-FORMULALM-REMOTE-BENCH-6H-20260629.json >/dev/null",
    "git diff --check -- docs/agent-work/formulalm-bench-gate-20260629.md"
  ],
  "source": {
    "kind": "manual_control_plane_candidate",
    "prepared_from": "docs/agent-work/investor-execution-pack-20260629.md",
    "rule": "gate only; no benchmark submission; Mac is control/editing surface"
  },
  "max_retries": 1
}
```

### 6.5 Сформировать data-room index только из проверенных артефактов

```json
{
  "task_id": "KOL-INVESTOR-DATA-ROOM-INDEX-20260629",
  "idempotency_key": "investor-data-room-index:2026-06-29",
  "kind": "generic_implementation",
  "required_capability": "generic_implementation",
  "runner": "codex",
  "target_node": "main",
  "base_ref": "origin/main",
  "branch": "agent/KOL-INVESTOR-DATA-ROOM-INDEX-20260629/data-room",
  "goal": "Create a Russian investor data-room index from existing repository artifacts only. Include document title, purpose, readiness status, allowed audience, claim boundary and blockers. Do not include secrets, private logs, raw customer data or unverified traction. Do not send materials externally.",
  "role_slot": "investor_sales_operator",
  "acceptance": [
    "Creates docs/agent-work/investor-data-room-index-20260629.md",
    "Every listed artifact exists in the repository",
    "Each artifact has readiness status and claim boundary",
    "Separates sendable, internal-only and blocked materials",
    "No secrets, private paths or personal data are printed"
  ],
  "verification_commands": [
    "git diff --check -- docs/agent-work/investor-data-room-index-20260629.md"
  ],
  "source": {
    "kind": "manual_control_plane_candidate",
    "prepared_from": "docs/agent-work/investor-execution-pack-20260629.md",
    "rule": "index only; no external sending"
  },
  "max_retries": 1
}
```

## 7. Ручной порядок исполнения на неделю

1. Подтвердить с владельцем, какие категории из раздела 2 можно исследовать
   первыми: рекомендуемый старт — 5 P0 client categories и 5 P0 investor
   categories.
2. Запустить research task из 6.1 или выполнить вручную, но не генерировать
   персональные контакты без источников.
3. Подготовить demo pack из 6.2 и data-room index из 6.5.
4. Для billing использовать только fallback lead или sandbox path до закрытия
   T-Банк readiness checklist.
5. FormulaLM держать в R&D: сначала gate report, затем remote benchmark только
   после fresh Linux node proof и owner approval.
6. После первых discovery calls обновить evidence: objections, requested
   metrics, no-fit reasons, pilot criteria и список материалов, которые можно
   отправлять без раскрытия секретов.
