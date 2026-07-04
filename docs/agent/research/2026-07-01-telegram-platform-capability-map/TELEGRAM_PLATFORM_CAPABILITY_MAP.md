# Telegram Platform Capability Map For Kolibri Factory

Дата: 2026-07-01
Проверено по официальной документации: 2026-07-01.

Назначение: зафиксировать, какие возможности Telegram нужно использовать для
Kolibri Factory Bot и Mini App, чтобы бот стал полноценным командным пультом
фабрики, а не набором случайных команд.

Полный официальный разбор возможностей Telegram вынесен в:
`TELEGRAM_OFFICIAL_FULL_STUDY.md`.

## Источники

- https://telegram.org/
- https://core.telegram.org/
- https://core.telegram.org/bots
- https://core.telegram.org/bots/features
- https://core.telegram.org/bots/api
- https://core.telegram.org/bots/api-changelog
- https://core.telegram.org/bots/webhooks
- https://core.telegram.org/bots/webapps
- https://core.telegram.org/bots/payments
- https://core.telegram.org/bots/payments-stars
- https://core.telegram.org/bots/telegram-login
- https://core.telegram.org/api/business
- https://core.telegram.org/gateway/api
- https://core.telegram.org/tdlib/docs/
- https://core.telegram.org/mtproto
- https://telegram.org/tos/bot-developers
- https://telegram.org/blog/ai-bot-revolution-11-new-features
- https://telegram.org/blog/watch-apps-and-more

## Вывод

Telegram для Kolibri нужно рассматривать как полноценную платформу:

- бот = человекоподобный AI-диспетчер и безопасный command router;
- Mini App = мобильный визуальный пульт фабрики;
- Bot API = runtime contract для сообщений, команд, webhooks, business updates,
  rich text, payments, files и статусов;
- Telegram Login / OIDC = внешний owner/auth слой для web-интерфейсов;
- Business / Secretary / Guest Bots / bot-to-bot = будущий контур автономных
  агентов и командной работы;
- Payments/Stars/affiliate/subscriptions = будущий revenue контур, но только с
  explicit owner approval для денег.

На 2026-07-01 последняя найденная публичная версия Bot API в changelog:
Bot API 10.1 от 2026-06-11. Самое важное для Kolibri: Rich Messages и
streaming AI replies, то есть Telegram уже официально движется к формату
человекоподобных AI-ботов с постепенной генерацией ответа.

Практическое решение для Kolibri: включаем сейчас только Bot API private chat,
чистое меню, один canonical receiver, Mini App auth contract, безопасные inline
actions и sanitized reports. Rich Messages, SSE/streaming, Telegram Login и
Mini App launch configuration идут следующим слоем. Guest Mode, Bot-to-Bot,
Business/Secretary, Managed Bots, Stars/payments и broadcast monetization
остаются policy-gated future features.

## Возможности Telegram, применимые к Kolibri

### 1. Human AI Bot

Назначение для Kolibri:

- принимать свободный русский текст;
- отличать разговор от задачи;
- формировать Control Plane envelope;
- возвращать человеческие summaries без raw logs;
- поддерживать streaming/partial response;
- помнить последние задачи и контекст фабрики;
- работать как owner-facing директор-оркестратор.

Обязательные правила:

- не показывать `task_id`, node id, worktree, stderr/stdout без прямого запроса;
- не отвечать заготовками;
- не запускать Mac-local implementation;
- все product tasks отправлять в Control Plane / Fabric API;
- один canonical receiver: webhook preferred, polling только fallback.

### 2. Commands And Clean Menu

Telegram поддерживает command scopes. Для Kolibri owner scope должен быть
минимальным:

- `/start` — открыть пульт и принять новую задачу;
- `/status` — статус фабрики;
- `/help` — краткая помощь.

Не держать в меню старые или коммерчески-шумные команды вроде `/plans`,
`/profile`, `/config`, `/ref`, `/support`, если они не реализованы в Kolibri UX.
Для сложных действий использовать Mini App, inline buttons и обычный текст.

### 3. Mini App

Kolibri Mini App должен быть главным мобильным UI:

- command composer;
- task board;
- active/running/completed/blocked tasks;
- fleet nodes;
- agents;
- models;
- PR/CI;
- artifacts;
- logs as summarized proof;
- settings with safety gates.

Требования:

- validate Telegram `initData` server-side;
- owner/admin authorization before privileged actions;
- use Telegram theme params;
- support Main Button / bottom controls;
- clear loading, empty, error and success states;
- no banking/payment/admin destructive actions without approval.

### 4. Bot API Runtime

Нужные API areas:

- `getUpdates` / webhook, but never both as active receivers;
- `sendMessage`, `editMessageText`, chat actions for streaming-like UX;
- command APIs: `setMyCommands`, `deleteMyCommands`, command scopes;
- menu button APIs: `setChatMenuButton`;
- file/media handling for screenshots, docs, estimates and artifacts;
- rich text formatting for long reports;
- rich message drafts / streaming-style AI reports;
- inline keyboards for confirmations, filters and artifact actions;
- callback queries for task actions;
- reactions, forum topics, direct-message topics and channel posts where useful;
- business connection updates only behind policy gates;
- business updates only after separate policy.

Operational rule:

- use webhook as the canonical production receiver when ingress is stable;
- use long polling only as fallback/diagnostic receiver;
- never run two active receivers against the same bot token;
- never call update-consuming methods from diagnostics unless the task explicitly
  permits it.

### 5. Rich Text Reports

Telegram 2026 rich text improvements are important for Kolibri reports:

- headings;
- tables;
- collapsible sections;
- nested quotes;
- inline media;
- math/formulas;
- long messages up to large report sizes with compact reading UX.
- streamed "thinking/progress" blocks for AI task execution.

Use this for:

- daily factory report;
- PR/CI summary;
- server incident summary;
- agent handoff;
- estimate/report previews.

### 6. Guest Bots, Bot-To-Bot, Secretary/Business

Future Kolibri architecture:

- Guest Bot mode: mention Kolibri from another chat and receive bounded answer;
- bot-to-bot communication: agent mesh and workflow automation;
- Business/Secretary mode: optional business-account automation;
- group guardian: screen join requests or moderate owner communities.
- bot-to-bot mode: agents can exchange bounded messages, but only with
  trace_id/task_id and loop protection.

Safety gate:

- do not enable business/secretary access until policy, audit logs and owner
  approval are implemented.
- do not let bots talk to bots without max hops, budget, rate limits and
  explicit task ownership.

### 7. Login And Identity

Telegram Login / OIDC can become owner auth for public/private web surfaces:

- web dashboard auth;
- Mini App backend session;
- safe owner/admin role mapping;
- token-bound request identity;
- short-lived sessions.

Required:

- verify ID tokens / initData cryptographically;
- bind Telegram user id to Kolibri roles;
- no secrets in logs;
- no implicit escalation from public Telegram user to owner.

### 8. Payments, Stars, Subscriptions

Telegram supports payments, Stars and monetization primitives. For Kolibri this
belongs to later revenue phase:

- paid mini app features;
- digital products;
- subscriptions;
- support packages;
- affiliate/referral mechanics.

Hard rule:

- no automatic money movement, payout, bank, tax, payment provider or paid
  publication actions without explicit owner approval.
- digital goods/services inside Telegram should be modeled with Telegram Stars;
  physical goods/services use payment providers, invoices and provider policy.
- every paid action must be idempotent, auditable and owner-approved before
  first production use.

### 9. Channels, Groups, Communities

Kolibri can use:

- private owner chat as command center;
- private team/group chat for agent reports;
- public channel for product updates;
- discussion group with guardian/moderation bot;
- scheduled reports and release notes.

Keep owner control separate from public/community automation.

### 10. Gateway API

Telegram Gateway is a separate HTTP API for sending verification codes through
Telegram instead of SMS.

Possible Kolibri use:

- authenticate new users for public Kolibri services;
- reduce SMS dependency for sign-up/login;
- add account verification for future SaaS/revenue workflows.

Not for MVP:

- not needed to fix the current bot;
- should be introduced only after auth/session/roles are stable.

### 11. TDLib And MTProto

