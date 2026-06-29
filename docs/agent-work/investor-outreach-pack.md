# Kolibri Investor & First-Customer Outreach Pack

Дата подготовки: 2026-06-29
Роль: `investor_sales_operator`

Назначение: рабочий пакет для первых касаний с инвесторами, стратегическими
партнёрами и ранними B2B-клиентами Kolibri AI Platform. Пакет не содержит
выдуманных контактов, финансовых обещаний, инвестиционных условий или
непроверенных метрик traction.

## 1. One-Pager Draft RU

### Kolibri AI Platform

Kolibri AI Platform — русскоязычная AI-платформа и фабрика автономных агентов
для воспроизводимого, наблюдаемого и управляемого искусственного интеллекта.
Первый коммерческий wedge — строительные сметы, КП, договоры, акты, счета и
PDF-документы, где пользователю важны повторяемость расчёта, аудит строк и
понятная подписочная модель.

### Проблема

Большинство AI-продуктов сегодня выглядит как чат поверх модели: результат
может быть полезным, но его трудно воспроизвести, проверить, передать команде
и превратить в операционный процесс. В строительных сметах это особенно
болезненно: ошибки в объёмах, формулах, региональных коэффициентах и итогах
быстро превращаются в коммерческий риск.

### Решение

Kolibri строит не только интерфейс, а runtime: SPA/PWA для пользователя,
Control Plane для серверов, фабрику агентных задач, inter-agent feed, GitHub
контур для проверяемой работы, billing-контур и детерминированный сметный
движок. LLM помогает понять задачу и текст, а расчёты нормализуются и
пересчитываются вне модели.

### Первый продукт

Первый продуктовый сценарий — AI-сметчик для подрядчиков, ремонтных бригад,
проектных бюро и строительных компаний:

- генерация смет из естественного запроса;
- повторяемые итоги для одинаковых вводных;
- audit fingerprint расчёта;
- коммерческое предложение, договор, акт, счёт и PDF-пакет;
- тарифы Solo, Team, Studio;
- режим lead fallback, если платёжный провайдер ещё не подключён.

### Технологический слой

Kolibri включает:

- Control Plane и удалённые agent hosts;
- inter-agent API для событий, inbox и артефактов;
- проверяемые worktree/PR/CI процессы;
- детерминированный estimate engine с pricebook version;
- FormulaLM R&D как формульный слой поверх LLM для задач, где важны расчёты,
  валидный JSON и воспроизводимость;
- PWA/mobile-first путь и будущий GoMesh слой для инфраструктуры.

### Почему сейчас

Agentic AI быстро переходит от демо к операционным системам. Бизнесу нужны не
просто ответы, а контролируемые workflows: кто выполнил задачу, где артефакт,
какие проверки прошли, что можно повторить и как это монетизируется. Kolibri
начинает с вертикального рынка, где ценность проверяемости видна сразу, и
сохраняет возможность расширяться в другие workflow-heavy категории.

### Что уже можно показывать

- Репозиторий с backend/frontend/ops слоями.
- SPA/PWA chat-first интерфейс с Control panel.
- Billing планы Solo, Team, Studio и T-Банк integration path.
- Детерминированный тест: `100 м2 штукатурки в Татарстане` даёт стабильный
  `estimate_id`, регион, pricebook version и итог.
- PDF generation tests для смет и бизнес-документов.
- Control Plane, leases, heartbeat, inter-agent messages и factory status.
- Документация по фабрике, FormulaLM и investor thesis.

### Кому это интересно

- AI-native инвесторам в agentic systems, devtools и AI infrastructure;
- B2B SaaS инвесторам, которые понимают подписочные вертикальные продукты;
- ConstructionTech/PropTech инвесторам и стратегам;
- строительным компаниям, ремонтным сетям, проектным бюро и отделам продаж;
- банкам, marketplace и интеграторам, которым нужен AI-документный workflow.

### Ask

Investor ask: 30 минут discovery call, чтобы проверить thesis, показать demo и
согласовать, какие метрики нужны для следующего разговора.

Customer ask: 20 минут demo call на одном реальном, обезличенном сметном
сценарии; цель — понять, экономит ли Kolibri время подготовки сметы и
документов.

### Важная честная рамка

Kolibri не должен заявлять, что FormulaLM уже доказан как превосходящий LLM
подход. Корректная формулировка: FormulaLM — R&D-направление, где проверяются
метрики валидного JSON, точных итогов, стабильности ответа и воспроизводимости.
Все публичные claims должны быть привязаны к демонстрациям, тестам или
артефактам.

