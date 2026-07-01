# Kwork Maria Handoff 2026-07-01

Owner: Владислав.

Subagent working name: Мария.

Role: Kwork Revenue Manager.

Status: dispatched to a real Codex background thread.

Dispatch:

- thread_id: `019f1b76-23c0-7e71-a130-8d90434b7c4b`;
- output directory: `/Users/kolibri/Documents/Codex/2026-07-01/kwork-maria-revenue-manager/outputs`;
- created from the supervising factory thread on 2026-07-01.

## Mission

Fully prepare Vladislav's Kwork/Quork account for revenue:

- finish and save portfolio cards;
- edit safe public profile text;
- create, update and publish focused kworks;
- analyze Kwork prices for the selected directions;
- send proposals and answer clients inside Kwork;
- route accepted work into Kolibri Factory;
- log every public action under `docs/business/kwork/`.

## Current UI Point

Yandex Browser is logged into Kwork as `kolibrinano`.

Expected page:

```text
https://kwork.ru/user/kolibrinano#portfolio-section
```

The supervising agent stopped while adding the fifth portfolio card.

Expected current form state:

- title: `Аудит и доработка Telegram/AI-бота`;
- category: `Разработка и IT`;
- subcategory: `Создание сайта`;
- type: `Новый сайт`;
- macOS file picker opened in `/Users/kolibri/Documents/KworkPortfolio`;
- select `05-bot-audit.png`;
- open it;
- wait for Kwork to generate or display the cover;
- click public `Сохранить`;
- verify the portfolio grid/status.

If the visible UI differs, inspect first and log the actual state. Do not guess.

## Owner Delegation

The owner authorized public Kwork operation from his account.

Latest owner update for `Мария`:

- negotiate price, deadlines, work composition, stages and execution terms only inside the safe Kwork chat;
- send public proposals and messages from Vladislav's account;
- after a Kwork request/order appears, confirm clear work and launch development through Kolibri Factory agents;
- guide the client through stages and send results inside Kwork;
- if a client asks for or sends a direct contact, politely answer that work continues only through the safe Kwork deal/chat according to platform rules, so both sides are protected;
- document what was published/saved, which proposals were sent, which dialogs need attention, where factory development is needed, and where platform-rule risk exists.

Allowed:

- save portfolio cards and covers;
- edit and save public profile copy;
- create, update and publish kworks;
- write, save and send proposals;
- answer clients inside Kwork;
- discuss price, budget, scope, stages, deadlines and paid add-ons inside Kwork;
- accept clear in-platform Kwork work and route it into Kolibri Factory.

Forbidden:

- payout, withdrawal, bank, card, tax, self-employed/IP verification, passport/legal forms;
- password, 2FA, phone/email/security/account-recovery settings;
- paid promotion or ads unless separately approved;
- deleting account data;
- external contacts: phone, Telegram, WhatsApp, email, external links for communication;
- personal meetings or any other channel intended to bypass Kwork;
- off-platform payment;
- spam, fake reviews, fake credentials, fake portfolio, platform manipulation;
- unclear, illegal, abusive, impossible or platform-risky orders.

If a client asks for direct contact, answer inside Kwork:

```text
Давайте продолжим здесь, через безопасную сделку и чат Kwork. Так соблюдаются правила площадки, а обе стороны защищены: сохраняется история договоренностей, этапы и передача результата.
```

## Kworks To Publish Or Finish

Primary safe directions:

1. Telegram AI bot for leads, FAQ and manager handoff.
2. AI bot for documents, КП, estimates, acts and reports.
3. Knowledge-base/FAQ support bot.
4. Mini app/PWA for forms, applications and status screens.
5. Audit and repair of existing Telegram/AI bots.

Use source copy:

- `KWORK_PROFILE_COPY.md`;
- `KWORK_SERVICE_CATALOG.md`;
- `KWORK_EXECUTABLE_AI_BOT_OFFERS.md`;
- `KWORK_FIRST_KWORK_READY_TO_PASTE.md`;
- `KWORK_PORTFOLIO_READY_TO_UPLOAD.md`;
- `KWORK_DAILY_OPERATING_SYSTEM.md`;
- `KWORK_RISK_AND_RULES.md`.

## Price Analysis Task

Before final publishing, inspect live Kwork search/category pages for each direction and record:

- 5-10 comparable kworks;
- visible base price;
- delivery time;
- number of packages/options;
- trust signals: reviews, portfolio, response time if visible;
- whether the offer is too broad or narrow.

Create or update:

```text
docs/business/kwork/KWORK_PRICE_PACKAGES_2026-07-01.md
```

Use conservative first prices until the account gains reviews.

## Factory Routing

When an order is accepted or paid inside Kwork:

1. Create sanitized order folder under `docs/business/kwork/orders/`.
2. Do not place secrets or private client documents in public GitHub.
3. Generate task envelope from `factory-envelopes/KWORK_ORDER_FACTORY_TASK_TEMPLATE.json`.
4. Dispatch through Kolibri Control Plane / Agent Host.
5. Use Russian agent names in assignment notes.
6. Track status, artifacts, tests and client reply drafts.

## Required Log Format

For every public action:

```text
time:
target:
action:
status: saved|published|sent|answered|blocked|failed
visible_result:
url_or_title:
blocker:
next_action:
```

## First Actions

1. Finish fifth portfolio card with `05-bot-audit.png`.
2. Verify portfolio grid.
3. Open Kwork management section.
4. Publish or complete the first Telegram AI bot kwork.
5. Analyze live pricing for the five directions.
6. Publish remaining safe kworks when package fields are unambiguous.
7. Update docs and push the PR branch.

## Blocker Rule

If Computer Use/UI access is unavailable, do not imitate completion. Return:

```text
status: blocked
blocked_reason: no-ui-computer-use-access
current_expected_ui:
next_manual_or_tool_action:
```
