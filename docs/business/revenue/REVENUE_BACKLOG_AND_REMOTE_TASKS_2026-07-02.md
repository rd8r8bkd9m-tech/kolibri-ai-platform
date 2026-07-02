# Revenue Backlog And Remote Tasks 2026-07-02

## P0 Backlog

| ID | Task | Output | Owner approval needed before external action |
| --- | --- | --- | --- |
| REV-001 | Landing copy and static offer page | Draft page for Telegram AI bots, document automation, bot audit, API integration, Mini App/PWA | Yes, before publication if public. |
| REV-002 | Offer copy pack | Kwork/landing copy for 5 offers with packages, requirements, FAQ, exclusions | Yes, before public publish unless already covered by Kwork delegation. |
| REV-003 | CRM seed | Repo-local lead table with ICP, offer, fit, price, status, next action | No for internal research. |
| REV-004 | Proposal templates | 10 safe templates for Kwork and direct B2B | Yes, before sending externally. |
| REV-005 | Kwork Wave A refresh | Re-check current project availability and update prepared queue | No for research; yes before sending. |
| REV-006 | AI documents/estimates demo | Synthetic demo estimate, КП, invoice, PDF/screenshots | No if synthetic and local. |
| REV-007 | Order intake and factory routing templates | `INTAKE.md`, `SCOPE.md`, `FACTORY_TASK.md`, `DELIVERY_CHECKLIST.md`, `CLIENT_REPLY_DRAFTS.md` | No. |
| REV-008 | Public portfolio cases | 3 anonymized cases: Telegram bot, AI estimate, bot audit | Yes before public upload. |
| REV-009 | B2B pilot one-pager | Contractor/renovation AI estimates pilot | Yes before sending. |
| REV-010 | Payment policy draft | Future manual invoice/Kwork/subscription/payment boundaries | Yes before implementation. |

## Remote Task Pack

### P0_REVENUE_LANDING_AND_OFFER_COPY_2026_07_02

Objective: create a public-ready but unpublished landing page/copy package for the five priority offers.

Read first:

- `docs/business/revenue/OWNER_REVENUE_PACKET_2026-07-02.md`
- `docs/business/revenue/GO_TO_MARKET_14_DAY_PLAN_2026-07-02.md`
- `origin/p0/kwork-revenue-manager-2026-07-01:docs/business/kwork/KWORK_EXECUTABLE_AI_BOT_OFFERS.md`
- `remote/kolibriai-frontend/src/pages/EstimatesPage.tsx`

Deliver:

- `docs/business/revenue/landing/OFFER_LANDING_COPY.md`
- `docs/business/revenue/landing/OFFER_FAQ.md`
- `docs/business/revenue/landing/INTAKE_FORM_FIELDS.md`
- `docs/business/revenue/landing/PUBLICATION_CHECKLIST.md`

Constraints:

- No public publication.
- No payments.
- No external outreach.
- No claims of guaranteed sales or error-free AI.

### P0_REVENUE_CRM_AND_LEAD_QUEUE_2026_07_02

Objective: create repo-local CRM seed and refresh safe lead queue from existing Kwork docs.

Read first:

- `origin/p0/kwork-revenue-manager-2026-07-01:docs/business/kwork/KWORK_SEND_QUEUE_2026-07-01.md`
- `origin/p0/kwork-revenue-manager-2026-07-01:docs/business/kwork/KWORK_SAFE_CHAT_ONLY_AUTONOMY_POLICY.md`
- `docs/business/revenue/OWNER_REVENUE_PACKET_2026-07-02.md`

Deliver:

- `docs/business/revenue/crm/LEADS.md`
- `docs/business/revenue/crm/KWORK_WAVE_A_REFRESH.md`
- `docs/business/revenue/crm/DAILY_REVENUE_REPORT_TEMPLATE.md`

Constraints:

- Research only unless owner approves sending.
- No scraping that violates platform rules.
- No private client data in GitHub.

### P0_REVENUE_DEMO_ASSETS_AI_ESTIMATES_2026_07_02

Objective: create synthetic demo artifacts for the AI document/estimate offer.

Read first:

- `backend/estimate_engine.py`
- `backend/document_engine.py`
- `backend/pdf_engine.py`
- `backend/routes_v1.py`
- `remote/kolibriai-frontend/src/pages/EstimatesPage.tsx`

Deliver:

- `docs/business/revenue/demos/ai-estimates/DEMO_SCRIPT.md`
- `docs/business/revenue/demos/ai-estimates/SYNTHETIC_CLIENT_BRIEF.md`
- `docs/business/revenue/demos/ai-estimates/DELIVERY_CHECKLIST.md`
- screenshots or generated PDFs only if they contain synthetic data.

Constraints:

- Synthetic data only.
- No client data.
- No deployment or public upload.

### P0_REVENUE_ORDER_INTAKE_FACTORY_ROUTING_2026_07_02

Objective: create safe order intake templates and factory task envelope template for paid Kwork/B2B work.

Read first:

- `origin/p0/kwork-revenue-manager-2026-07-01:docs/business/kwork/KWORK_REVENUE_CONTROL_LEDGER_2026-07-01.md`
- `docs/superfactory/API_FIRST_CONTROL_FABRIC.md`
- `docs/superfactory/FULL_CONTROL_API_POLICY.md`
- `ops/factory_control.py`
- `ops/agent_host.py`

Deliver:

- `docs/business/revenue/orders/TEMPLATE_INTAKE.md`
- `docs/business/revenue/orders/TEMPLATE_SCOPE.md`
- `docs/business/revenue/orders/TEMPLATE_FACTORY_TASK.md`
- `docs/business/revenue/orders/TEMPLATE_DELIVERY_CHECKLIST.md`
- `docs/business/revenue/orders/TEMPLATE_CLIENT_REPLY_DRAFTS.md`

Constraints:

- Do not accept or start real client work.
- Do not include secrets.
- Do not route live tasks without owner/client scope confirmation.

## Sequencing

1. Run landing/offer copy and CRM/lead queue in parallel.
2. Run demo assets after offer copy selects exact positioning.
3. Run order intake/factory routing before accepting any paid implementation work.
4. Only after owner approval: publish/update public pages or send next Kwork proposals.
