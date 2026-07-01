# Telegram Official Capabilities Full Study For Kolibri

Дата исследования: 2026-07-01
Источник: официальные страницы `telegram.org` и `core.telegram.org`.
Назначение: дать Kolibri Factory полную карту того, что Telegram можно
использовать как платформу управления, AI-интерфейс, Mini App, revenue-канал и
безопасный owner command surface.

Этот документ не разрешает live mutation бота, webhook, BotFather-настроек,
платежей, Business/Guest/Bot-to-Bot режима или рассылок. Все такие действия
должны идти отдельными задачами с owner approval, trace_id, task_id и
отдельными safety gates.

## Executive Summary

Telegram уже не просто чат с ботом. Для Kolibri это полноценная платформа:

- Bot API: основной безопасный интерфейс для `@kolibriai_bot`.
- Mini Apps: полноценный мобильный UI внутри Telegram, фактически замена
  отдельного мобильного приложения.
- Rich Messages: структурированные AI-отчеты, таблицы, раскрывающиеся блоки,
  медиа, формулы и потоковая генерация через rich drafts.
- Guest Bots: AI-бота можно вызывать в чужих чатах по mention, без добавления в
  участники, но с жестким ограничением контекста.
- Bot-to-Bot: официальная основа для агентных цепочек, но только с loop
  prevention, лимитами и наблюдаемостью.
- Secretary/Business Bots: бот может быть подключен к профилю/бизнес-аккаунту
  и обрабатывать входящие сообщения в заданном владельцем scope.
- Managed Bots: отдельный слой, где бот-менеджер может помогать создавать и
  управлять другими ботами.
- Telegram Login/OIDC: внешний auth слой для сайта и dashboard.
- Gateway API: отдельный HTTP API для verification codes через Telegram вместо
  SMS.
- Payments/Stars: деньги, подписки, paid media и цифровые товары, но для
  Kolibri это future revenue phase, не MVP.
- TDLib/Telegram API/MTProto: для создания кастомных клиентов и глубоких
  клиентских интеграций; для `@kolibriai_bot` это не основной путь.

Практический вывод: ближайшая правильная форма продукта - `@kolibriai_bot` как
человеческий AI-диспетчер плюс Mini App как визуальный command center фабрики.
Команды в меню нужно держать минимальными, сложные действия переносить в Mini
App, а все реальные product/deploy/admin задачи направлять через Kolibri
Fabric API / Control Plane.

## Official Source Index

- Telegram APIs overview: https://core.telegram.org/
- Bot API: https://core.telegram.org/bots/api
- Bot features: https://core.telegram.org/bots/features
- Mini Apps: https://core.telegram.org/bots/webapps
- Telegram Login/OIDC: https://core.telegram.org/bots/telegram-login
- Widgets: https://core.telegram.org/widgets
- Gateway overview: https://core.telegram.org/gateway
- Gateway API: https://core.telegram.org/gateway/api
- Telegram Business API: https://core.telegram.org/api/business
- TDLib: https://core.telegram.org/tdlib
- Payments for digital goods / Stars: https://core.telegram.org/bots/payments-stars
- Payments for physical goods/services: https://core.telegram.org/bots/payments
- Bot platform developer terms: https://telegram.org/tos/bot-developers
- AI bot platform update: https://telegram.org/blog/ai-bot-revolution-11-new-features

## 1. Telegram API Families

Telegram officially exposes several families of capabilities:

- Bot API: HTTPS JSON API for bots. This is the correct default for Kolibri.
- Telegram API / MTProto: lower-level protocol for custom Telegram clients.
- TDLib: cross-platform client library that handles networking, encryption,
  local storage and update ordering for client apps.
- Gateway API: separate HTTP API for verification-code delivery.
- Widgets/Login: website integration layer.

Kolibri decision:

- Use Bot API + Mini App + Telegram Login first.
- Use Gateway later for user verification in SaaS/onboarding flows.
- Use TDLib/MTProto only if Kolibri intentionally builds a custom Telegram
  client or needs a capability not available to bots.
- Do not use user-account automation to bypass Telegram rules, rate limits or
  business constraints.

## 2. Bot API Core

Bot API gives Kolibri:

- receiving updates by webhook or `getUpdates`;
- message handling for private chats, groups, supergroups, channels and direct
  message topics;
