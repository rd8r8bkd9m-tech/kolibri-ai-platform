# Kwork Portfolio Plan: AI Bots And Business Automation

Purpose: make the Kwork profile look focused, practical and order-ready. The portfolio should sell work that Vladislav and the Kolibri execution environment can actually deliver now: AI bots, Telegram bots, mini apps, document/estimate automation, RAG assistants, API integrations and bot/code audits.

## Positioning

Main direction:

> AI-боты, Telegram-боты и приложения для бизнеса: заявки, поддержка, документы, сметы, база знаний, CRM/API и автоматизация рутинных процессов.

Short profile angle:

> Я собираю рабочие AI-боты и небольшие приложения под конкретную бизнес-задачу: от идеи и сценария до кода, тестового запуска и инструкции. Сложные проекты разбиваю на этапы, чтобы быстро получить первый результат и не переплачивать за лишнюю сложность.

## What We Can Honestly Sell Now

These are the directions that can be executed by Codex/Kolibri without pretending to be a huge agency:

1. Telegram AI bot for заявки, FAQ and lead qualification.
2. AI support bot trained on a small knowledge base or document set.
3. AI document bot: КП, акты, отчеты, summaries, estimates and structured outputs.
4. AI smeta/estimate assistant: text request -> structured estimate -> PDF/document pack.
5. Bot with simple admin panel, table export or webhook/API integration.
6. Telegram Mini App / PWA shell for bot workflows.
7. Existing bot audit, bug fixing and improvement plan.
8. AI agent prompt/role/scenario package for business support.
9. Legal parser/monitoring bot with notifications, only for allowed public/owned data.
10. MVP AI service prototype: frontend + FastAPI/backend + provider integration.

## What We Do Not Sell

- "Any AI system" without scope.
- Guaranteed sales, traffic, income or perfect AI answers.
- Spam bots, fake accounts, mass registrations, bypassing platform limits, scraping behind auth, fraud or grey monetization automation.
- Banking, tax, legal, medical or security final decisions without human review.
- 24/7 production support inside a small fixed-scope kwork.
- Work that requires secret tokens in open chat.

## Portfolio Structure

Publish 8 portfolio works. Mark internal/demo cases honestly as demo/internal, not paid client work.

### 1. Telegram AI Bot For Leads And FAQ

- Title: Telegram AI-бот для заявок и ответов клиентам
- Type: demo/internal case, reusable client pattern
- Problem: бизнесу нужно быстро отвечать клиентам, собирать заявки и передавать их менеджеру.
- Solution: Telegram bot with menu/buttons, AI answer scenario, lead form, manager handoff and launch checklist.
- Stack: Python, Telegram Bot API / Aiogram-style architecture, FastAPI/API, OpenAI-compatible provider or local model by agreement.
- Result: first working bot flow that can be tested, extended and connected to CRM/table/webhook.
- Confidentiality: no real customer chats, no tokens, no private leads.
- Related kwork: "Создам Telegram-бота с AI-ассистентом для вашего бизнеса".
- Visual: bot flow diagram, safe Telegram demo screenshot, architecture card.

Paste-ready description:

```text
Сценарий Telegram AI-бота для малого бизнеса: бот принимает обращение, задает уточняющие вопросы, отвечает по FAQ, собирает заявку и передает результат менеджеру. Такой формат подходит для услуг, ремонта, обучения, записи, консультаций и первичной поддержки.

Что показано: логика диалога, структура кнопок, AI-сценарий, передача заявки, безопасная архитектура без публикации токенов и личных данных.
```

### 2. AI Support Bot With Knowledge Base

- Title: AI-бот поддержки по базе знаний
- Type: demo/internal case
- Problem: клиентам или сотрудникам нужно быстро получать ответы из инструкций, документов and FAQ.
- Solution: RAG-style assistant: documents -> search/context -> answer with guardrails.
- Stack: Python, FastAPI, RAG pipeline, embeddings/vector search, OpenAI-compatible provider/local LLM by agreement.
- Result: prototype that answers from prepared materials and reduces manual FAQ responses.
- Confidentiality: use synthetic documents or redacted examples.
- Related kwork: "Создам AI-бота поддержки по вашей базе знаний".
- Visual: knowledge base flow, answer screen, safe architecture card.

Paste-ready description:

