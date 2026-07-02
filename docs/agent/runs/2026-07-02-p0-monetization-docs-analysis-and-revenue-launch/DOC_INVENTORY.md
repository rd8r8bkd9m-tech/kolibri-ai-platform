# Revenue Source Index 2026-07-02

Purpose: index every project source found during the monetization scan that is relevant to money, clients, offers, products, tariffs, sales, estimates, SaaS, Telegram, Control Center, Agent Factory, API, subscriptions, services, B2B/B2C, or other monetization paths.

## Checkout Note

The requested workspace path was empty. The actual project repository used for this scan is `/var/lib/kolibri-agent/repo`.

The current checkout has unrelated local changes in product/runtime files. This scan did not modify them.

## Primary Commercial Sources

| Source | Why it matters | Revenue signal |
| --- | --- | --- |
| `origin/p0/kwork-revenue-manager-2026-07-01:docs/business/kwork/KWORK_SERVICE_CATALOG.md` | Catalog of fixed-scope Kwork services. | 10 sellable service directions: Telegram AI bot, AI automation, landing, audit, document assistant, data automation, API/webhook, code review, AI MVP, AI-agent prompts. |
| `origin/p0/kwork-revenue-manager-2026-07-01:docs/business/kwork/KWORK_PRICE_PACKAGES_2026-07-01.md` | Live Kwork price scan and package ranges. | Starter/Standard/Advanced ranges from 5 000 RUB to 180 000 RUB depending on offer. |
| `origin/p0/kwork-revenue-manager-2026-07-01:docs/business/kwork/KWORK_14_DAY_REVENUE_SPRINT.md` | Operating plan for first revenue. | Narrow offers, daily proposal routine, trust-building path for low-review account. |
| `origin/p0/kwork-revenue-manager-2026-07-01:docs/business/kwork/KWORK_EXECUTABLE_AI_BOT_OFFERS.md` | Offers that can be executed now. | Safe commercial menu for bots, docs, support, integrations, Mini App/PWA, audit, prompt packs. |
| `origin/p0/kwork-revenue-manager-2026-07-01:docs/business/kwork/KWORK_REVENUE_CONTROL_LEDGER_2026-07-01.md` | Public-action ledger and current Kwork state. | First public Kwork exists, one proposal sent, public-action gates recorded. |
| `origin/p0/kwork-revenue-manager-2026-07-01:docs/business/kwork/KWORK_SAFE_CHAT_ONLY_AUTONOMY_POLICY.md` | Defines allowed and forbidden revenue actions. | Allows safe Kwork-only negotiation and routing to factory; blocks payout/bank/tax/security/off-platform actions. |
| `origin/p0/kwork-revenue-manager-2026-07-01:docs/business/kwork/KWORK_SEND_QUEUE_2026-07-01.md` | Prepared lead queue. | 25 Kwork projects classified into waves, with one proposal already sent. |
| `origin/p0/kwork-revenue-manager-2026-07-01:docs/business/kwork/KWORK_RISK_AND_RULES.md` | Marketplace safety policy. | No spam, fake reviews, fake portfolio, off-platform payment, or unrealistic promises. |
| `origin/p0/kwork-revenue-manager-2026-07-01:docs/business/kwork/KWORK_FIRST_KWORK_READY_TO_PASTE.md` | First published Kwork copy and package. | Telegram AI bot offer: observed public buyer price 9 000 RUB, 3 days. |

## Product And Asset Sources In Current Checkout

