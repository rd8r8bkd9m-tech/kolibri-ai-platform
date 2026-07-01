# Telegram Platform Capability Map For Kolibri Factory

Дата: 2026-07-01

Назначение: зафиксировать, какие возможности Telegram нужно использовать для
Kolibri Factory Bot и Mini App, чтобы бот стал полноценным командным пультом
фабрики, а не набором случайных команд.

## Источники

- https://telegram.org/
- https://core.telegram.org/bots
- https://core.telegram.org/bots/features
- https://core.telegram.org/bots/api
- https://core.telegram.org/bots/webapps
- https://core.telegram.org/bots/payments
- https://core.telegram.org/bots/telegram-login
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
- inline keyboards for confirmations, filters and artifact actions;
- callback queries for task actions;
- business updates only after separate policy.

### 5. Rich Text Reports

Telegram 2026 rich text improvements are important for Kolibri reports:

- headings;
- tables;
- collapsible sections;
- nested quotes;
- inline media;
- math/formulas;
- long messages up to large report sizes with compact reading UX.

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

Safety gate:

- do not enable business/secretary access until policy, audit logs and owner
  approval are implemented.

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

### 9. Channels, Groups, Communities

Kolibri can use:

- private owner chat as command center;
- private team/group chat for agent reports;
- public channel for product updates;
- discussion group with guardian/moderation bot;
- scheduled reports and release notes.

Keep owner control separate from public/community automation.

## Kolibri Telegram Product Shape

MVP:

1. Clean bot commands and menu.
2. One canonical webhook/poller.
3. Human AI chat grounded in factory context.
4. `/status` and free-text task submission.
5. Mini App task board and fleet overview.
6. Artifacts and PR/CI links.
7. Owner-safe redaction.

P1:

1. Streaming responses.
2. Rich text status reports.
3. Inline buttons for approve/retry/cancel/view artifact.
4. Model/fleet chooser.
5. Agent assignment by Russian names.
6. Push notifications for failed CI, blocked nodes, completed PRs.

P2:

1. Guest Bot mode.
2. Bot-to-bot mesh.
3. Business/Secretary integration.
4. Payments/Stars revenue layer after finance policy.
5. Public channel publishing.
6. Group guardian/community automation.

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