- text, photos, video, documents, voice, video notes, stickers, polls, dice,
  contact, venue and location objects;
- media groups, file IDs, downloads/uploads, thumbnails and captions;
- reactions, message reaction counts, forum topics, direct-message topics;
- inline queries, chosen inline results and callback queries;
- shipping queries, pre-checkout queries and successful payment messages;
- business connection updates, business messages and deleted business messages;
- guest messages and guest replies;
- paid media, paid messages, gifts, checklists, suggested posts and Stars;
- web app data and `answerWebAppQuery`;
- admin/moderation methods for groups/channels when the bot has rights;
- `setMyCommands`, command scopes and `setChatMenuButton`;
- `sendChatAction`, `editMessageText`, reply markup, keyboards and inline
  keyboards;
- rich message methods in Bot API 10.1.

Kolibri runtime rule:

- Production must have one canonical receiver for one bot token.
- Webhook is preferred when ingress is stable.
- Long polling is fallback/diagnostic only.
- Do not run webhook and polling as active consumers of the same token.
- Diagnostics must not consume live updates unless the task explicitly allows
  it.

## 3. Updates, Webhooks And Receiver Discipline

Telegram states `getUpdates` and webhooks are mutually exclusive update
delivery mechanisms. Incoming updates are stored by Telegram until the bot
receives them, but not indefinitely.

Kolibri implications:

- `ops/telegram_gateway.py` must remain the single canonical receiver or be
  replaced by exactly one new receiver.
- Tests must mock Telegram calls; they must not call `getUpdates`,
  `setWebhook`, `deleteWebhook`, `setMyCommands` or `setChatMenuButton`.
- Any receiver migration must be a separate task with proof:
  current receiver identity, target receiver identity, webhook/poller status,
  rollback path and token lineage evidence without printing the token.

## 4. Commands, Menu And BotFather UX

Telegram supports:

- slash commands up to 32 chars;
- command scopes by user/group/admin/language;
- default global commands such as `/start`, `/help`, `/settings` where relevant;
- menu button with command list or Mini App launch;
- BotFather profile fields: name, username, about text, description, media,
  localized descriptions and profile media;
- BotFather Mini App configuration: Main Mini App, splash/loading screen,
  menu button, attachment menu test setup, bot management modes.

Kolibri menu decision:

- Owner bot menu should be clean and minimal:
  - `/start` - open Kolibri command center;
  - `/status` - concise factory status;
  - `/help` - short human help.
- Remove or hide unrelated old commands like `/plans`, `/profile`, `/config`,
  `/ref`, `/faq`, `/support` unless they are truly implemented for Kolibri.
- Complex commands should be natural language and Mini App flows, not slash-menu
  clutter.
- Backend must verify authorization for every command; command scopes are UX,
  not security.

## 5. Text, Buttons, Keyboards And Inline UX

Telegram gives several levels of interaction:

- free text input;
- reply keyboards for simple choices;
- inline keyboards for callback actions, URL buttons, switch-to-inline, games,
  payments and web app buttons;
- callback queries for behind-the-scenes actions;
- chat/user selection buttons;
- deep links with `start` and `startgroup` payloads;
- inline mode from any chat;
- attachment menu integration for approved/test contexts.

Kolibri usage:

- Free text should be the primary owner input: "почини телеграм", "запусти
  аудит", "покажи агентов".
- Inline keyboards should be used for bounded actions:
  - view artifact;
  - open PR;
  - retry after failure;
  - cancel task;
  - approve gated action.
- Every callback must be idempotent and bound to task_id, trace_id, owner role
  and short-lived session state.

## 6. Mini Apps As The Main Kolibri UI

Telegram Mini Apps can replace a website inside Telegram and are launched from:

- main Mini App/profile button;
- keyboard button;
- inline button;
- bot menu button;
- inline mode;
- direct link with `startapp`;
- attachment menu.

Mini App APIs include:

- `window.Telegram.WebApp`;
- `initData` and `initDataUnsafe`;
- theme params and CSS variables;
- safe area and content safe area;
- fullscreen, orientation lock/unlock, expand/close;
- BackButton, MainButton and SecondaryButton;
- SettingsButton;
- haptic feedback;
- cloud storage;
- biometric manager;
- accelerometer, device orientation and gyroscope;
- location manager;
- local DeviceStorage and SecureStorage;
- popups, QR scanning, clipboard, file download, link opening and invoice
  opening;
