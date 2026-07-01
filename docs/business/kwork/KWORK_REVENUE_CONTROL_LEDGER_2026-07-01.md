# Kwork Revenue Control Ledger 2026-07-01

Date: 2026-07-01

Owner: Vladislav.

Commercial identity: ИП Кочуров Владислав Евгеньевич, НПД.

Purpose: keep Kwork revenue work tied to Kolibri Factory discipline: clear public-action gates, GitHub source of truth, sanitized order intake, and remote factory execution after paid orders.

## Current State

GitHub source of truth:

- Branch: `p0/kwork-revenue-manager-2026-07-01`.
- PR: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/87
- Status docs are under `docs/business/kwork/`.

Subagent delegation:

- Kwork/UI work delegated to `Мария`.
- Codex thread id: `019f1b76-23c0-7e71-a130-8d90434b7c4b`.
- Handoff file: `docs/business/kwork/KWORK_MARIA_HANDOFF_2026-07-01.md`.
- Safe-chat-only autonomy policy: `docs/business/kwork/KWORK_SAFE_CHAT_ONLY_AUTONOMY_POLICY.md`.
- Latest owner update delivered to `Мария`: negotiate and deliver only inside Kwork; public proposals/messages allowed; direct contacts, payout/bank/tax/passport/password/2FA/security settings and Kwork rule bypass are forbidden; log saved/published items, sent proposals, attention-needed dialogs, factory work and platform-rule risks.

Kwork public/profile state observed:

- First portfolio item exists on Kwork: `Telegram AI-бот для заявок и FAQ`.
- Kwork showed: `Работа в процессе подготовки к публикации. Обычно это занимает до нескольких часов.`
- Browser observed portfolio URL: `https://kwork.ru/portfolio/23058129`.
- Fifth handoff portfolio item was saved by `Мария` on 2026-07-01 05:21 MSK: `Аудит и доработка Telegram/AI-бота`; Kwork returned to the profile portfolio grid and showed the new work in preparation for publication.

Kwork published/created service state observed:

- First public kwork created by `Мария` on 2026-07-01 05:44 MSK.
- Title: `Создам Telegram AI-бота для заявок и ответов клиентам`.
- URL: `https://kwork.ru/script-programming/53216866/sozdam-telegram-ai-bota-dlya-zayavok-i-otvetov-klientam`.
- Public buyer price: `9 000 руб.`
- Seller-side selected kwork price: `7 200 ₽`.
- Deadline: `3 дня`.
- Category path: `Разработка и IT > Скрипты, боты и mini apps > Чат-боты`.
- Attributes observed on public page: `Написание и доработка`, `Python`, `Telegram`.
- Status note: public kwork page opened successfully after `Готово`; no validation blocker visible.

Kwork form state prepared but not publicly saved:

- Second portfolio item title: `AI-бот для документов, КП и смет`.
- Category: `Разработка и IT`.
- Subcategory: `Создание сайта`.
- Type: `Новый сайт`.
- Main image: `docs/business/kwork/portfolio-assets/02-ai-document-estimate.png`.
- Cover image: `docs/business/kwork/portfolio-assets/02-ai-document-estimate.png`.
- The Kwork `Сохранить` button was active.

## Public Action Gates

The assistant may prepare forms, upload owner-approved demo images, draft text and inspect public pages.

Owner public-button authorization was given on 2026-07-01:

```text
Публичные кнопки разрешаю нажимать
```

Owner negotiation/update authorization was reinforced on 2026-07-01:

```text
Мария may negotiate price, deadlines, scope, stages and execution terms only inside safe Kwork chat; send public proposals/messages from Vladislav's Kwork account; confirm clear in-platform work after receiving a request; route accepted work to the factory/agents; manage client stages and send results inside Kwork.
```

This authorization covers prepared and logged public Kwork actions:

- click `Сохранить` for a prepared portfolio item;
- save prepared public profile text;
- publish or edit a prepared kwork;
- send proposals from a documented send queue;
- send prepared safe replies to Kwork clients.
- negotiate price, deadlines, scope, milestones, terms and add-ons only inside Kwork;
- confirm clear Kwork work and route it to Kolibri Factory/agents;
- send stage updates and delivery results inside Kwork.

This authorization does not cover:

- tax, payout, bank, passport, card, phone, email, password, 2FA or security settings;
- payout/withdrawal/bank/tax/legal/security actions;
- external contact/payment;
- phone, Telegram, WhatsApp, email, personal meetings or links used to bypass Kwork;
- accepting, delivering or closing unclear, illegal, abusive, impossible or platform-risky work;
- deleting data;
- spam, fake claims, fake portfolio, fake reviews or platform manipulation.

Every public click must be logged with time, page/action, visible result and next action.

## Today Execution Queue