Telegram has two lower-level client-facing surfaces:

- Telegram API / MTProto: protocol layer for Telegram clients.
- TDLib: cross-platform client library usable from many languages.

Kolibri interpretation:

- Bot API is the correct default for `@kolibriai_bot`.
- TDLib/MTProto are only needed for building a custom Telegram client,
  advanced user-account automation, or deep client features not exposed to bots.
- Do not use user-account automation to bypass Telegram limits or business
  rules. For Kolibri, owner control should stay inside official Bot API,
  Business Bot, Mini App, Login and Gateway paths.

### 12. Safety, Privacy And Terms

Hard safety rules:

- no spam, scam, fake users, fake engagement or mass unsolicited messaging;
- no extraction/printing of Telegram tokens, private chat IDs, cookies or
  personal messages into logs/artifacts;
- every privileged factory action must have owner identity, task_id, trace_id,
  scope, audit log and reversible/fallback path where possible;
- public/community automation must be separate from owner_root control;
- paid/financial operations remain approval-gated.

### 13. What Telegram Cannot Be For Kolibri

Telegram should not become:

- the source of truth for code, secrets, payments or git history;
- an unrestricted shell;
- the only control path for production incidents;
- a place where raw logs/secrets are dumped;
- an unsupervised mass-outreach engine.

Telegram should be:

- the most convenient owner-facing command and observation layer;
- a human AI interface over Fabric API / Control Plane;
- a notification and artifact delivery surface;
- a polished mobile UI via Mini App.

## Kolibri Telegram Product Shape

MVP:

1. Clean bot commands and menu.
2. One canonical webhook/poller.
3. Human AI chat grounded in factory context.
4. `/status` and free-text task submission.
5. Mini App task board and fleet overview.
6. Artifacts and PR/CI links.
7. Owner-safe redaction.
8. Server-side Telegram initData verification for Mini App.
9. Fabric API envelope creation from normal Russian owner messages.

P1:

1. Streaming responses.
2. Rich text status reports.
3. Inline buttons for approve/retry/cancel/view artifact.
4. Model/fleet chooser.
5. Agent assignment by Russian names.
6. Push notifications for failed CI, blocked nodes, completed PRs.
7. Rich daily/incident reports with collapsible blocks and tables.

P2:

1. Guest Bot mode.
2. Bot-to-bot mesh.
3. Business/Secretary integration.
4. Payments/Stars revenue layer after finance policy.
5. Public channel publishing.
6. Group guardian/community automation.
7. Gateway API for verified user onboarding.

## Immediate Next Tasks For Agents

1. PR #89 verifier cleanup: make Control Plane wrapper green for Telegram
   Superfactory branch.
2. Single receiver migration: choose webhook or canonical polling; stop all
   stale receivers only after confirmed evidence.
3. Mini App UX pass: make `kolibriai.ru/?telegram=1` a real Telegram-optimized
   command dashboard.
4. Bot runtime pass: replace raw task text with human summaries and streaming
   progress.
5. Auth pass: validate initData/OIDC and map Telegram owner id to Kolibri roles.

## Recommended Remote Task

Task id:

`P0_TELEGRAM_FACTORY_COMMAND_CENTER_SPEC_AND_RUNTIME_GAP_AUDIT_2026_07_01`

Goal:

Create an implementation-ready spec and gap audit for turning `@kolibriai_bot`
and `kolibriai.ru` Mini App into the Kolibri Factory command center.

Must read:

- `ops/telegram_gateway.py`
- `ops/agent_host.py`
- `tests/test_telegram_gateway.py`
- `tests/test_agent_host_telegram_chat.py`
- `docs/superfactory/API_FIRST_CONTROL_FABRIC.md`
- `docs/superfactory/FULL_CONTROL_API_POLICY.md`
- this capability map.

Acceptance:

- define final clean command menu;
- define webhook vs polling canonical receiver plan;
- define Mini App screens and API calls;
- define owner auth and `initData` verification;
- define streaming/rich-message strategy;
- define safety gates for admin actions;
- produce PLAN/ACTIONS/TESTS/RESULT/NEXT artifacts;
- no product code changes in the audit task.
