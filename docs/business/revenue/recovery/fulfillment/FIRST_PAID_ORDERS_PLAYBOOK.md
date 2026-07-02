# First Paid Orders Fulfillment Playbook 2026-07-02

Status: internal operating draft. Does not authorize accepting, starting, or delivering real client work without owner-approved order scope.

## Purpose

Define how first paid orders move from intake to delivery while keeping scope, safety, QA, and factory routing controlled.

## Non-Negotiable Boundaries

Do not:

- perform paid actions without explicit approval;
- sign contracts or approve terms;
- send mass messages;
- publish externally;
- mutate public, production, billing, DNS, marketplace, or customer-facing accounts;
- expose secrets, credentials, tokens, private keys, payment details, or private customer data;
- promise discounts, refunds, deadlines, or scope changes without approval.

Stop and escalate if any step requires one of these.

## Roles

| Role | Responsibility |
| --- | --- |
| Order Owner | Commercial commitment, customer relationship, final approval, scope decisions. |
| Fulfillment Lead | Intake, routing, tracking, QA gate, delivery preparation. |
| Factory Operator | Production work inside approved scope. |
| QA Reviewer | Quality, completeness, safety, and handoff readiness. |
| Client Contact | Provides inputs and receives approved delivery. |

## Lifecycle

1. Intake.
2. Scope confirmation.
3. Factory routing.
4. Execution.
5. QA gates.
6. Delivery preparation.
7. Client handoff.
8. Closeout.

## Intake Fields

| Field | Required detail |
| --- | --- |
| Order ID | Internal/Kwork/order reference. |
| Client | Company or customer name; avoid sensitive detail. |
| Client contact | Approved channel only. |
| Offer | Purchased package or custom order. |
| Payment status | Paid, pending, failed, disputed, comped, or approved exception. |
| Terms reference | Link/reference only; no signing here. |
| Promised outcome | Plain-language result. |
| Due date | Confirmed date or delivery window. |
| Required inputs | Assets, examples, data, approvals, constraints. |
| Sensitive data present | Yes/no/type; never paste secret values. |
| Delivery channel | Approved destination. |
| Owner | Accountable internal person. |

## Scope Template

```text
Order:
Client:
Purchased offer:
Included deliverables:
Explicit exclusions:
Client inputs required:
Internal assumptions:
Acceptance criteria:
Target delivery window:
Approval required before:
```

## Routing Matrix

| Order type | Route to | QA emphasis |
| --- | --- | --- |
| Telegram bot starter | Bot/workflow factory | Conversation path, handoff, error states. |
| AI documents/estimates | Document/estimate factory | Numeric accuracy, template fit, human review. |
| Bot audit/repair | Review/repair factory | Findings, risk ranking, safe changes. |
| API/webhook integration | Integration factory | Payloads, auth handling, failure visibility. |
| Mini App/PWA prototype | Frontend prototype factory | Mobile fit, single-flow clarity, handoff docs. |

## Factory Work Packet

Every factory assignment must include:

- order ID;
- approved scope;
- deliverables;
- exclusions;
- input links or references;
- sensitive data handling notes;
- due date or milestone;
- QA reviewer;
- escalation contact.

## Execution Rules

- Work only from approved scope.
- Keep work inside approved systems or client-approved environments.
- Do not store secrets in notes, prompts, screenshots, tickets, or logs.
- Record assumptions and unresolved questions.
- Preserve QA evidence: test output, screenshots, file names, or change summaries.
- Mark blockers early.

## Statuses

| Status | Meaning |
| --- | --- |
| Intake | Order captured, not scoped. |
| Scoped | Scope written and internally approved. |
| Routed | Assigned to factory path. |
| In Progress | Production work started. |
| Blocked | Waiting on input, approval, access, or decision. |
| QA | Deliverable ready for review. |
| Ready for Delivery | QA passed and delivery packet prepared. |
| Delivered | Client update/deliverable sent through approved channel. |
| Accepted | Client accepted or acceptance window completed. |
| Closed | Internal closeout completed. |

## QA Gates

### Gate A: Scope Fit

- Deliverables match approved scope.
- Exclusions were not accidentally included.
- Assumptions are documented.
- Deviations have Order Owner approval.

### Gate B: Quality

- Output is complete and understandable.
- Formatting, naming, links, and files are clean.
- No placeholder text remains.
- Calculations and technical behavior are checked where relevant.

### Gate C: Safety And Privacy

- No secrets, credentials, payment details, or private data exposed.
- No internal-only links included unless approved.
- No public/production/billing/DNS/account mutation performed without approval.
- No legal, financial, medical, tax, or contractual commitment is made.

### Gate D: Delivery Readiness

- Delivery package includes promised items.
- Client-facing summary is accurate.
- Known limitations are disclosed.
- Next step is clear.
- Fulfillment record is updated.

## Client Update Drafts

Intake confirmation:

```text
We received your order for [offer]. We are reviewing the details and will confirm the fulfillment scope before production begins.

To continue, please send: [inputs].
```

Blocked on input:

```text
Work is currently blocked on [missing input/approval]. Once this is provided through the approved channel, we can continue from [next step].
```

Delivery note:

```text
The agreed deliverable is ready: [summary]. Please review [files/links] through the approved channel. Known limitations: [limitations]. Included revision path: [revision terms].
```

Closeout:

```text
The order is complete from our side. Internal closeout notes are recorded, and any future changes should be scoped separately.
```

