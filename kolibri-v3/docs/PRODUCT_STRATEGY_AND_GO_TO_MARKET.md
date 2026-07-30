# Kolibri: product strategy, first vertical and go-to-market

- Status: product baseline
- Date: 2026-07-30
- Platform product: Kolibri universal agent workspace
- First commercial vertical: `construction.estimates`
- Existing production: `https://kolibriai.ru/app`
- Production R1 update target: 2026-08-06

## 1. Executive decision

Kolibri is not a construction application that may later be generalized.
Kolibri is a universal, multi-tenant agent platform whose first paid product is
the construction-estimate vertical pack.

This distinction is a product and architecture constraint:

```text
Kolibri Platform
  = identity + projects + chat + agents + files + artifacts + approvals
    + durable runs + mobile shell + billing boundary

Construction Estimates
  = estimate domain + normative/price sources + calculation kernel
    + estimate editor + specialist agents + domain documents
```

The initial public promise must nevertheless be narrow. A buyer pays for a
resolved construction problem, not for a generic platform. Therefore:

- the company story is a universal agent operating system for professional
  work;
- the first sales story is faster, verifiable construction estimates;
- the architecture stays universal;
- the launch experience is intentionally construction-specific for entitled
  tenants;
- future verticals reuse the Core and add a versioned, policy-bound pack.

## 2. Product thesis

### 2.1. Long-term thesis

Professional software will become a combination of:

1. a conversational and mobile workspace;
2. durable agents that can perform long-running work;
3. deterministic domain engines;
4. governed source data;
5. human approval and an audit trail;
6. documents and integrations accepted by the existing industry.

Kolibri owns the reusable workspace and execution layer. A vertical pack owns
the domain truth.

### 2.2. First commercial wedge

The construction wedge is attractive because estimate preparation combines:

- unstructured inputs: drawings, specifications, PDFs, spreadsheets and chat;
- repetitive expert work;
- deterministic arithmetic;
- changing price and normative sources;
- costly errors;
- review, revision and formal document output;
- collaboration between office and site.

It is therefore a demanding validation of the platform rather than a special
case embedded into the Core.

### 2.3. The first job to be done

> From project files and user clarification, prepare a reviewable commercial
> construction estimate with explicit quantities, prices, source evidence,
> calculation version and export, then revise it without losing history.

The first release should solve this one job end-to-end. It should not claim to
replace every regulated workflow of 1C or GRAND before compatibility and
compliance evidence exist.

## 3. Beachhead market

### 3.1. Primary ideal customer profile

The first design partners should be:

- small and medium contractors or fit-out companies;
- one to five people regularly preparing commercial estimates;
- source documents arriving through PDF, XLSX, images and messaging;
- an owner, commercial director or chief estimator who feels the turnaround
  and correction cost directly;
- willingness to review output rather than blindly delegate financial
  responsibility to AI.

This segment can adopt a web product without a long enterprise integration,
while still having frequent, monetizable work.

### 3.2. Secondary early segment

- independent estimators;
- construction consultants;
- small design-and-build teams;
- internal estimate teams that may use Kolibri before exporting into their
  incumbent system.

### 3.3. Deliberately later segments

- state procurement and expert-review workflows;
- large developers requiring ERP/BIM/SSO/data-residency integration;
- organizations requiring complete regulated estimate-method parity on day
  one;
- medical or other regulated verticals.

They are important expansion markets, but poor first-week launch targets.

## 4. Competitive strategy

### 4.1. Verified incumbent baseline

The comparison below uses official product information as of 2026-07-30.

| Capability | 1C:Estimate | GRAND-Estimate | Kolibri strategy |
|---|---|---|---|
| Local, object and consolidated estimates | Mature incumbent capability | Mature incumbent capability | Build compatibility progressively; do not claim parity in R1 |
| Basic, resource, basic-index and resource-index methods | Supported | Supported, including FSNB-2022 RIM | Deterministic engine roadmap; first release focuses on a verified commercial estimate |
| FSIS CS/normative bases | Supported through product data flows | Supported through product databases and updates | Use only licensed/approved sources with provenance and effective dates |
| KS-2, KS-3, M-29 and formal outputs | Supported | Broad professional document workflow | Add through versioned templates only after fixture and expert acceptance |
| Industry exchange formats | ARPS, EstML, KENML, `gsfx` and other exchanges are listed | XML/GGE and professional exports are supported | Import/export compatibility is a primary adoption feature, not an afterthought |
| Accounting/ERP/BIM ecosystem | Strong 1C and Renga position | Established estimate ecosystem | Integrate and coexist first; replace only where evidence supports it |
| Agentic intake from mixed files | Not the primary incumbent interaction model | Not the primary incumbent interaction model | Initial differentiation |
| Mobile conversational workflow | Not the core product advantage | “Mobile” offer is a portable keyed desktop edition | Mobile Safari plus later native iOS/Android is an initial differentiation |
| Durable autonomous work with user approval | Not the primary product model | Not the primary product model | Core platform advantage |
| Transparent evidence per generated result | Varies by workflow | Strong domain data, traditional UI | Make source, engine and approval evidence a first-class artifact |

