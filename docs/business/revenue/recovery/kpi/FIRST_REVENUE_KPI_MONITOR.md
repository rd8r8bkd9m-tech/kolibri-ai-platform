# First Revenue KPI Monitor 2026-07-02

Status: internal monitor template. This process must not send messages, charge payments, publish externally, sign contracts, or mutate accounts.

## Purpose

Track the first revenue motion daily so the owner can see proposal activity, replies, qualified leads, orders, booked revenue, delivery handoffs, blockers, and safety incidents.

## KPI Definitions

| KPI | Definition |
| --- | --- |
| Proposals drafted | Distinct proposal/order/offer drafts prepared but not sent. |
| Proposals sent | Intentional one-to-one sends through approved channel only. |
| Replies received | Substantive inbound replies; exclude bounces/receipts. |
| Qualified leads | Leads with need, fit, timing, buyer/next stakeholder, and known risk. |
| Orders booked | Commitments accepted under approved commercial process. |
| Revenue booked | Conservative amount tied to booked orders only. |
| Delivery handoffs | Booked orders handed to delivery with owner, scope, milestone, and risks. |
| Blockers | Active issue preventing progress. |
| Safety incidents | Legal, security, privacy, finance, customer trust, or operational risk. |

## Revenue Booking Rule

Count revenue only when all are true:

- customer or authorized buyer made a clear commitment through approved process;
- price, scope, and delivery expectation are recorded;
- required approval is complete;
- this monitor did not sign a contract;
- this monitor did not charge payment.

If uncertain, record as pipeline note, not booked revenue.

## Daily Update Template

```markdown
# Daily Revenue KPI Update

Date: YYYY-MM-DD
Prepared by:
Timezone: UTC

## Summary

One to three sentences on what changed today, most important movement, and highest-risk blocker.

## KPI Snapshot

| KPI | Today | Cumulative | Notes |
| --- | ---: | ---: | --- |
| Proposals drafted | 0 | Unknown |  |
| Proposals sent | 0 | Unknown |  |
| Replies received | 0 | Unknown |  |
| Qualified leads | 0 | Unknown |  |
| Orders booked | 0 | Unknown |  |
| Revenue booked | 0 | Unknown | Currency: RUB unless owner changes. |
| Delivery handoffs | 0 | Unknown |  |
| Active blockers | 0 | Unknown |  |
| Safety incidents | 0 | Unknown |  |

## Proposal Details

| Opportunity | Owner | Offer/scope | Status | Next action |
| --- | --- | --- | --- | --- |
|  |  |  | Drafted / Sent / Blocked |  |

## Replies

| Opportunity | Reply type | Summary | Owner | Next action |
| --- | --- | --- | --- | --- |
|  | Positive / Neutral / Negative / Question |  |  |  |

## Qualified Leads

| Lead | Qualification basis | Buyer/next stakeholder | Timing | Risk/disqualifier | Owner |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

## Orders And Revenue

| Order | Customer/opportunity | Booking basis | Revenue booked | Currency | Owner | Notes |
| --- | --- | --- | ---: | --- | --- | --- |
|  |  |  | 0 | RUB |  |  |

Booking check:

- Customer commitment recorded: Yes / No / Unknown
- Price, scope, delivery expectation recorded: Yes / No / Unknown
- Required approval complete: Yes / No / Not required / Unknown
- No contract signed by this monitor: Confirmed
- No payment charged by this monitor: Confirmed

## Delivery Handoffs

| Order | Delivery owner | Scope summary | Target date/milestone | Constraints | Risks |
| --- | --- | --- | --- | --- | --- |
|  |  |  | YYYY-MM-DD |  |  |

## Blockers

| Blocker | Impact | Owner | Next action | Due date | Status |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  | YYYY-MM-DD | Open |

## Safety Incidents

| Incident | Category | Impact | Containment | Escalation owner | Status |
| --- | --- | --- | --- | --- | --- |
|  | Legal / Security / Privacy / Finance / Customer trust / Operations / Other |  |  |  | Open |

## Decisions Needed

| Decision | Needed by | Owner | Options | Recommendation |
| --- | --- | --- | --- | --- |
|  | YYYY-MM-DD |  |  |  |

## Next-Day Priorities

1. 
2. 
3. 

## Guardrail Confirmation

- No paid actions performed.
- No contracts signed.
- No mass messages sent.
- Nothing published externally.
- No public accounts mutated.
- No secrets, credentials, payment details, or sensitive personal data exposed.
```

## Review Checklist

- KPI totals match detail rows.
- Revenue excludes speculative/unapproved pipeline.
- Orders meet booking rule.
- Delivery handoffs have owners and milestones.
- Blockers have next actions.
- Safety incidents include containment and escalation.
- No secrets, sensitive personal data, payment details, or contract-signing instructions appear.

