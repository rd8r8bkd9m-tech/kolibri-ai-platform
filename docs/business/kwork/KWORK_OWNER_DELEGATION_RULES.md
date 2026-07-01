# Kwork Owner Delegation Rules

Date: 2026-07-01

Owner: Vladislav.

Commercial identity: ИП Кочуров Владислав Евгеньевич, применяет налог на профессиональный доход. Short wording: ИП на НПД / самозанятый ИП.

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
- drafting replies to clients;
- preparing order execution plans;
- organizing delivery artifacts and reports.
- routing accepted Kwork work into Kolibri Factory tasks with sanitized client data.

## Owner-Only Actions

The owner keeps final authority for:

- payments;
- paid promotion;
- withdrawals;
- bank, tax, card, payout and security settings;
- self-employed confirmation, tax status changes and legal identity fields;
- accepting legally or financially risky commitments;
- final approval of public batch sending when required by account/action safety.

## Public Action Gate

Kwork proposals, public profile saves, kwork publishing, client messages and order acceptance are representational actions from Vladislav's account. Codex can prepare them end to end, but before the public click/send/publish step it must present:

- target project/client;
- exact text;
- proposed price and срок;
- risk notes;
- batch size.

Then Codex requests a short owner confirmation for that exact batch/action.

## Practical Rule For Today

P0 goal: get the first real Kwork lead/order path today.

Execution order:

1. Select AI-bot/app projects from current Kwork feed.
2. Draft 25 personalized proposals.
3. Prioritize top 10 by fit and probability.
4. Prepare texts for submission.
5. Ask one confirmation for the batch.
6. After confirmation, submit and log each sent response.
7. Monitor notifications and draft replies quickly.
8. When a paid order starts, create a factory task envelope and dispatch remote execution.

## Boundaries

Codex must not:

- promise guaranteed revenue, ranking or sales;
- offer spam, fake accounts, bypass automation or platform manipulation;
- move communication/payment outside Kwork;
- paste secrets into public chat;
- accept impossible deadlines without clarifying scope;
- claim portfolio cases are paid client projects if they are internal/demo cases.
- mix multiple Kwork clients in one branch, task id, artifact directory or public GitHub context.

## Factory Routing Rule

Accepted Kwork orders are executed by Kolibri Factory as separate remote tasks. The Mac stays a thin command client: it prepares the envelope, submits it through `ops/kolibri-dispatch`, monitors status, collects artifacts and drafts the Kwork delivery.

Use:

- `KWORK_FACTORY_ORDER_ROUTING.md` for the process.
- `factory-envelopes/KWORK_ORDER_FACTORY_TASK_TEMPLATE.json` for the dispatch template.