- events for theme, viewport, safe area, buttons, invoices, popups,
  biometrics, fullscreen, home-screen state and device sensors.

Kolibri Mini App should expose:

- command composer;
- active task board;
- fleet nodes;
- agents with Russian display names;
- model/provider status;
- PR/CI board;
- artifact browser;
- settings/safety gates;
- read-only incident view;
- owner approvals for dangerous actions.

Kolibri Mini App must not:

- trust `initDataUnsafe` for authorization;
- expose raw logs/secrets by default;
- call live Bot API mutation methods on startup;
- perform deploy, service restart, webhook mutation, money movement or Business
  actions without owner confirmation.

## 7. Mini App Identity And InitData

Telegram Mini App identity flow:

- frontend receives raw `initData`;
- backend validates the signed data before trusting it;
- `auth_date` must be checked to reject stale data;
- complex values are JSON-serialized;
- third-party validation can use Telegram Ed25519 public keys and signature.

Kolibri auth decision:

- First P0 implementation must be server-side `initData` verification.
- Map Telegram user id to Kolibri roles from configuration:
  `owner`, `operator`, `reviewer`, `observer`, `guest_candidate`.
- Issue short-lived backend sessions only after successful verification.
- Never log raw bot token, raw initData, signature material, cookies or private
  owner prompts.
- `initDataUnsafe` may be used for display only after verified `initData`
  confirms the same user.

## 8. Telegram Login / OIDC

Telegram Login now includes:

- website login library;
- OIDC support with authorization code flow and PKCE;
- allowed URLs configured in BotFather;
- Client ID and Client Secret from BotFather;
- optional scopes such as profile, phone and write permission;
- server-side ID token validation.

Kolibri use:

- Use Mini App `initData` for in-Telegram owner command center.
- Use Telegram Login/OIDC for `kolibriai.ru` web dashboard and non-Telegram web
  auth.
- Both paths must map into the same Kolibri role model and audit log.

## 9. Rich Messages And Streaming AI Reports

Bot API 10.1 adds Rich Messages:

- structured content blocks;
- headings, lists, task lists, dividers and details blocks;
- tables with alignment/captions;
- media blocks and captions;
- block quotes, pull quotes, anchors, references and footnotes;
- LaTeX/math;
- maps, collages and slideshows;
- `sendRichMessage`;
- `sendRichMessageDraft` for streaming partial rich messages;
- `rich_message` on `Message`;
- rich message support in inline, guest and Web App query content.

Kolibri should use Rich Messages for:

- task status reports;
- CI summaries;
- branch/PR readiness summaries;
- server incident reports;
- agent handoffs;
- estimate/report previews;
- daily factory dashboard.

Guardrail:

- "thinking" or progress blocks must contain sanitized operational progress,
  not private chain-of-thought.
- Always keep plain text fallback via `sendMessage` / `editMessageText`.

## 10. Guest Bots

Guest Mode lets a bot be mentioned in a chat where it is not a participant and
reply once based on the specific invocation context. It does not grant chat
history or participant list access.

Kolibri future use:

- mention `@kolibriai_bot` in a project chat to ask a bounded question;
- ask for status of a public task or PR;
- summon a temporary AI helper for translation, fact-checking or summary.

Required gates before activation:

- public/private data classification;
- no owner-only artifact leakage;
- per-chat allowlist or explicit owner enablement;
- max output policy;
- spam/abuse prevention;
- audit trail and kill switch.

Guest Mode is not a substitute for owner command center.

## 11. Bot-To-Bot Communication

Telegram now allows bot-to-bot communication in specific contexts:

- group commands/replies with bot-to-bot mode;
- private bot-to-bot messages when enabled for both bots;
- business account workflows.

Telegram explicitly warns about infinite loops and recommends safeguards:

- deduplicate repeated messages;
- rate limit;
- enforce maximum depth/timeouts;
- stay stable if another bot responds instantly and continuously.

Kolibri architecture:

- This is useful for future agent teams, but must not be enabled casually.
- Every bot-to-bot exchange needs task_id, trace_id, max_hops, max_duration,
  max_cost, dedupe key and owner-visible audit.
- Bot-to-bot must use Russian display names for Kolibri agents, while keeping
  stable internal IDs.

