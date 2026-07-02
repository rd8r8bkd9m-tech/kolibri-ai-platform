# Owner Revenue Packet 2026-07-02

## Executive Decision

Kolibri can start earning fastest by selling narrow implementation services that reuse already-built assets, not by selling the whole Superfactory as a platform on day one.

Best immediate wedge:

1. Telegram AI bots for leads/FAQ/support.
2. AI assistant for documents, КП, estimates, acts, reports.
3. Audit and repair of existing Telegram/AI bots.
4. API/webhook/CRM/table integration around a bot.
5. One-screen Telegram Mini App/PWA for an existing bot.

The Superfactory, Fabric API, Control Center, agent hosts and fleet are the delivery engine and trust proof. They should be shown as capability, but packaged as clear buyer outcomes.

## What Already Exists

### Commercial Motion

- Kwork revenue branch exists: `origin/p0/kwork-revenue-manager-2026-07-01`.
- First Telegram AI bot Kwork was published on 2026-07-01.
- Observed public buyer price: 9 000 RUB.
- One safe Kwork proposal was sent for an AI call-analysis MVP at 60 000 RUB / 10 days.
- Kwork safe-chat-only autonomy policy exists and gives boundaries for proposals, negotiation, intake and factory routing.
- 25 Kwork leads were already classified into Wave A/B/C.
- Portfolio assets exist on the Kwork branch.

### Product Assets

- AI estimate engine: deterministic line totals, overhead/tax, audit fingerprint.
- Business document engine: commercial offer, contract, completion act, invoice.
- PDF generation for estimates/documents.
- v1 estimates API: list, create, update, calculate, duplicate, export CSV/JSON, PDF stub, AI audit/fix.
- Estimate editor UI: mobile-hardened professional surface with client/object/region, line items, status, AI audit, save/calculate, CSV/PDF actions.
- Telegram gateway and Mini App contracts.
- Factory Control Plane and Agent Host for remote execution.
- API-first Fabric docs and security policy.

## What Can Be Sold Quickly

| Offer | Readiness | Why sell now | First package |
| --- | --- | --- | --- |
| Telegram AI bot for leads/FAQ | Ready enough | Kwork offer already exists; gateway code proves capability. | 9 000-15 000 RUB starter, 3-5 days. |
| AI bot for documents, КП, estimates | Ready enough | Estimate/document/PDF engines exist; strong ICP pain. | 10 000-20 000 RUB starter, 3-5 days. |
| Existing bot audit/repair | Ready | Low risk, fast delivery, good first-review path. | 5 000-12 000 RUB starter, 1-3 days. |
| API/webhook integration | Ready with scope limits | Existing backend/API/factory experience; common buyer demand. | 15 000-35 000 RUB standard, 3-7 days. |
| Telegram Mini App/PWA prototype | Partly ready | Mini App concepts and frontend assets exist; needs tight scope. | 12 000-25 000 RUB starter, 3-6 days. |
| Control Center for teams | Not first sale | Strong internal asset, but too large for cold buyers. | Sell as paid audit/spec first: 30 000-90 000 RUB. |
| Agent Factory / API SaaS | Future | Needs packaging, auth, billing, docs, support policy. | Begin as B2B pilot, not self-serve SaaS. |

## ICP

### ICP 1: Service Businesses With Telegram Leads

Examples: repair, installation, clinics, education, consulting, local services.

Pain: missed messages, repeated questions, no structured intake.

Offer: Telegram AI bot for заявки and FAQ with manager handoff.

Proof asset: published Kwork, Telegram gateway, bot flow portfolio.

### ICP 2: Construction, Renovation, Engineering, Fit-Out

Pain: estimates, КП, invoices and acts are slow and error-prone.

Offer: AI assistant for estimates and commercial documents.

Proof asset: `backend/estimate_engine.py`, `backend/document_engine.py`, `backend/pdf_engine.py`, `EstimatesPage.tsx`.

### ICP 3: Small Teams With Existing Broken Bots

Pain: bot works poorly, no handoff, bad prompts, integration bugs.

Offer: audit/repair report plus small fix.

Proof asset: Kwork audit offer, tests, bot/runtime code.

### ICP 4: Teams That Need Bot To CRM/Table/API Handoff

Pain: leads stay in chat and are not routed.

Offer: one API/webhook/Google Sheets/CRM integration.

Proof asset: FastAPI backend, route contracts, webhook/API experience.

### ICP 5: Founders Testing AI MVPs

Pain: idea is too big; need a testable prototype.

Offer: AI MVP spec/prototype, Mini App/PWA, or backend skeleton.

Proof asset: Kolibri Platform, Fabric API, Control Center specs.

## Pricing Guardrails

Use fixed-scope prices and avoid broad "anything with AI" promises.

| Direction | Starter | Standard | Advanced |
| --- | ---: | ---: | ---: |
| Telegram AI bot | 7 000-12 000 RUB | 18 000-30 000 RUB | 40 000-70 000 RUB |
| Documents/КП/estimates bot | 10 000-20 000 RUB | 25 000-60 000 RUB | 70 000-160 000 RUB |
| Knowledge-base support bot | 8 000-18 000 RUB | 20 000-45 000 RUB | 55 000-120 000 RUB |
| Mini App/PWA | 12 000-25 000 RUB | 30 000-75 000 RUB | 90 000-180 000 RUB |
| Bot audit/repair | 5 000-12 000 RUB | 15 000-35 000 RUB | 45 000-100 000 RUB |

Source: Kwork price package doc from `origin/p0/kwork-revenue-manager-2026-07-01`. Re-check live Kwork competitors before publishing additional offers.

## Channels

1. Kwork: immediate, already started, use safe-chat-only policy.
2. Warm direct B2B: owner-approved only, no mass outreach; start with manual short list and individual messages after approval.
3. Public landing: use as trust surface and intake, not as paid acquisition yet.
4. Telegram channel/bot demo: show controlled demos and portfolio without client data.
5. GitHub/docs evidence: selectively translate into public case studies without secrets.

## Safety Gates

Allowed now:

- Create internal revenue docs.
- Prepare landing copy, offer copy, CRM seed fields and lead research tasks.
- Prepare Kwork proposals and remote tasks.
- Route accepted Kwork work into factory after scope is clear.

Not allowed without separate owner confirmation:

- Spend money.
- Sign contracts or accept external legal terms.
- Touch payout, bank, tax, passport, password, 2FA or account-security settings.
- Send mass external outreach.
- Move communication/payment outside Kwork when using Kwork.
- Enable Telegram payments/Stars/subscriptions/invoices.
- Promise guaranteed revenue, guaranteed ranking, guaranteed conversion or fully error-free AI.

## Owner Decisions Needed

1. Approve whether the next public offer should be `AI bot for documents, КП and estimates` or `bot audit/repair`.
2. Approve whether to continue Kwork proposal Wave A from the existing queue.
3. Approve landing copy publication path: current frontend, separate static page, or docs-only draft first.
4. Approve a CRM location: repository markdown/CSV first, then Airtable/Notion/Sheets only if owner wants external tooling.
