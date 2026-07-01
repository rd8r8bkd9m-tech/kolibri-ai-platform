# Kwork Batch Send Approval Packet 2026-07-01

Status: first Wave A proposal sent; continue Wave A under safe-chat-only delegation.

Purpose: give the owner one clear approval packet for the first Kwork proposal wave while preserving Kolibri Factory rules: no fake status, no external payments, no secret exposure, no local Mac implementation as the main execution path.

## Public Action Gate

Sending proposals is public representational communication from Vladislav's Kwork account.

Owner public-button authorization was recorded on 2026-07-01:

```text
Публичные кнопки разрешаю нажимать
```

Operational meaning for proposal sending:

- no per-button confirmation is required for a documented proposal wave once the queue, targets and proposal texts are prepared;
- the assistant must verify the visible project page and proposal text before each send;
- every sent/failed/skipped proposal must be logged in `KWORK_SEND_QUEUE_2026-07-01.md`;
- do not send to projects that require off-platform contact/payment, fake activity, abuse, unclear illegal work, or secrets in public chat.

Payment, payout, tax, bank, card, passport, security, password, 2FA and account-recovery actions remain excluded.

The prepared portfolio save action is covered by the same public-button authorization, but its result must be logged separately in `KWORK_PORTFOLIO_UPLOAD_STATUS_2026-07-01.md`.

## Current Readiness

- Account direction: AI bots, Telegram bots, document/estimate AI, support bots, mini apps, parsers and API automation.
- Portfolio support: first card observed on Kwork; second card prepared in the form but not publicly saved.
- Proposal source: `KWORK_TODAY_OUTREACH_2026-07-01.md`.
- Send queue source: `KWORK_SEND_QUEUE_2026-07-01.md`.
- Order routing source: `KWORK_FACTORY_ORDER_ROUTING.md`.

## Recommended First Wave

Send Wave A first, not all 25 at once, unless the owner explicitly chooses the full wave. Wave A uses the strongest fit and keeps the first public batch easier to monitor.

| # | Project ID | Project | Offer | Range | Why first |
|---|---:|---|---|---|---|
| 1 | 3208095 | Сервис анализа звонков и проверки выполнения скриптов | AI call analysis MVP | sent 2026-07-01 06:00 MSK at 60 000 RUB / 10 days | High-value AI pipeline and reports. |
| 2 | 3207309 | Разработка ИИ-приложения для Word Add-in | AI document add-in prototype | 40 000-160 000 RUB | Fits document AI and API/backend skills. |
| 3 | 3207963 | Доработка платформы с Telegram-ботом | Audit + implementation stage | 20 000-150 000 RUB | Good fit for bot/backend rescue work. |
| 4 | 3208206 | AI-ассистент в amoCRM (TG + Max) | AI sales assistant + CRM handoff | 20 000-60 000 RUB | Clear bot + CRM handoff case. |
| 5 | 3208076 | Telegram-бот Python/Aiogram с ИИ | Telegram AI bot | 30 000-80 000 RUB | Direct match to core offer. |
| 6 | 3208237 | Telegram-магазин бытовой техники | Telegram shop MVP | 35 000-60 000 RUB | Practical bot commerce MVP. |
| 7 | 3207719 | Парсер цен конкурентов с уведомлениями | Price monitoring bot | 18 000-36 000 RUB | Small but executable automation. |
| 8 | 3207754 | Оцифровка кабинетов МП через API | API analytics module | 10 000-15 000 RUB | Narrow API analytics module. |
| 9 | 3207152 | Создать ТГ Бота | Lead intake AI bot | 12 000-15 000 RUB | Simple first lead bot. |
| 10 | 3207252 | Чат-бот или мини-приложение | Bot/mini app MVP | 10 000-15 000 RUB | Good portfolio-aligned mini app lead. |

## Send Rules

- Send only inside Kwork.
- Do not include phone, email, Telegram handle, external links, bank details, GitHub private links or direct-payment offers.
- Do not promise guaranteed revenue, rankings, conversion, moderation, or error-free AI.
- Ask for scope clarification, not secrets.
- If the client offers external contact/payment, keep the response inside Kwork and decline external payment.
- If the task requires questionable automation, platform abuse, bypassing limits or fake activity, skip it.

## After Each Sent Proposal

Update `KWORK_SEND_QUEUE_2026-07-01.md`:

```text
Time:
Project:
Status: sent|failed|skipped
Notes:
```

If a client replies, create a sanitized intake row:

```text
lead_id:
kwork_project_or_order_id:
public_title:
client_alias:
fit:
offer_type:
reply_status:
factory_task_id:
next_action:
```

## Factory Routing After Paid Order

No client implementation should become a chaotic local Mac task.

When a paid order exists, dispatch through Kolibri Factory:

1. Create sanitized order folder under `docs/business/kwork/orders/`.
2. Generate envelope from `docs/business/kwork/factory-envelopes/KWORK_ORDER_FACTORY_TASK_TEMPLATE.json`.
3. Submit through Control Plane / Agent Host.
4. Use Russian human-readable agent names in task assignments.

Suggested remote agent roles:

- `Алексей`: implementation lead.
- `Мария`: QA and acceptance checklist.
- `Ирина`: client delivery package and instructions.
- `Дмитрий`: review/security/secrets check.
- `Олег`: deployment/runtime validation when needed.

## Owner Decision

Recommended next public action:

```text
Continue Wave A from item #2 if visible proposal texts and project targets still match this packet.
```

Alternative:

```text
Stop before proposal sending and continue portfolio/profile setup only.
```

Because the owner has granted public-button authorization, the assistant should not ask for repeated per-button confirmations. The assistant must pause only when scope, page state, text, legal/platform risk, payment/security/tax settings or order acceptance is ambiguous.