## 12. Secretary / Business Bots

Secretary Mode / Business connection lets a user connect a bot to their account
and allow it to process incoming messages in selected chats. The user controls
which chats are accessible. Depending on rights, the bot can reply or perform
allowed actions on behalf of the user in recent active chats.

Telegram Business capabilities include:

- opening hours;
- location;
- quick replies;
- automated messages;
- custom start pages;
- chatbot support;
- connected bots for non-Premium users in some cases;
- business message updates and business connection events.

Kolibri policy:

- Do not enable Business mode for owner/customer automation until a separate
  privacy/security policy exists.
- Business data must be used only for the purpose the user authorized.
- Do not disclose message contents/files to third-party APIs without explicit
  authorization.
- Do not conceal bot activity from the business account owner.
- Use this later for safe customer support automation, not for spam or covert
  outreach.

## 13. Managed Bots

Telegram supports bots that help users create/manage other bots. Manager bots
can receive managed-bot updates and fetch the new bot token via Bot API methods.

Kolibri future use:

- a "bot factory" product where Kolibri creates AI assistant bots for clients;
- personal business bot setup assistant;
- managed customer bots with strict tenancy, secrets isolation and lifecycle
  governance.

Hard rule:

- Tokens for managed bots are secrets and must never appear in logs, artifacts
  or public PRs.

## 14. Payments, Stars And Monetization

Telegram monetization includes:

- Telegram Stars for digital goods/services;
- invoices to private chats, groups and channels;
- inline invoices;
- paid media;
- subscription plans;
- revenue sharing from Telegram Ads;
- gifts and Premium gifting;
- physical goods/services through third-party payment providers;
- Stars rewards/ads usage subject to Telegram terms.

Kolibri revenue interpretation:

- P0/P1: no live money actions.
- P2: use Stars for digital Kolibri products inside Telegram.
- Physical/off-platform services can use payment providers, but only after
  legal/tax/payment policy.
- Every invoice/refund/subscription/gift action needs explicit owner-approved
  finance gate and audit.
- `/paysupport` and dispute handling must exist before selling digital goods.

## 15. Gateway API

Gateway API is a separate Telegram verification platform:

- sends verification codes to users registered on Telegram;
- uses HTTPS API at `gatewayapi.telegram.org`;
- supports JSON/form/query parameters;
- uses a Gateway access token;
- supports delivery TTL, delivery/refund semantics and status checks.

Kolibri use:

- Later: phone verification for public Kolibri SaaS sign-up.
- Not needed to fix current `@kolibriai_bot`.
- Must be separate from Bot API token handling.

## 16. Widgets And Website Embeds

Telegram widgets include:

- share button;
- post widget;
- login widget / Login library;
- discussion widget.

Kolibri use:

- `kolibriai.ru`: Telegram Login/OIDC for account linking.
- Public articles: share button and post embeds.
- Product/community page: channel/discussion widgets if useful.
- Do not use widgets as admin auth without server-side token verification.

## 17. TDLib, Telegram API And Local Bot API Server

TDLib:

- cross-platform;
- multi-language;
- asynchronous;
- handles networking, encryption and local storage;
- supports all Telegram features for custom clients.

Local Bot API server:

- official open-source Bot API server can be hosted locally;
- local instance changes file limits and webhook transport assumptions;
- requires `logOut` before redirecting requests to local API URL;
- local server uses HTTP by default and needs TLS termination for remote HTTPS.

Kolibri use:

- Local Bot API server is useful if Kolibri needs large file upload/download
  capacity or isolated Bot API infrastructure.
- It is not required for initial bot cleanup.
- TDLib is not required for normal command center, but useful for a future
  custom Telegram client/desktop control surface.

## 18. Channels, Groups, Forums And Communities

Telegram gives Kolibri community primitives:

- private owner chat for command/control;
- private operations group for agent reports;
- channel for public release notes;
- group/forum topics for support and user communities;
- admin moderation actions if bot has rights;
- join requests and guard-bot style flows;
- reaction and poll statistics;
- silent scheduled messages.

Kolibri rule:

- Keep owner_root controls separate from public/community automation.
- Public channels can receive sanitized release notes only.
- Support/community bots must not see factory secrets, server identities or raw
  artifacts.

## 19. Files, Media, Reports And Artifacts

Bot API supports many media/file surfaces:

- documents;
- photos/videos/live photos;
- audio/voice/video notes;
- stickers/custom emoji;
- polls/checklists;
- locations/venues;
- paid media;
- copy/forward where permitted;
- protection flags.

Kolibri use:

- send sanitized artifacts as documents;
- attach screenshots and generated images;
- send PDF/DOCX/XLSX estimate packs;
- use rich captions and safe filenames;
- avoid forwarding protected/private content into public contexts.

For large artifact distribution, consider:

- signed artifact URLs from Kolibri backend;
- Telegram file upload for small/medium outputs;
- local Bot API server only if limits become a real blocker.

## 20. Safety, Privacy And Terms Constraints

Telegram Bot Platform Developer Terms matter directly:

- collect/store only data essential for the service;
- do not scrape public groups/channels to build datasets or AI products;
- protect credentials and secrets;
- do not spam or harass users;
- do not impersonate Telegram or unauthorized entities;
- do not misrepresent services/functions;
- do not ask for Telegram password or OTP;
- do not bypass rate limits/moderation;
- Business data cannot be repurposed or disclosed outside user authorization;
- payment/tax/dispute obligations remain developer responsibility;
- crypto Mini Apps must follow TON/TON Connect rules.

Kolibri hard rules:

- No unsolicited outreach automation from Telegram.
- No scraping chats/channels for model/RAG data.
- No hidden Business account actions.
- No token/secret printing.
- No fake AI assistant claims that misrepresent what Kolibri can do.
- No owner_root action unless authenticated, authorized, traceable and scoped.

## 21. Kolibri Capability Priority

### MVP

1. Clean command menu: `/start`, `/status`, `/help`.
2. Human free-text AI dispatcher in private owner chat.
3. One canonical receiver.
4. Server-side Mini App `initData` verification.
5. Mini App command center: tasks, fleet, agents, models, PR/CI, artifacts.
6. Sanitized status reports and artifact links.
7. Inline buttons for safe bounded actions.
8. Plain text fallback for all reports.

### P1

1. Rich Messages for factory reports.
2. Streaming rich drafts behind feature flag.
3. Mini App SSE/WebSocket live task board.
4. Model/provider selector.
5. PR/CI reviewer cards.
6. Owner approval modals for retry/cancel/drain.
7. Telegram Login/OIDC for web dashboard.

### P2

1. Guest Mode for bounded public/project chat answers.
2. Bot-to-Bot agent mesh with loop prevention.
3. Business/Secretary automation policy.
4. Managed bot factory.
5. Stars/payment/subscription product layer.
6. Gateway verification for public accounts.
7. Local Bot API server if artifact/file limits justify it.

## 22. What To Dispatch Next

Recommended next remote task:

`P0_TELEGRAM_COMMAND_CENTER_OFFICIAL_CAPABILITY_ALIGNMENT_2026_07_01`

Goal:

Align `@kolibriai_bot` and `kolibriai.ru` Mini App implementation plan with the
official Telegram capability map in this document.

Preferred remote agent:

`Иван - Telegram Platform Architect`

Scope:

- docs and contract tests only;
- no live Telegram Bot API mutation;
- no BotFather changes;
- no webhook/poller changes;
- no payments;
- no Business/Guest/Bot-to-Bot activation.

Must read:

- `docs/agent/research/2026-07-01-telegram-platform-capability-map/TELEGRAM_OFFICIAL_FULL_STUDY.md`
- `docs/product/telegram-command-center/2026-07-01/COMMAND_CENTER_SPEC.md`
- `docs/product/telegram-command-center/2026-07-01/MINI_APP_UX_SPEC.md`
- `docs/product/telegram-command-center/2026-07-01/OWNER_AUTH_AND_INITDATA_POLICY.md`
- `ops/telegram_gateway.py`
- `backend/main.py`
- `frontend/src/App.jsx`
- `tests/test_telegram_gateway.py`

Acceptance:

- produce exact implementation checklist for MVP/P1/P2;
- mark which Telegram features are allowed now, gated later, or forbidden;
- define clean BotFather/menu target state without executing it;
- define Mini App API contracts and auth gates;
- define Rich Message report model and fallback;
- define Guest/Bot-to-Bot/Business threat gates;
- update `NEXT_TASK_PROMPTS.md` with remote implementation tasks.