## 2. One-Pager Draft EN

### Kolibri AI Platform

Kolibri AI Platform is a Russian-language AI platform and autonomous-agent
factory for reproducible, observable and controllable AI workflows. The first
commercial wedge is construction estimating: estimates, commercial proposals,
contracts, completion acts, invoices and PDF document packs where calculation
repeatability, line-item auditability and subscription-based delivery matter.

### Problem

Most AI products still behave like a chat layer on top of a model. The output
may be useful, but it is difficult to reproduce, verify, assign to a team and
turn into an operating process. In construction estimating, this creates direct
commercial risk: mistakes in quantities, formulas, regional coefficients and
totals can break trust quickly.

### Solution

Kolibri is building a runtime, not just an interface: a user-facing SPA/PWA, a
server Control Plane, an autonomous-agent task factory, an inter-agent feed, a
GitHub-visible verification loop, billing infrastructure and a deterministic
estimate engine. The LLM helps understand the task and text; calculations are
normalized and recalculated outside the model.

### First Product

The first product scenario is an AI estimator for contractors, renovation
teams, design bureaus and construction companies:

- estimate generation from natural-language input;
- repeatable totals for identical inputs;
- calculation audit fingerprint;
- commercial proposal, contract, completion act, invoice and PDF pack;
- Solo, Team and Studio subscription tiers;
- lead fallback mode when the payment provider is not yet connected.

### Technology Layer

Kolibri includes:

- Control Plane and remote agent hosts;
- inter-agent API for events, inboxes and artifacts;
- verifiable worktree, PR and CI processes;
- deterministic estimate engine with pricebook versioning;
- FormulaLM R&D as a formula layer on top of LLMs for calculation-sensitive
  tasks, valid JSON and reproducibility;
- PWA/mobile-first delivery path and a future GoMesh infrastructure layer.

### Why Now

Agentic AI is moving from demos to operating systems. Businesses need more than
answers: they need workflows that show who did the work, where the artifact is,
which checks passed, what can be reproduced and how the value is monetized.
Kolibri starts with a vertical market where verifiability is immediately
valuable, while keeping the runtime extensible to other workflow-heavy
categories.

### Evidence Available Today

- Repository with backend, frontend and ops layers.
- Chat-first SPA/PWA with a Control panel.
- Solo, Team and Studio billing plans and T-Bank integration path.
- Deterministic test: `100 m2 plastering in Tatarstan` produces a stable
  estimate ID, region, pricebook version and total.
- PDF generation tests for estimates and business documents.
- Control Plane, leases, heartbeat, inter-agent messages and factory status.
- Documentation for the agent factory, FormulaLM and investor thesis.

### Target Audience

- AI-native investors focused on agentic systems, devtools and AI
  infrastructure;
- B2B SaaS investors familiar with vertical subscription products;
- ConstructionTech/PropTech investors and strategics;
- construction companies, renovation teams, design bureaus and sales teams;
- banks, marketplaces and integrators that need AI document workflows.

### Ask

Investor ask: a 30-minute discovery call to test the thesis, show the demo and
align on which metrics are needed for the next conversation.

Customer ask: a 20-minute demo call using one real, anonymized estimating
scenario; the goal is to learn whether Kolibri reduces time spent preparing
estimates and document packs.

### Honest Framing

Kolibri should not claim that FormulaLM has already been proven to outperform
LLMs broadly. Correct framing: FormulaLM is an R&D track evaluating valid JSON
rate, exact totals, output stability and reproducibility. Public claims should
be tied to demos, tests or artifacts.

## 3. Email Templates

### Email 1 — Investor Intro

#### RU Version

Subject A: Kolibri AI — управляемый agent runtime + первый вертикальный рынок

Subject B: Вопрос по agentic AI infrastructure

Здравствуйте, {first_name}.

Я строю Kolibri AI Platform: управляемый agent runtime с первым коммерческим
рынком в строительных сметах.

Гипотеза такая: agentic AI нужен не только чат-интерфейс. Командам нужны
воспроизводимые задачи, видимые артефакты, audit trail, billing и путь от demo
к операционному workflow. Kolibri объединяет SPA/PWA, Control Plane, фабрику
удалённых агентов, inter-agent feed, детерминированный сметный движок и
GitHub-visible контур проверки.

Первый клиентский сценарий — генерация строительных смет и документов.
Ключевой момент: расчёты нормализуются и пересчитываются вне модели, поэтому
одинаковые вводные могут давать стабильный проверяемый результат.