```text
Пример AI-бота поддержки, который отвечает не "из головы", а по подготовленной базе знаний: инструкции, FAQ, документы, регламенты или описания услуг. Подходит для внутренней поддержки, клиентских вопросов, обучения сотрудников и быстрых консультаций.

Что показано: схема загрузки документов, поиск релевантного контекста, ответ пользователю, ограничения безопасности и сценарии проверки качества.
```

### 3. AI Document And Estimate Assistant

- Title: AI-бот для документов, КП и смет
- Type: internal product/demo
- Problem: ручная подготовка смет, КП, актов and structured documents takes time and creates calculation mistakes.
- Solution: text request -> normalized structure -> deterministic totals -> PDF/document pack.
- Stack: Python, Pydantic, deterministic calculation engine, PDF generation, FastAPI.
- Result: repeatable workflow for estimates, commercial offers, acts, invoices and reports.
- Confidentiality: only synthetic estimate data.
- Related kwork: "Создам AI-ассистента для документов и смет".
- Visual candidates:
  - `/Users/kolibri/Projects/smeta/smeta_mockups_v1 2/01_desktop_estimate.png`
  - `/Users/kolibri/Projects/smetaminiapp/tmp/pdfs/estimate-live-page1.png`

Paste-ready description:

```text
AI-сценарий для документов и смет: из текстового описания формируется структура работ, суммы пересчитываются детерминированно, затем можно подготовить PDF, КП, акт или отчет. Это не заменяет профессиональную проверку, но сильно ускоряет первичную подготовку документов.

Что показано: экран сметы, таблица работ, итоговая сумма, логика пересчета и безопасные тестовые данные.
```

### 4. Bot + CRM/API/Webhook Integration

- Title: AI-бот с передачей заявок в CRM, таблицу или webhook
- Type: reusable architecture case
- Problem: заявки из бота теряются in chat and are not routed into a business system.
- Solution: bot collects data, validates it, sends structured payload to CRM/table/webhook and notifies manager.
- Stack: Python/TypeScript, API, webhooks, FastAPI, Telegram Bot API.
- Result: clear request pipeline from user message to business action.
- Confidentiality: no real API keys, redacted payload examples only.
- Related kwork: "Сделаю интеграцию бота с API, CRM или таблицей".
- Visual: redacted payload flow, integration diagram.

Paste-ready description:

```text
Кейс интеграции AI-бота с рабочим процессом: бот собирает заявку, проверяет обязательные поля, передает данные в таблицу/CRM/webhook и уведомляет менеджера. Это помогает не терять обращения и быстрее запускать обработку заявок.

Что показано: схема "бот -> проверка -> webhook/API -> менеджер", пример безопасного payload без токенов и персональных данных.
```

### 5. Telegram Mini App / PWA Around A Bot

- Title: Мини-приложение для бота: форма, кабинет, заявки
- Type: app UI/product case
- Problem: some bot flows need richer UI than chat: forms, cards, catalog, booking, statuses.
- Solution: responsive mini app/PWA connected to bot or backend.
- Stack: React, Vite, PWA, FastAPI/API, Telegram Mini App-compatible flow by agreement.
- Result: buyer can inspect a real app-like experience instead of only chat messages.
- Confidentiality: no private customer data.
- Related kwork: "Сделаю Telegram Mini App или PWA для вашего бота".
- Visual candidates:
  - `/Users/kolibri/motor-doctor/design/mockups/start-screens.png`
  - `/Users/kolibri/Projects/smeta/smeta_mockups_v1 2/02_mobile_estimate.png`

Paste-ready description:

```text
Пример мини-приложения вокруг бизнес-бота: удобный экран для заявок, статусов, услуг или личного кабинета. Такой подход подходит, когда обычного чата мало и пользователю нужна форма, карточки, история или быстрые действия.

Что показано: mobile-first интерфейс, сценарий заявки, адаптивная структура и возможность связать UI с ботом/API.
```

### 6. Existing Bot Audit And Repair Plan

- Title: Аудит и доработка существующего Telegram/AI-бота
- Type: service proof case
- Problem: bot exists but answers poorly, breaks, has unclear logic or no handoff.
- Solution: inspect flow, code/config assumptions, risks, quick fixes and next delivery plan.
- Stack: Python/JS review, API checks, prompt/scenario review, safety checklist.
- Result: buyer gets an understandable report and can order targeted fixes.
- Confidentiality: no private source snippets in public portfolio.
- Related kwork: "Проверю и улучшу Telegram/AI-бота".
- Visual: anonymized audit report cover.

