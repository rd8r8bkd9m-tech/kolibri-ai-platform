# Kwork Factory Order Routing

Date: 2026-07-01

Purpose: every real Kwork lead or order becomes a scoped Kolibri Factory task with sanitized client data, isolated artifacts, and clear acceptance.

## Lead States

1. New lead or buyer project found in Kwork.
2. Fit check: AI bot, Telegram bot, mini app, parser, API integration, documents, estimates, dashboard or automation.
3. Proposal drafted and sent inside Kwork only.
4. Scope clarified inside Kwork.
5. Paid order starts.
6. Internal factory task envelope created.
7. Remote agent implements, tests and produces artifacts.
8. Codex reviews result as thin client.
9. Delivery package is returned through Kwork.
10. Revisions and follow-up offers stay inside Kwork.

## Intake Card

Create one intake card per lead or order:

- `kwork_project_id` or `kwork_order_id`.
- Public project title.
- Client alias, not private personal data.
- Category and fit score.
- Agreed deliverables.
- Agreed exclusions.
- Required access/data.
- Price, deadline and revision count.
- Risks: API limits, platform rules, missing data, scope creep.
- Factory task id.
- Branch/artifact path.
- Kwork reply status.

## Scope Rules

- Start work only after a paid Kwork order or explicitly approved pre-sales audit.
- Keep all client communication inside Kwork.
- Do not copy private chat, tokens, credentials, bank data, personal data or proprietary documents into public GitHub.
- Use demo data in public docs and screenshots.
- If client access is needed, request temporary credentials inside the Kwork order and instruct the client to rotate them after delivery.
- Separate every client into its own task id and branch.

## Factory Envelope Rules

Every order task must include:

- `task_id`.
- `kind: owner_remote_task`.
- `required_capability: generic_implementation`.
- `source.kind: kwork_order`.
- Owner business identity: `ИП Кочуров Владислав Евгеньевич, НПД`.
- Sanitized client alias.
- Isolated branch: `kwork/YYYYMMDD/projectid-slug`.
- Explicit write scope.
- Acceptance criteria.
- Artifact requirements.
- Secrets/client-data redaction constraints.

Submit through the factory dispatcher:

```bash
ops/kolibri-dispatch submit --file docs/business/kwork/factory-envelopes/<envelope>.json
```

## Suggested Branch Pattern

```text
kwork/YYYYMMDD/<project-id>-<short-slug>
```

Examples:

```text
kwork/20260701/3208076-telegram-ai-bot
kwork/20260701/3208206-amocrm-ai-assistant
kwork/20260701/3207719-price-parser
```

## Artifact Layout

Keep client artifacts private or sanitized. Suggested internal layout:

```text
docs/business/kwork/orders/YYYYMMDD-<project-id>-<slug>/
  INTAKE.md
  SCOPE.md
  FACTORY_TASK.md
  DELIVERY_CHECKLIST.md
  CLIENT_REPLY_DRAFTS.md
```

If product code is created for a client, use a separate private repository or an isolated branch/worktree according to the order and confidentiality level.

## Delivery Package

Before Kwork delivery, collect:

- short completion report;
- files or repository link allowed by the order;
- setup/run instructions;
- test checklist;
- limitations and required client-side actions;
- credential rotation reminder if any temporary access was used;
- support/revision boundary.

## Status Ledger

Track each order:

```text
task_id:
kwork_project_or_order_id:
client_alias:
status: lead|proposal_sent|scope_clarifying|ordered|running|ready_for_review|delivered|closed|blocked
factory_status:
lease_owner:
branch:
artifact_path:
tests_run:
blockers:
next_action:
```

## When A Client Replies

1. Read the message.
2. Classify: clarification, price objection, scope change, new requirement, access issue, delivery issue.
3. Draft a reply inside Kwork tone.
4. If scope changes, update the intake and task envelope.
5. If work is accepted, dispatch or update the remote factory task.
6. Send only after action-time owner confirmation for the exact public message.
