# Pricing Experiments 2026-07-02

Status: internal draft. Do not mutate live prices, paid flows, subscriptions, or public offers without owner approval.

## Baseline From Monetization Package

Immediate sellable offers should stay fixed-scope and outcome-based:

| Direction | Starter | Standard | Advanced |
| --- | ---: | ---: | ---: |
| Telegram AI bot | 7 000-12 000 RUB | 18 000-30 000 RUB | 40 000-70 000 RUB |
| Documents/КП/estimates bot | 10 000-20 000 RUB | 25 000-60 000 RUB | 70 000-160 000 RUB |
| Knowledge-base support bot | 8 000-18 000 RUB | 20 000-45 000 RUB | 55 000-120 000 RUB |
| Mini App/PWA | 12 000-25 000 RUB | 30 000-75 000 RUB | 90 000-180 000 RUB |
| Bot audit/repair | 5 000-12 000 RUB | 15 000-35 000 RUB | 45 000-100 000 RUB |

For first revenue, use pricing as a hypothesis. Do not overfit early signals from one lead, one view count, or one reply.

## Package Architecture

### Starter

Purpose: low-friction first order and review path.

Use when:

- buyer is price-sensitive;
- scope is narrow;
- proof/reviews are still limited.

Must include:

- one scenario, template, or workflow;
- clear input requirements;
- test checklist;
- exclusions for paid APIs, hosting, domains, account mutation, and complex integrations.

### Standard

Purpose: default commercial target.

Use when:

- buyer has a real workflow and enough context;
- one integration or stronger document flow is needed;
- expected value justifies more QA and handoff work.

Must include:

- fixed deliverables;
- owner/client review gate;
- handoff documentation;
- explicit revision limit.

### Advanced

Purpose: high-intent buyers with broader implementation needs.

Use when:

- multiple workflows, integrations, or screens are required;
- support, monitoring, or stronger QA is needed;
- project can be staged safely.

Must include:

- phase plan;
- assumptions and exclusions;
- delivery milestones;
- risk register.

## Safe Experiments

| Experiment | Hypothesis | Safe setup | Decision signal |
| --- | --- | --- | --- |
| Three-tier table vs one offer | A tier table clarifies buying and increases qualified replies | Change presentation only; keep actual prices unchanged | More qualified inquiries, no confusion complaints |
| Standard as recommended | Highlighting Standard raises average order value | Same prices, clearer "best fit" label | Higher Standard selection without reply drop |
| Audit-first wedge | Bot audit/repair converts faster for low-trust first account | Offer audit as entry product | Replies/orders vs implementation offer |
| Documents/estimates wedge | Existing product assets make document automation the strongest second offer | Publish/stage only after approval | Qualified leads in construction/service ICP |
| Fixed delivery windows | 3-5 day starter is more credible than vague turnaround | Show realistic windows by package | Fewer scope questions, better acceptance |
| Optional add-ons | Separating integration/PDF/hosting avoids underpricing | List add-ons as approval-scoped | Fewer hidden-scope requests |

## Decision Rules

Primary metric:

- booked revenue per qualified opportunity, not raw views.

Secondary metrics:

- proposal reply rate;
- qualified lead rate;
- order acceptance rate;
- average ticket;
- delivery time;
- revision/support load;
- refund/dispute/safety incident count.

Pass criteria:

- primary metric improves by at least 10-15% or the qualitative signal is clearly stronger for low sample size;
- no increase in buyer confusion, refund pressure, scope creep, or unsafe requests;
- delivery load remains feasible.

Stop criteria:

- repeated buyer confusion about what is included;
- requests cluster around excluded work;
- pricing causes pressure for off-platform payment, fake discounts, or unrealistic deadlines;
- support/delivery load exceeds capacity;
- any public/legal/payment/compliance risk appears.

## Guardrails

- No fake discounts, fake scarcity, or invented "was" prices.
- No hidden mandatory fees.
- No guaranteed revenue, ranking, conversion, moderation, or perfect AI claims.
- No live price change without owner approval and rollback plan.
- No payment/subscription/billing implementation in this experiment.
- Re-check live marketplace competitors before external publication.

## First Recommended Test

Start with docs-only or unpublished offer presentation:

1. `Documents/КП/estimates assistant` as the recommended second Kwork offer.
2. `Bot audit/repair` as the lower-risk starter.
3. Use three tiers but publish only one approved package if the channel requires simplicity.
4. Track replies and qualified leads in the KPI monitor before changing prices.

