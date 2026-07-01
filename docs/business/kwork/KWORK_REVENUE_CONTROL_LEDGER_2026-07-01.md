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

Kwork public/profile state observed:

- First portfolio item exists on Kwork: `Telegram AI-бот для заявок и FAQ`.
- Kwork showed: `Работа в процессе подготовки к публикации. Обычно это занимает до нескольких часов.`
- Browser observed portfolio URL: `https://kwork.ru/portfolio/23058129`.

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

The assistant must stop before these actions unless the owner gives action-time confirmation:

- click `Сохранить` for a Kwork portfolio item;
- save public profile text;
- publish or edit a kwork;
- send proposals or messages;
- accept, reject, price, deliver or close an order;
- enter/save tax, payout, bank, passport, card, phone, email or security settings.

Exact confirmation phrase for the currently prepared item:

```text
Сохраняй вторую карточку Kwork
```

## Today Execution Queue

1. Save second portfolio card only after the exact owner confirmation above.
2. Prepare card 3 in the browser without saving: `AI-бот поддержки по базе знаний`.
3. Prepare card 4 in the browser without saving: `Мини-приложение: форма и заявки`.
4. Prepare card 5 in the browser without saving: `Аудит и доработка Telegram/AI-бота`.
5. Inspect public profile after Kwork finishes processing the first item.
6. Update `KWORK_PORTFOLIO_UPLOAD_STATUS_2026-07-01.md` after every observed public state change.
7. Send proposal wave A only after owner batch confirmation.

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

When a Kwork order is paid and scope is clear:

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
- Submit owner-approved proposal batch inside Kwork.
- Convert replies into sanitized intake rows.

Evening:

- Update `KWORK_SEND_QUEUE_2026-07-01.md`.
- Update this ledger.
- Push GitHub status if any public state changed.
- Dispatch paid/approved work to remote factory execution.

## Next Owner-Facing Decision

The next public action is saving the second portfolio card. The browser form is ready. The assistant must wait for:

```text
Сохраняй вторую карточку Kwork
```

Without that phrase, continue only non-public preparation, GitHub docs, read-only inspection, and internal factory task setup.