1. Delegate Kwork UI completion to the dedicated subagent role `Мария`.
2. Done 2026-07-01 05:21 MSK: fifth portfolio card saved from `05-bot-audit.png` and observed in Kwork preparation state.
3. Inspect public profile after Kwork finishes portfolio processing.
4. Done 2026-07-01 05:44 MSK: first Telegram AI bot kwork created/published to public page after fields were verified.
5. Publish or complete remaining narrow kworks when price/scope/deadline fields are unambiguous.
6. Update `KWORK_PORTFOLIO_UPLOAD_STATUS_2026-07-01.md` after every observed portfolio state change.
7. Send proposal wave A inside Kwork after verifying page state, project fit and current proposal limits.

## Offer Focus

Prioritize work the factory can deliver safely:

- Telegram AI bots for applications, FAQ, lead qualification and manager handoff.
- AI document assistants for КП, estimates, acts, reports and structured files.
- Knowledge-base support bots with controlled answers and source material.
- Mini apps/PWA around bots for forms, status screens and simple dashboards.
- Audit and repair of existing bots, prompts, API integrations and automation flows.

Avoid:

- gray traffic, account farming, fake engagement, bypasses or platform manipulation;
- unpaid technical work outside a Kwork order;
- external contact/payment requests;
- promises of guaranteed income, ranking, conversion or fully error-free AI.

## Lead Intake Rules

For every Kwork project or reply, create a sanitized intake row before doing work:

```text
lead_id:
kwork_project_or_order_id:
public_title:
client_alias:
fit: high|medium|low|skip
offer_type:
expected_price_range:
expected_term:
reply_status: draft|owner_approved|sent|answered|skipped
factory_task_id:
next_action:
```

Never put tokens, client private chats, personal data, bank data, cookies, screenshots with secrets or proprietary documents into public GitHub.

## Factory Dispatch On Paid Order

When a Kwork order is paid or clearly accepted inside Kwork and scope is clear:

1. Create sanitized order folder:

```text
docs/business/kwork/orders/YYYYMMDD-<project-id>-<slug>/
```

2. Fill:

```text
INTAKE.md
SCOPE.md
FACTORY_TASK.md
DELIVERY_CHECKLIST.md
CLIENT_REPLY_DRAFTS.md
```

3. Generate task envelope from:

```text
docs/business/kwork/factory-envelopes/KWORK_ORDER_FACTORY_TASK_TEMPLATE.json
```

4. Dispatch through Control Plane / Agent Host, not as local Mac implementation:

```bash
ops/kolibri-dispatch submit --file docs/business/kwork/factory-envelopes/<task>.json
```

5. Track:

```text
task_id:
lease_owner:
node:
branch:
artifact_path:
tests_run:
delivery_ready:
blockers:
```

## Revenue Daily Loop

Morning:

- Check Kwork inbox and notifications.
- Check proposal limits/connects.
- Check portfolio processing status.
- Refresh new project list and classify only safe/fit tasks.

Midday:

- Draft proposals for wave A/B.
- Submit safe proposal batch inside Kwork under the owner delegation.
- Convert replies into sanitized intake rows.

Evening:

- Update `KWORK_SEND_QUEUE_2026-07-01.md`.
- Update this ledger.
- Push GitHub status if any public state changed.
- Dispatch paid/approved work to remote factory execution.

## Next Kwork Execution Step

Run the `Мария` Kwork handoff: finish portfolio, publish focused kworks, analyze prices, send safe in-platform proposals, and route accepted work into Kolibri Factory.

After every public action, record the observed Kwork result in `KWORK_PORTFOLIO_UPLOAD_STATUS_2026-07-01.md`, `KWORK_SEND_QUEUE_2026-07-01.md` or this ledger before moving to the next action.

## Public Action Log

```text
time: 2026-07-01 05:21 MSK
target: Kwork portfolio item / user kolibrinano
action: selected /Users/kolibri/Documents/KworkPortfolio/05-bot-audit.png, uploaded it to the fifth portfolio form, used the generated/displayed cover, clicked public Сохранить
status: saved
visible_result: modal closed; Kwork portfolio grid showed a newly saved work in preparation for publication
url_or_title: https://kwork.ru/user/kolibrinano#portfolio-section / Аудит и доработка Telegram/AI-бота
blocker: none
next_action: continue with Kwork management section, price analysis, and first kwork completion/publishing under the existing delegation
```

```text
time: 2026-07-01 05:44 MSK
target: Kwork public kwork / user kolibrinano
action: created/completed first Telegram AI bot kwork draft, uploaded unique cover, filled description and buyer requirements, set volume, selected seller-side price 7200 ₽, selected 3-day deadline, clicked public Готово
status: published
visible_result: Kwork opened the public kwork page with title, cover, description, buyer requirements, attributes Python/Telegram, price 9 000 руб. for buyer and 3-day delivery
url_or_title: https://kwork.ru/script-programming/53216866/sozdam-telegram-ai-bota-dlya-zayavok-i-otvetov-klientam / Создам Telegram AI-бота для заявок и ответов клиентам
blocker: none
next_action: verify public visibility from manage kworks/profile, then send safe in-platform proposal wave A or prepare the next narrow kwork
```