| Source | Why it matters | Revenue signal |
| --- | --- | --- |
| `README.md` | Platform inventory. | Existing FastAPI backend, React frontend, factory control, Telegram gateway, mesh bridge, tests. |
| `backend/estimate_engine.py` | Deterministic estimate engine. | AI/document estimate product core: line items, prices, totals, audit fingerprint, prompt-to-estimate seed. |
| `backend/document_engine.py` | Commercial document generator. | Creates commercial offers, contracts, acts, invoices from estimates. |
| `backend/pdf_engine.py` | PDF generation for estimates and business documents. | Delivery-ready artifact generator for documents. |
| `backend/routes_v1.py` | v1 estimates API. | CRUD, calculate, duplicate, CSV/JSON export, PDF stub, AI audit/fix endpoints, seed estimate. |
| `remote/kolibriai-frontend/src/pages/EstimatesPage.tsx` | Estimate editor UI. | Professional mobile-ready estimate workspace with AI audit, save/calculate, CSV/PDF links. |
| `backend/tests/test_estimate_document_pdf_engines.py` | Regression tests. | Verifies deterministic totals, document pack, PDF generation. |
| `docs/agent/runs/2026-07-02-p1-kolibriai-ru-mobile-uiux-production-hardening/*` | QA evidence for frontend hardening. | Build passed; mobile estimate editor production hardening documented. |

## Telegram, Mini App, Control Center Sources

| Source | Why it matters | Revenue signal |
| --- | --- | --- |
| `docs/product/telegram-command-center/2026-07-01/COMMAND_CENTER_SPEC.md` | Command Center product spec. | Telegram-native owner/operator surface for dispatch, task board, fleet, agents, models, PR/CI, artifacts, settings. |
| `docs/product/telegram-command-center/2026-07-01/IMPLEMENTATION_SLICES.md` | PR-sized delivery plan. | Auth, read APIs, Mini App shell, composer, safe actions, artifacts, rich messages, streaming. |
| `docs/product/telegram-command-center/2026-07-01/NEXT_TASK_PROMPTS.md` | Next remote task. | Owner auth contract is already queued as the next implementation step. |
| `docs/telegram-superfactory.md` | Telegram gateway and Mini App runtime contract. | Telegram messages become Control Plane task envelopes; Mini App uses superfactory status/task/artifact endpoints. |
| `frontend/public/telegram-miniapp.html` | Mini App entry. | Existing asset for Telegram/Mini App demos and future productization. |
| `ops/telegram_gateway.py` | Owner-facing Telegram command/chat integration. | Demonstrable Telegram automation capability for client bots and internal factory control. |
| `ops/telegram_superfactory.py` | Superfactory planning/runtime helpers. | Runner policy and initData validation helpers for Mini App/control workflows. |

## API, Agent Factory, SaaS-Like Infrastructure Sources

| Source | Why it matters | Revenue signal |
| --- | --- | --- |
| `docs/superfactory/API_FIRST_CONTROL_FABRIC.md` | API-first architecture. | Foundation for B2B agent factory/API product and owner control plane. |
| `docs/superfactory/FULL_CONTROL_API_POLICY.md` | Security and role policy. | B2B trust story: authenticated, authorized, traceable, scoped, redacted. |
| `docs/superfactory/TASKS.md` | Superfactory roadmap. | Fleet guardian, API-first fabric, logical-agent scheduler, business/revenue engine. |
| `ops/factory_control.py` | Redis-backed control plane. | Queue, leases, node heartbeat, task lifecycle; internal delivery automation. |
| `ops/agent_host.py` | Agent runner host. | Remote task execution, artifacts, review tasks; foundation for delivery factory. |
| `backend/factory_status.py` | Normalized factory status. | Frontend/Control Center status product component. |
| `infra/network/api.py` | Unified API/organism prototype. | Routes tasks across nodes; productizable architecture proof. |

## Revenue-Relevant Constraints Found

- Money actions in Telegram Command Center are disabled unless a separate owner-approved payments policy exists.
- Kwork safe autonomy allows Kwork-only proposals, negotiation, stage updates, request/order intake, and factory routing, but forbids payout, bank, tax, passport, password, 2FA, security settings, off-platform payment/contact, spam, fake claims, and rule bypass.
- This revenue launch must not spend money, sign contracts, mutate payment settings, or do mass external outreach without separate owner confirmation.