Я не рассылаю инвестиционные условия и не делаю массовый fundraising blast.
Ищу короткий 30-минутный discovery call с инвесторами, которым близки agentic
systems, vertical AI или B2B SaaS.

Будет ли уместно созвониться на следующей неделе?

С уважением,
{sender_name}

Optional footer:
Коммерческое/инвесторское сообщение. Если это неактуально, ответьте
"unsubscribe", и я не буду писать повторно.

#### EN Version

Subject A: Kolibri AI — controllable agent runtime + first vertical wedge

Subject B: Quick question on agentic AI infrastructure

Hi {first_name},

I am building Kolibri AI Platform: a controllable agent runtime with a first
commercial wedge in construction estimating.

The thesis is that agentic AI needs more than chat UI. Teams need reproducible
tasks, visible artifacts, audit trails, billing and a path from demo to
operating workflow. Kolibri combines a SPA/PWA, Control Plane, remote agent
factory, inter-agent feed, deterministic estimate engine and a GitHub-visible
verification loop.

The first customer-facing workflow generates construction estimates and
document packs. The important part is that calculations are normalized and
recomputed outside the model, so identical inputs can produce stable audited
outputs.

I am not sending a broad fundraising blast or attaching terms. I am looking for
a focused 30-minute discovery conversation with investors who understand
agentic systems, vertical AI or B2B SaaS.

Would it be worth a short call next week?

Best,
{sender_name}

Optional footer:
Commercial/investor outreach. If this is not relevant, reply "unsubscribe" and
I will not follow up.

### Email 2 — Strategic / ConstructionTech Partner

#### RU Version

Subject A: AI-сметы и пакеты документов для строительных workflow

Subject B: Kolibri demo для строительных смет

Здравствуйте, {first_name}.

Я готовлю первую волну партнёров и клиентов для Kolibri AI Platform.

Kolibri — AI workflow продукт для строительных смет и связанных документов:
смета, коммерческое предложение, договор, акт, счёт и PDF-пакет. Продукт
строится вокруг повторяемых расчётов и аудита строк, а не только генерации
текста.

В раннем demo можно показать:

- создание сметы из естественного запроса;
- детерминированный пересчёт итогов;
- audit fingerprint сметы;
- генерацию PDF и бизнес-документов;
- тарифы и lead capture flow.

Сейчас я ищу небольшое число команд, готовых проверить один реальный,
обезличенный сметный сценарий и честно сказать, экономит ли это время отдела
продаж, сметчика или проектной команды.

Будет ли {company_name} открыта к 20-минутному demo?

С уважением,
{sender_name}

Optional footer:
Коммерческое сообщение. Если это неактуально, ответьте "unsubscribe", и я не
буду писать повторно.

#### EN Version

Subject A: AI estimates and document packs for construction workflows

Subject B: Kolibri demo for construction estimates

Hi {first_name},

I am preparing the first partner/customer wave for Kolibri AI Platform.

Kolibri is an AI workflow product for construction estimates and related
documents: estimate, commercial proposal, contract, completion act, invoice and
PDF pack. The product is built around repeatable calculations and auditability,
not just text generation.

The early demo can show:

- natural-language estimate creation;
- deterministic recalculation of totals;
- audit fingerprint for the estimate;
- PDF/business document generation;
- subscription plans and lead capture flow.

I am looking for a small number of teams willing to test one real, anonymized
estimating scenario and give blunt feedback on whether this saves time for
sales, estimating or project teams.

Would {company_name} be open to a 20-minute demo?

Best,
{sender_name}

Optional footer:
Commercial outreach. If this is not relevant, reply "unsubscribe" and I will
not follow up.

### Email 3 — Follow-Up After No Reply

#### RU Version

Subject: Re: Kolibri AI

Здравствуйте, {first_name}.

Коротко напомню про Kolibri.

Причина, почему я решил написать: Kolibri решает операционную часть agentic AI
— не просто получить ответ от модели, а сделать workflow воспроизводимым,
проверяемым и связанным с реальными артефактами.

Для инвесторов я могу прислать короткий one-pager и показать текущие
продуктовые доказательства. Для строительных команд могу провести demo на
одном обезличенном сметном кейсе и зафиксировать, есть ли практический смысл
двигаться дальше.

Если сейчас не момент, всё в порядке. Закрыть вопрос здесь или лучше написать
кому-то другому?

С уважением,
{sender_name}