Paste-ready description:

```text
Кейс аудита существующего бота: проверка сценария, качества ответов, ошибок логики, интеграций и рисков. На выходе покупатель получает понятный список проблем, быстрых исправлений и следующий безопасный этап работ.

Что показано: структура отчета, чек-лист проверки, приоритизация исправлений без публикации приватного кода.
```

### 7. Internal AI Agent / Business Assistant

- Title: AI-агент для внутренних задач бизнеса
- Type: internal factory pattern
- Problem: routine tasks require context, rules, role and repeatable execution.
- Solution: agent role, constraints, prompts, task queue, status/reporting loop.
- Stack: AI prompts, Python/FastAPI, task envelope, GitHub/docs workflow, optional Control Plane-style routing.
- Result: repeatable AI worker that can handle bounded tasks with reports.
- Confidentiality: no secrets, no internal keys, no private node details.
- Related kwork: "Настрою AI-агента под вашу бизнес-задачу".
- Visual: agent workflow card.

Paste-ready description:

```text
Пример внутреннего AI-агента: фиксируем роль, правила, разрешенные действия, входные данные, формат результата и проверку качества. Такой агент помогает готовить документы, анализировать заявки, сортировать задачи или поддерживать команду.

Что показано: role prompt, workflow, ограничения, формат отчета и безопасный цикл проверки результата.
```

### 8. AI Bot MVP: Frontend + Backend + Provider

- Title: MVP AI-сервиса: чат, backend и подключение модели
- Type: product prototype case
- Problem: idea is too large to build all at once, but a testable MVP is needed.
- Solution: small chat/app prototype with provider integration, backend endpoint and deploy/run instructions.
- Stack: React, FastAPI, WebSocket/HTTP, provider API, GitHub workflow.
- Result: first clickable AI service prototype for validation.
- Confidentiality: no provider keys, no private data.
- Related kwork: "Подготовлю MVP AI-бота или AI-сервиса".
- Visual candidates:
  - `/Users/kolibri/Projects/kolibri-project/output/playwright/desktop-chat.png`
  - `/Users/kolibri/Projects/kolibri-project/output/playwright/mobile-chat.png`

Paste-ready description:

```text
MVP AI-сервиса: интерфейс чата, backend endpoint, подключение AI-провайдера и базовая проверка сценария. Формат подходит для проверки идеи до большого бюджета: сначала делаем рабочий прототип, затем отдельно планируем развитие.

Что показано: чат-интерфейс, backend/API, provider flow, адаптивные экраны и безопасный запуск без публикации ключей.
```

## First 5 Portfolio Items To Publish

Priority order for Kwork:

1. Telegram AI-бот для заявок и ответов клиентам.
2. AI-бот для документов, КП и смет.
3. AI-бот поддержки по базе знаний.
4. Мини-приложение для бота: форма, кабинет, заявки.
5. Аудит и доработка существующего Telegram/AI-бота.

These five create a focused story: "I build useful AI bots and the small apps around them."

Ready-to-upload copy and generated safe covers are in `KWORK_PORTFOLIO_READY_TO_UPLOAD.md` and `portfolio-assets/`.

## Asset Checklist

Use only assets that are safe and redacted:

- existing screenshots with synthetic/test data;
- UI mockups without private clients;
- generated architecture cards;
- redacted workflow diagrams;
- no tokens, no API keys, no private chats, no payment screens.

Candidate local assets:

- `/Users/kolibri/Projects/smeta/smeta_mockups_v1 2/01_desktop_estimate.png`
- `/Users/kolibri/Projects/smeta/smeta_mockups_v1 2/02_mobile_estimate.png`
- `/Users/kolibri/Projects/smetaminiapp/tmp/pdfs/estimate-live-page1.png`
- `/Users/kolibri/motor-doctor/design/mockups/start-screens.png`
- `/Users/kolibri/Projects/kolibri-project/output/playwright/desktop-chat.png`
- `/Users/kolibri/Projects/kolibri-project/output/playwright/mobile-chat.png`
- `/Users/kolibri/Projects/kolibri-project/output/playwright/desktop-tasks.png`
- `/Users/kolibri/Projects/kolibri-project/output/playwright/desktop-knowledge.png`

## Kwork Upload Rule

Do not upload or save anything publicly until owner confirms the exact public action. Drafting, preparing text, organizing screenshots and filling a not-submitted draft is allowed. Public save/publish/send requires action-time confirmation.
