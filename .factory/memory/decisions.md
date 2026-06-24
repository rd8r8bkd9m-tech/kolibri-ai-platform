# Factory Decisions

## 2026-06-20: Bootstrap Factory Before Fanout

Decision: create Factory v1 scaffolding, schemas, policies, dry-run scripts, and
two canary tasks before restarting broad MiMo fanout.

Reason: previous remote agent attempts produced timeouts and ambiguous results;
the user needs a persistent, reviewable, parallel development factory rather
than sequential firefighting.

Assumption: existing dirty changes in `backend/public_proxy.py`,
`frontend/src/hooks/useCluster.js`, `scripts/agent_factory.py`,
`docs/agent-factory.md`, and `infra/systemd/kolibri-agent-factory.service` are
kept and treated as current work, not reverted.

## 2026-06-20: Competitive Analyst Subagent

Decision: add a read-only competitive analyst role and reusable prompt template
to the factory.

Reason: the factory needs stronger task prompts derived from competitor,
product, domain, legal, QA, and integration analysis. The analyst does not
change production code; it prepares reports and prompts that Codex converts into
task envelopes.

Artifacts:
- `.factory/agents/competitive_analyst.md`
- `.factory/templates/competitive_analysis_prompt.md`
- `.factory/tasks/ready/KOL-ANALYTICS-001.json`
- `.factory/reports/competitive-analysis-001.md`
- `.factory/reports/competitive-prompts-001.md`

## 2026-06-21: Block 10k Synthetic Estimate Generation Until Proof Gate

Decision: record the user's 10k synthetic estimate generation request as a
blocked scale task, and prepare only a read-only canary/spec task first.

Reason: the FormulaLM protocol requires a final `estimate-pilot-001`
STOP/CONTINUE/SCALE report with metrics and artifact hashes before scaling to
10k estimates. Synthetic estimates can help training later, but they cannot be
used as proof of superiority and must never contaminate untouched final-test
data.

Artifacts:
- `.factory/tasks/blocked/FORMULALM-SYNTHETIC-10K-GENERATION-001.json`
- `.factory/tasks/ready/FORMULALM-SYNTHETIC-CANARY-SPEC-001.json`
- `.factory/reports/ai_inventions_inventory_20260621.md`

## 2026-06-21: Disable Duplicate MiMo Service on `kolibri-main`

Decision: keep `mimo-acp.service` as the single MiMo server on port `4096` and
stop/disable the duplicate `mimo-agent.service` instead of moving it to a second
port.

Reason: `mimo-acp.service` was already healthy and listening on `0.0.0.0:4096`.
`mimo-agent.service` launched the same `mimo serve` command on the same port,
failed repeatedly, and produced `/tmp/.feff*-00000000.so` files containing
`libopentui.so` on every restart. Moving the duplicate to another port would
create an unnecessary second MiMo endpoint, and the service logs showed
`MIMOCODE_SERVER_PASSWORD` was not set.

Actions:
- Stopped and disabled `mimo-agent.service` on `kolibri-main`.
- Left `mimo-acp.service` running on port `4096`.
- Removed 223 verified `/tmp/.feff*-00000000.so` files after confirming their
  ELF `SONAME` was `libopentui.so`.
- Verified after a wait that no new matching files appeared and only
  `mimo-acp.service` was listening on port `4096`.

## 2026-06-23: Expand Canvas Action Task Scope For Existing Estimate Editor

Decision: expand `KOL-FE-CANVAS-ACTIONS-001` allowed paths to include
`frontend/src/features/estimates` and `frontend/src/shared/types.ts`.

Reason: the first bounded CanvasManifest/DynamicAction slice must wire the
approved registry into the existing estimate editor and shared frontend
contracts. Keeping those files outside the envelope would make the
implementation unverifiable and would hide actual touched paths from Factory
review.

Guardrails:
- No production deploy, restart, live billing, or secret access.
- No arbitrary remote UI execution, `eval`, `Function`, or generated HTML.
- Dynamic UI remains data-only and rendered through approved frontend
components.

## 2026-06-24: Component-First PWA And Device API Rule

Decision: Kolibri frontend work is component-first SPA/PWA development. Shared
surfaces, controls, actions, document/export flows, and device integrations must
be implemented once and reused across screens instead of copied per view.

Reason: the product must behave as one installable Kolibri application on
phones and desktop devices, not as separate screen-specific implementations.
Device capabilities must be accessed through a shared frontend API layer so
behavior stays consistent and can be tested.

Rules:
- Keep Kolibri as a Single Page Application with deep links served by the SPA
  shell.
- Keep the PWA install path working: `manifest.webmanifest`, `sw.js`,
  standalone/iOS metadata, app icons, shortcuts, and offline shell fallback.
- Route browser/device APIs through `frontend/src/lib/deviceApi.js` or another
  shared adapter before components use them.
- Prefer reusable components and shared style tokens for buttons, cards,
  sidebars, document actions, estimate actions, and mobile surfaces.
- Do not duplicate UI logic separately in every screen when a shared component
  or hook can own it.
# 2026-06-24 launch stale lease cleanup

- Decision: treat `KOL-CANARY-001` and `KOL-CANARY-002` as stale, not active
  running leases for the `launch-20260624T212027Z` run.
- Evidence: their status heartbeats are from `2026-06-20T21:35:53Z`, and the
  local PID checks for the recorded factory daemon/subagent autorun processes did
  not find running processes.
- Action: move the stale task envelopes from `.factory/tasks/running/` to
  `.factory/tasks/stale/` and keep their status JSON as historical evidence.
- Rationale: this unblocks the new bounded launch tasks while preserving the
  prior run history and avoiding overlapping mutation assumptions.