Optional footer:
Коммерческое/инвесторское сообщение. Если это неактуально, ответьте
"unsubscribe", и я не буду писать повторно.

#### EN Version

Subject: Re: Kolibri AI

Hi {first_name},

Quick follow-up on Kolibri.

The reason I thought this might be relevant: Kolibri is trying to solve the
operational side of agentic AI — not just generating an answer, but making the
workflow reproducible, auditable and connected to real artifacts.

For investors, I can share a concise one-pager and show the current product
evidence. For construction/customer teams, I can run a short demo on one
anonymized estimating case and capture whether the workflow is worth pursuing.

If now is not the right moment, no worries. Should I close the loop here, or is
there a better person to ask?

Best,
{sender_name}

Optional footer:
Commercial/investor outreach. If this is not relevant, reply "unsubscribe" and
I will not follow up.

## 4. CRM Fields

Use these fields before collecting real contacts. Do not invent contacts; every
row must have a source URL, event source, warm intro, or manual verification
note.

| Field | Type | Notes |
| --- | --- | --- |
| `record_id` | string | Internal CRM ID. |
| `record_type` | enum | `investor`, `strategic_partner`, `customer`, `advisor`, `press`, `other`. |
| `segment` | enum | See segmentation below. |
| `priority` | enum | `P0`, `P1`, `P2`, `P3`. |
| `company_name` | string | Fund, company, studio, contractor, bank, platform. |
| `person_name` | string | Leave blank until verified. |
| `role_title` | string | Partner, principal, founder, innovation lead, sales lead, etc. |
| `email` | string | Verified only; no guessed emails. |
| `linkedin_url` | URL | Optional verified profile. |
| `website_url` | URL | Company/fund/source URL. |
| `geo` | string | Country/region. |
| `language` | enum | `RU`, `EN`, `mixed`. |
| `thesis_fit` | multi-select | `agentic_ai`, `devtools`, `vertical_ai`, `constructiontech`, `proptech`, `b2b_saas`, `fintech`, `marketplace`, `enterprise_ai`. |
| `customer_fit` | multi-select | `contractor`, `renovation_team`, `design_bureau`, `construction_company`, `sales_department`, `integrator`, `bank`, `marketplace`. |
| `evidence_to_send` | multi-select | `one_pager`, `demo_video`, `repo_summary`, `estimate_test`, `pdf_pack`, `factory_note`, `formulalm_note`, `billing_note`, `financial_model`. |
| `compliance_status` | enum | `not_checked`, `ok_to_contact`, `needs_consent`, `do_not_contact`, `counsel_review`. |
| `source` | string | Where the record came from; must be non-empty. |
| `source_date` | date | Date source was checked. |
| `relationship_path` | enum | `warm_intro`, `inbound`, `event`, `public_email`, `existing_relationship`, `manual_research`. |
| `last_touch_at` | datetime | Last email/call/meeting. |
| `next_step_at` | datetime | Scheduled follow-up. |
| `status` | enum | `research`, `ready`, `sent_1`, `sent_2`, `replied`, `meeting_booked`, `not_fit`, `do_not_contact`, `closed`. |
| `last_message_template` | enum | `investor_intro`, `customer_partner_intro`, `follow_up`, `custom`. |
| `reply_summary` | text | Short neutral notes. |
| `meeting_notes` | text | Problems, objections, requested artifacts. |
| `objections` | multi-select | `too_early`, `no_traction`, `unclear_market`, `needs_security`, `needs_demo`, `pricing`, `integration`, `legal`, `not_focus`. |
| `requested_artifacts` | multi-select | Same list as `evidence_to_send` plus `deck`, `data_room`, `security_note`, `customer_case`. |
| `consent_or_opt_out` | enum | `none`, `consented`, `unsubscribed`, `bounced`, `objected`. |
| `owner` | string | CRM owner/operator. |
| `notes_private` | text | No secrets, no sensitive personal data. |

## 5. First-Wave Segmentation

### Wave 0 — Manual Validation

Goal: prove messaging before scale.

- Size: 10-15 total records.
- Mix: 5 investors/advisors, 5 construction/customer operators, 2-5 strategic
  ecosystem people.
- Source quality: warm intros, known relevant public profiles, existing
  relationships, events.
- Message style: highly manual, no automation beyond CRM tracking.
- Success criteria: 3+ replies, 2+ demo/discovery calls, clear objection list.

### Wave 1A — AI-Native Investors

Fit:

- agentic systems;
- AI infrastructure;
- devtools;
- workflow automation;
- applied/vertical AI.

