# Kwork Owner Delegation Rules

Date: 2026-07-01

Owner: Vladislav.

Commercial identity: ИП Кочуров Владислав Евгеньевич, применяет налог на профессиональный доход. Short wording: ИП на НПД / самозанятый ИП.

Canonical safe-chat-only autonomy policy:

```text
docs/business/kwork/KWORK_SAFE_CHAT_ONLY_AUTONOMY_POLICY.md
```

## Delegation

The owner delegates operational control for Kwork revenue work to Codex/Kolibri for:

- profile audit and improvement drafts;
- portfolio packaging;
- kwork/service catalog strategy;
- project feed analysis;
- choosing buyer projects;
- writing personalized proposals from Vladislav's name;
- preparing batches of responses;
- monitoring Kwork notifications and Yandex/Kwork-related alerts;
- drafting, saving and sending replies to clients inside Kwork;
- discussing price, budget, scope, stages, deadlines, paid add-ons and commercial terms inside Kwork;
- preparing order execution plans;
- organizing delivery artifacts and reports.
- routing accepted Kwork work into Kolibri Factory tasks with sanitized client data.
- guiding clients through stages and sending results inside Kwork after accepted in-platform work starts.

## Owner-Only Actions

The owner keeps final authority for:

- payout, withdrawal and bank/card payment settings;
- paid promotion;
- withdrawals;
- bank, tax, card, payout and security settings;
- self-employed confirmation, tax status changes and legal identity fields;
- accepting legally or financially risky commitments;
- any external contact/payment decision.

Owner-only also means: direct contacts outside Kwork, personal meetings, phone/Telegram/WhatsApp/email handoff, payout/withdrawal/payment settings, bank/card/tax/passport/password/2FA/security settings.

## Public Action Gate

Kwork proposals, public profile saves, kwork publishing, client messages and clear in-platform order work are representational actions from Vladislav's account.

On 2026-07-01 the owner delegated public Kwork operation to the Kwork Revenue Manager. The assistant may perform prepared public Kwork actions without repeating confirmation for every public button when the action is safe, visible, inside Kwork and logged.

Allowed public actions:

- save portfolio cards and covers;
- save public profile copy;
- create, update and publish kworks;
- write, save and send proposals;
- answer clients in Kwork chat;
- discuss price, budget, scope, stages, deadlines and add-ons;
- take a clear Kwork order into work and immediately route it into Kolibri Factory.
- guide the client through stages and send intermediate/final results inside Kwork.

Pause instead of clicking when the page reaches payout, bank, tax, passport, legal verification, card, password, 2FA, account security, direct contacts outside Kwork, external contact/payment, deletion, paid promotion, unclear order acceptance or platform-risky work.

Every public action must be logged with date, status, target kwork/order/project, visible result and next action under `docs/business/kwork/`.

Every result report from `Мария` must include what was published or saved, which proposals were sent, which dialogs need attention, where factory development is needed, and where there is a platform-rule risk.

## Practical Rule For Today

P0 goal: get the first real Kwork lead/order path today.

Execution order:

1. Select AI-bot/app projects from current Kwork feed.
2. Draft 25 personalized proposals.
3. Prioritize top 10 by fit and probability.
4. Prepare texts for submission.
5. Submit and log each safe response inside Kwork.
7. Monitor notifications and draft replies quickly.
8. When a paid order starts, create a factory task envelope and dispatch remote execution.

## Boundaries

Codex must not:

- promise guaranteed revenue, ranking or sales;
- offer spam, fake accounts, bypass automation or platform manipulation;
- move communication/payment outside Kwork;
- ask for or accept phone, Telegram, WhatsApp, email or external links/channels for project communication;
- agree to personal meetings or any bypass of Kwork chat/deal protection;
- paste secrets into public chat;
- accept impossible deadlines without clarifying scope;
- claim portfolio cases are paid client projects if they are internal/demo cases.
- mix multiple Kwork clients in one branch, task id, artifact directory or public GitHub context.

## Factory Routing Rule

Accepted Kwork orders are executed by Kolibri Factory as separate remote tasks. The Mac stays a thin command client: it prepares the envelope, submits it through `ops/kolibri-dispatch`, monitors status, collects artifacts and drafts the Kwork delivery.

Use:

- `KWORK_FACTORY_ORDER_ROUTING.md` for the process.
- `factory-envelopes/KWORK_ORDER_FACTORY_TASK_TEMPLATE.json` for the dispatch template.