Official references:

- [1C:Estimate capabilities](https://solutions.1c.ru/catalog/smeta3/features)
- [1C:Estimate acquisition and current list prices](https://solutions.1c.ru/catalog/smeta3/buy)
- [GRAND-Estimate program and database prices](https://shop.grandsmeta.ru/produkty/programmnoe-obespechenie/pokupka-programmy)
- [GRAND-Estimate resource-index method](https://www.grandsmeta.ru/tekstovye-materialy/posobie-v-tekstovom-vide/vvedenie)
- [Ministry of Construction pricing and FSNB materials](https://minstroyrf.gov.ru/trades/tsenoobrazovanie/)
- [GGE XML/IFC validation service](https://checkxml.gge.ru/)

### 4.2. Positioning

Kolibri should not start with “another estimate table.” Its position is:

> Kolibri turns project materials and expert clarification into a traceable
> estimate and keeps the agent, reviewer, revisions and documents in one
> workspace.

The product competes on workflow time, clarity and mobility first. It earns
the right to compete on full replacement later through calculation,
normative, document and exchange-format parity.

### 4.3. Land, coexist, expand, replace

1. **Land** — create and revise a commercial estimate from mixed inputs.
2. **Coexist** — import from and export to the customer’s existing workflow.
3. **Expand** — team review, source policy, versions, acts, price monitoring,
   reusable company catalogs and integrations.
4. **Replace selectively** — only after the customer’s required methods,
   forms, databases and exchange formats pass an explicit acceptance matrix.

This reduces migration risk and creates a credible path to direct competition
with 1C and GRAND.

## 5. Product package

### 5.1. Universal Core included for every tenant

- secure browser and device identity;
- tenants, users, roles and entitlements;
- projects, threads and searchable history;
- durable agent runs, progress, cancel, retry and resume;
- attachments and generic artifact library;
- typed A2A assignments;
- approvals and audit events;
- web/mobile shell, theme and accessibility;
- usage metering and plan boundary.

### 5.2. `construction.estimates` pack

- project intake and estimate clarification;
- estimate aggregate and immutable revisions;
- source-aware price status;
- deterministic calculation;
- estimate editor for desktop and mobile;
- estimate review and explicit human approval;
- PDF/XLSX/DOCX/CSV package exports;
- construction specialist agent capabilities;
- later: regulated methods, normative libraries, KS-2/KS-3/M-29,
  XML/GGE and incumbent-system exchange.

### 5.3. What AI may and may not do

AI may:

- extract candidate quantities and works;
- propose classifications and matching;
- locate candidate price or normative evidence;
- explain changes and inconsistencies;
- prepare a draft and ask for missing facts.

AI may not:

- invent a verified price source;
- silently change an approved revision;
- make floating-point financial arithmetic authoritative;
- declare regulatory compliance without a rule and evidence set;
- approve its own consequential output;
- write canonical history around Product/Data validation.

## 6. Technical product decisions

### 6.1. Client strategy

| Surface | Decision | Reason |
|---|---|---|
| Browser desktop | Keep the current desktop experience stable | It is already useful and is not the mobile redesign target |
| Mobile Safari/Chrome | Responsive web is a production requirement | Every customer receives the mobile product from the same URL |
| Native iOS/Android | Expo + React Native is the current quality baseline and truth spike | Native keyboard, gestures, haptics, camera, audio, notifications and secure storage |
| Tauri 2 | Candidate Kolibri Edge Shell for desktop, kiosk, managed and selected mobile surfaces | One web presentation can be paired with Rust and Swift/Kotlin plugins where a supported system WebView exists |
| Headless/embedded | Rust/device SDK without a mandatory UI shell | Sensors, voice terminals, gateways, printers and actuators must participate without pretending to be a browser |

The official assistant-ui React Native package supports streaming, tools,
attachments and native components, and documents reusing the same backend
endpoint. That makes Expo a credible native-client path without changing
Product/Data authority:
[assistant-ui React Native documentation](https://www.assistant-ui.com/docs/react-native?platform=rn).

Tauri is strategically relevant because Kolibri targets more than phones and
laptops. It supports major desktop and mobile platforms, uses the system
WebView, bridges JavaScript to Rust and allows native Swift/Kotlin mobile
plugins. Its official ecosystem includes device-oriented capabilities such as
biometrics, barcode scanning, NFC, haptics, notifications and file access:
[Tauri overview](https://v2.tauri.app/start/),
[mobile plugin development](https://v2.tauri.app/develop/plugins/develop-mobile/),
[features and plugins](https://v2.tauri.app/plugin/).

It is nevertheless one shell family, not the universal protocol. A TV browser,
watch extension, spatial surface, microcontroller gateway or voice-only device
may not provide Tauri's supported WebView/process model. Kolibri therefore
standardizes device identity, capabilities, events and Rust domain libraries,
then selects the appropriate presentation adapter.

### 6.2. Shared code boundary

Web and native share:

- API and event contracts;
- semantic design tokens;
- capability IDs;
- state machines and validation rules where runtime-neutral;
- fixtures and journey specifications.

They do not share:

- DOM views;
- CSS layout;
- web-only gesture emulation;
- platform security storage;
- keyboard and safe-area implementations.

Pixel and behavioral parity come from one design specification and shared
semantics, not from embedding the browser application in every client.

### 6.3. Device-surface strategy

The target is a device mesh:

```text
Kolibri cloud/product authority
  ↕ versioned contracts, events, identity and policy
device capability protocol
  ├─ browser/PWA
  ├─ Expo/React Native
  ├─ Tauri Edge Shell
  ├─ native extension where the platform requires it
  └─ headless Rust/device SDK
```

At enrollment a device declares its form factor, inputs, outputs, connectivity,
secure-storage properties and local execution capabilities. The server verifies
what it can and returns an allowlisted capability snapshot. The client then
composes a surface appropriate to that device; it does not merely shrink the
desktop page.

The detailed baseline is
`kolibri-v3/docs/DEVICE_SURFACE_ARCHITECTURE.md`, and the first protocol schema
is `contracts/v1/devices/device-capability-manifest.schema.json`.

### 6.4. Rust decision

Rust is introduced as an independent domain kernel now, not as a reason to
choose Tauri.

The estimate kernel:

- belongs to `construction.estimates`, not Platform Core;
- accepts versioned normalized JSON;
- uses fixed-precision decimals;
- has no database, network, UI, LLM or approval authority;
- runs in shadow mode until it matches the authoritative Python path;
- can later be called through a process boundary, PyO3, a service, WASM or
  native binding without rewriting the contract.

This preserves optionality and prevents the calculation engine from becoming
coupled to one client shell.

### 6.5. Universal capability composition

A server-authoritative capability snapshot decides which vertical surfaces
exist for a tenant. The client never activates a vertical from a local label
or downloaded executable manifest.

The trusted manifest specifies:

- vertical and package version;
- capabilities and contracts;
- entitlement requirements;
- artifact kinds;
- allowlisted renderer/editor keys;
- agent capabilities;
- source, data and approval policies.

No arbitrary JavaScript, Python or Rust is loaded from a runtime manifest.

## 7. One-week production objective

Kolibri is already live at `https://kolibriai.ru/app`. The 2026-08-06 release
is an atomic, rollbackable update of the existing product and a controlled
commercial-vertical pilot—not a greenfield launch and not market-wide
functional parity with incumbents.

The current web product remains the production base. Expo, Tauri and headless
SDK work add clients to the same authority; none may replace the working web
route merely because its technology spike builds.

It succeeds when an invited user can, over desktop or cellular mobile:

1. register and sign in;
2. open a project and durable chat;
3. send a normal prompt and receive streaming progress without a new runtime
   process being created for every message;
4. leave, reconnect and resume the same work;
5. attach source material;
6. create, edit and version an estimate;
7. see source/completeness status and deterministic totals;
8. export a useful document;
9. return from the editor to the main screen without losing draft or scroll;
10. encounter no dead microphone, image or voice controls.

The detailed delivery gates are in
`kolibri-v3/docs/PRODUCTION_ROADMAP_2026-08-06.md`.

## 8. Twelve-month product roadmap

### Phase 0 — production foundation, now through week 1

- one Product/Data backend and one release lane;
- exact runtime/bootcamp binding;
- durable AG-UI/A2A journey;
- responsive mobile web and desktop regression;
- first vertical capability boundary;
- Rust kernel contract and golden tests;
- controlled pilot, monitoring, backup and rollback.

### Phase 1 — sellable commercial-estimate product, weeks 2–6

- ten discovery interviews and five hands-on design partners;
- measured intake-to-first-draft journey;
- reliable PDF/XLSX/image extraction;
- company price catalog and source evidence;
- estimate revisions, comparison and approval;
- polished PDF/XLSX exports;
- usage, correction and acceptance analytics;
- first paid pilots.

### Phase 2 — team system of work, months 2–3

- roles for estimator, reviewer, manager and viewer;
- comments, assignments and approval queues;
- reusable templates and analog projects;
- price freshness and change alerts;
- offline-tolerant native read/review flow;
- integration/export adapters chosen from actual pilot demand;
- security review, retention controls and organization administration.

### Phase 3 — professional compatibility, months 4–6

- prioritized regulated calculation methods;
- approved normative source pipeline and licensing;
- KS-2/KS-3/M-29 fixtures where the target segment requires them;
- XML/GGE and selected incumbent exchange formats;
- expert acceptance corpus and calculation differential testing;
- enterprise SSO, audit export and deployment options;
- evidence for any compliance or replacement claims.

### Phase 4 — direct incumbent competition, months 7–12

- accepted compatibility matrix for the selected customer segment;
- BIM/ERP/accounting integrations driven by contracts, not bespoke UI;
- scale, availability and support SLAs;
- partner implementation playbook;
- migration tooling and data reconciliation;
- selective replacement offers with a documented rollback plan.

### Phase 5 — second vertical

A second vertical starts only after the Core proves:

- repeatable tenant activation;
- durable agent execution;
- reusable project/chat/artifact/approval patterns;
- profitable or strategically validated first-vertical retention;
- a vertical onboarding checklist that does not require forking the Core.

An auto-service vertical is a lower-regulation candidate. A medical vertical
requires a separate safety, consent, retention, provider and data-residency
program and must not inherit construction policy defaults.

## 9. Business model

### 9.1. Packaging model

```text
Kolibri Platform subscription
  + enabled vertical pack
  + model/storage/document usage
  + optional onboarding, integration and expert-review services
```

Entitlements must be expressed as capabilities, not client-side plan names.
This keeps future bundles and client-specific products possible.

### 9.2. Pricing experiments, not final prices

Current official list prices show that customers already pay separately for
professional software, seats, databases and updates. For example, the official
pages list a 1C:Estimate 3 electronic license at 20,700 RUB and GRAND-Estimate
2026.2 at 35,500 RUB per workplace, before the relevant databases and update
subscriptions. These are reference anchors, not directly comparable SaaS
economics.

Test three offers with design partners:

| Offer hypothesis | Test band | Intended user |
|---|---:|---|
| Professional | 3,900–6,900 RUB/user/month | independent estimator or one-seat contractor |
| Team | 2,900–4,900 RUB/user/month, minimum 5 seats | contractor estimate team |
| Business pilot | 150,000–500,000 RUB/year plus onboarding | organization requiring policy, integration or support |

Every offer should have annual and monthly options, a clear included-usage
allowance and visible overage behavior. Do not subsidize unbounded model or
document processing.

Final prices require evidence from at least:

- ten problem interviews;
- five live workflow pilots;
- three explicit willingness-to-pay conversations;
- actual model, storage, support and extraction cost per accepted estimate.

### 9.3. Unit economics instrumentation

For every tenant and accepted estimate, measure:

- model and tool cost;
- extraction/document processing cost;
- compute and storage cost;
- human support/review time;
- gross revenue allocation;
- gross margin;
- number of revisions and regenerated documents.

Target gross margin should be set after observed workloads. A product that
saves user time but loses money on every large document is not ready for
self-service pricing.

## 10. Go-to-market system

### 10.1. Design-partner motion

Recruit five partners with recent, real estimate packages. For each:

1. record the current workflow and time;
2. process one historical project side-by-side;
3. compare line coverage, quantities, prices, totals and documents;
4. log every correction with a reason;
5. run a new live project;
6. ask for payment before adding bespoke features;
7. convert common needs into product contracts, not tenant branches.

No customer file becomes model-training data or a cross-tenant source without
an explicit policy and legal basis.

### 10.2. Acquisition message

Lead with:

- “from project files to a reviewable estimate”;
- “every price and decision has evidence”;
- “continue from phone or desktop”;
- “the agent works while the project and history stay durable”;
- “export into the workflow you already use.”

Do not lead with:

- “universal AI for everything”;
- “fully replaces 1C/GRAND” before the acceptance matrix passes;
- unsupported accuracy percentages;
- “autonomous approval” of financial or regulated output.

### 10.3. Sales proof package

Each pilot should produce:

- before/after process map;
- time to first reviewable draft;
- correction log;
- accepted export sample;
- source/evidence manifest;
- customer quote only with permission;
- calculated ROI range with disclosed assumptions.

## 11. Product metrics

### 11.1. North-star metric

**Weekly accepted professional artifacts per active organization.**

For the first vertical this means an estimate revision that a human reviewer
accepts for use or export. Message count and token consumption are not product
success.

### 11.2. Activation funnel

1. organization created;
2. first project created;
3. first source file attached;
4. first agent run started;
5. first reviewable estimate draft produced;
6. first human-approved revision;
7. first useful export;
8. second project within 30 days.

### 11.3. Quality and reliability

- time to first visible progress;
- time to first reviewable artifact;
- percent of runs resumed after disconnect;
- agent run completion/retry/cancel rate;
- line coverage and correction rate;
- unsupported price/source rate;
- Rust/Python calculation mismatch count;
- document validation and acceptance rate;
- tenant-boundary violations: target zero;
- exact-runtime routing violations: target zero.

### 11.4. Commercial

- design partner to paid conversion;
- paid organization retention;
- accepted artifacts per paid organization;
- expansion seats and vertical capabilities;
- gross margin per accepted artifact;
- support hours per organization;
- sales cycle by segment.

## 12. Risk register

| Risk | Consequence | Control |
|---|---|---|
| Generic-platform positioning is too broad | No buyer recognizes an urgent problem | Sell the construction job, keep universality architectural |
| Estimate features leak into Core | Every later vertical requires a fork | Capability manifest, namespaced schemas and dependency tests |
| AI invents facts or prices | Financial loss and destroyed trust | Provenance states, fail-closed release gates and human approval |
| Normative data is used without rights/currentness | Legal and product risk | Approved source registry, licensing, effective dates and immutable source snapshots |
| Premature “replacement” claim | Failed customer migration | Coexistence adapters and explicit acceptance matrix |
| Native, web and desktop fragment | High cost and inconsistent behavior | Shared contracts/tokens/journeys; platform-native renderers |
| Tauri and Rust are conflated | One WebView shell is incorrectly treated as every device | Independent Rust crates, device protocol and evidence-based shell selection |
| One process is launched per message | Long latency and unstable agents | Persistent supervised runtime, durable queue and timing SLO |
| Runtime/bootcamp substitution | Wrong authority or environment | Exact `runtime.profile` constraint, signed card/version and fail-closed validation |
| Custom work becomes customer forks | Product cannot scale | Typed adapters, pack versions and explicit configuration boundaries |
| Medical expansion is treated like a theme | Safety and regulatory exposure | Separate regulated vertical program and no default activation |

## 13. Decision gates

### Production pilot gate

All P0 items in the one-week roadmap pass with immutable build, rollback and
physical-device evidence.

### Paid pilot gate

- end-to-end estimate journey works on customer material;
- reviewer understands source and completeness states;
- deterministic totals and revisions pass;
- document output is actually usable;
- measured cost supports the offered pilot price;
- support and data handling terms are explicit.

### Incumbent-replacement claim gate

For a named customer segment, every required method, source, form, import,
export, audit and integration row in the acceptance matrix passes. The claim
must be segment-specific.

### Second-vertical gate

- first vertical has a repeatable paid use case;
- Core/pack dependency audit passes;
- the new vertical has its own domain owner, policies and deterministic
  authority;
- no regulated claim is inherited from another vertical.

## 14. Immediate operating priorities

1. Ship one stable Product/Data backend and persistent agent runtime.
2. Complete production-grade mobile Safari while preserving desktop.
3. Use Expo/React Native as the mobile-quality reference while running a
   measured Tauri mobile/edge evaluation; do not block web production on either
   app-store path.
4. Put the Rust kernel into CI and shadow parity, not immediate authority.
5. Implement server-authoritative device and vertical capability activation.
6. Finish the complete first estimate journey and evidence package.
7. Recruit five real design partners before broadening the feature list.
8. Build compatibility according to observed customer migration needs.

The strategic discipline is simple: universal Core, sharp first vertical,
deterministic domain truth, measurable customer value.