Why they may care:

- Kolibri is runtime-first, with Control Plane, agents, observability and
  reproducible artifacts.
- The first vertical wedge makes the platform less abstract.

Evidence to attach:

- EN one-pager;
- architecture diagram or repo summary;
- factory note;
- deterministic estimate test;
- FormulaLM note framed as R&D, not proven moat.

Avoid:

- valuation claims;
- "proprietary model" claims unless there is evidence;
- any securities terms before counsel review.

### Wave 1B — ConstructionTech / PropTech Investors and Strategics

Fit:

- construction SaaS;
- estimating/tendering/procurement;
- real estate operations;
- marketplaces for contractors/services;
- document automation in construction.

Why they may care:

- The wedge maps to a concrete costly workflow.
- Deterministic estimates and document packs are easier to evaluate than
  generic AI productivity claims.

Evidence to attach:

- RU or EN one-pager depending on recipient;
- demo script;
- sample anonymized estimate;
- sample PDF document pack;
- short note on pricebook/version/audit.

Avoid:

- claiming regulatory-grade or accounting-grade estimates without audit;
- implying guaranteed cost accuracy in all regions.

### Wave 1C — First Customers: Contractors, Renovation Teams, Design Bureaus

Fit:

- small and medium contractors;
- renovation teams;
- sales departments preparing commercial proposals;
- project/design bureaus that need repeatable document packs.

Why they may care:

- Faster draft estimates and customer-facing documents.
- Repeatability and editable output reduce rework.
- Subscription tiers map to solo/team/studio usage.

Evidence to attach:

- RU one-pager or one-screen product note;
- 2-3 screenshots or short demo video;
- sample estimate and PDF pack;
- clear note that outputs require human review before sending to a client.

Avoid:

- over-technical agent factory pitch in the first email;
- investor language;
- broad "AI replaces estimator" positioning.

### Wave 1D — Banks, Marketplaces, Integrators

Fit:

- fintech/banks serving SMBs or construction businesses;
- marketplaces for ремонт/строительство;
- integrators building enterprise document workflows.

Why they may care:

- Kolibri can become an AI document workflow layer around a paid vertical use
  case.
- Billing, subscriptions and document generation are natural integration
  points.

Evidence to attach:

- strategic partner version of one-pager;
- API/product architecture summary;
- billing/lead capture note;
- data/privacy/security checklist draft.

Avoid:

- promising enterprise readiness before security review;
- sharing internal server details, private IPs, secrets or raw logs.

## 6. Evidence to Attach

Use attachments sparingly. The first email should usually include one attachment
or one link, not a full data room.

### Minimum Safe Evidence Pack

1. One-pager RU/EN.
2. 60-120 second demo video or 5 screenshot sequence.
3. Sample anonymized estimate JSON and PDF.
4. Short architecture note: SPA/PWA, backend, Control Plane, agent hosts.
5. Test excerpt showing deterministic estimate behavior.

### Investor Evidence Pack

- One-pager EN.
- 8-10 slide deck after interest is confirmed.
- Repo summary without secrets.
- Factory/Control Plane note.
- Deterministic estimate test summary.
- FormulaLM research note with honest methodology and blockers.
- Product roadmap.
- Financial model draft with assumptions clearly labelled.
- Data room index, not raw dump.

### Customer Evidence Pack

- RU one-pager or product note.
- Demo video/screenshots.
- Sample estimate and PDF pack.
- Pricing/tariff page or summary:
  - Solo: up to 30 estimates/month.
  - Team: up to 150 estimates/month.
  - Studio: unlimited operational contour / custom onboarding framing.
- Human review disclaimer for customer-facing documents.

### What Not To Attach Yet

- Secrets, env files, tokens, private server addresses.
- Raw customer documents.
- Unredacted logs.
- Internal local absolute paths.
- Claims about revenue, customers, model performance or valuation unless
  already evidenced.
- Securities terms, SAFE drafts or cap table unless counsel-approved and the
  recipient is intentionally in a fundraising process.

## 7. Outreach Operating Rules

- No invented contacts.
- No guessed emails.
- Every CRM row needs a source.
- First wave is manual and low-volume.
- Use one clear ask per email.
- Attach evidence only if it matches the segment.
- Track opt-outs immediately.
- Keep investor and customer messaging separate.
- Do not imply that a customer demo is an investment solicitation.
- Do not imply that an investor intro is a commercial product purchase request.
- Sanitize repo screenshots before sharing.
- Keep product claims tied to current artifacts and tests.

## 8. Compliance Caveats

This section is operational guidance, not legal advice. Counsel should review
fundraising materials, securities-offering language, privacy posture and
cross-border marketing before scaled outreach.

### Investor Outreach / Securities

- Do not include investment terms, valuation, allocation, minimum check, return
  projections or urgency language in cold emails unless counsel has approved the
  fundraising path.
- If using a U.S. private offering framework, distinguish between private
  outreach and general solicitation. Under SEC Rule 506(c), broad solicitation
  can be allowed only with conditions such as accredited-investor purchasers and
  reasonable verification. Rule 506(b) has different limits, including no
  general solicitation.
- If a sale occurs under relevant SEC exemptions, Form D and state notice
  requirements may apply.
- Keep all performance and traction statements evidence-backed.
- Do not send data-room access automatically. Gate it behind relevance,
  identity checks and NDA where appropriate.

Official references checked 2026-06-29:

- SEC Rule 506(c) overview:
  https://www.sec.gov/resources-small-businesses/exempt-offerings/general-solicitation-rule-506c
- Investor.gov Rule 506 overview:
  https://www.investor.gov/introduction-investing/investing-basics/glossary/rule-506-regulation-d

### Commercial Email

- For U.S. commercial email, CAN-SPAM applies to B2B commercial messages as
  well as bulk campaigns. Use accurate sender/header information, truthful
  subjects, a physical postal address and a clear opt-out path; honor opt-outs.
- Do not use deceptive subject lines like "Re:" unless there was an actual prior
  thread.
- Keep unsubscribe/opt-out handling in CRM.
- Avoid purchased lists for Wave 0/Wave 1; use warm intros, public business
  contacts and manually verified relevance.

Official reference checked 2026-06-29:

- FTC CAN-SPAM business guide:
  https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business

### Marketing Claims

- FTC guidance expects advertising claims to be truthful, non-deceptive and
  evidence-based.
- Do not claim "guaranteed accuracy", "fully autonomous legal documents",
  "best-in-class", "proven superior to LLMs", or "enterprise-ready security"
  unless supporting evidence exists and the scope is clear.
- Testimonials, logos and customer names require permission.
- Any comparison with competitors needs substantiation.

Official references checked 2026-06-29:

- FTC advertising and marketing basics:
  https://www.ftc.gov/business-guidance/advertising-marketing
- FTC advertising substantiation policy:
  https://www.ftc.gov/legal-library/browse/ftc-policy-statement-regarding-advertising-substantiation

### Privacy / EU-UK Style Direct Marketing

- If outreach touches EU/UK individuals, confirm lawful basis and electronic
  marketing rules before sending.
- For UK guidance, direct marketing may sometimes rely on legitimate interests,
  but this is not automatic; a necessity and balancing assessment is required,
  and PECR can require consent in some channels.
- Corporate subscriber rules can differ from individual subscriber rules.
- Keep data minimization: name, role, company, business contact source,
  outreach status and opt-out state are usually enough for early CRM.

Official references checked 2026-06-29:

- ICO direct marketing lawful basis:
  https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/sending-direct-marketing-choosing-your-lawful-basis/
- ICO legitimate interests guidance:
  https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/legitimate-interests/when-can-we-rely-on-legitimate-interests/

## 9. First Outreach Checklist

Before sending:

- CRM record has source and segment.
- Recipient relevance is manually checked.
- Email template is customized with one specific reason.
- No investment terms in the body.
- Claims match attached evidence.
- Physical address / compliant footer is available for commercial emails.
- Opt-out field exists.
- Attachments are sanitized.
- Follow-up date is set.

After sending:

- Update status to `sent_1`.
- Record exact template and evidence sent.
- If no reply after 4-7 business days, send Email 3 once.
- If no reply after follow-up, close as `no_response` or move to later nurture.
- If opt-out, mark `do_not_contact` immediately.

## 10. Suggested Artifact List

Create or assemble next:

1. `one-pager-ru.pdf` and `one-pager-en.pdf`.
2. `kolibri-demo-90s.mp4` or screenshot sequence.
3. `sample-estimate-anonymized.json`.
4. `sample-estimate-anonymized.pdf`.
5. `sample-document-pack.pdf`.
6. `architecture-note-public.md`.
7. `factory-evidence-note.md`.
8. `formulalm-research-note.md`.
9. `billing-and-pricing-note.md`.
10. `data-room-index.md`.
11. `crm-template.csv`.
12. `compliance-review-checklist.md`.
