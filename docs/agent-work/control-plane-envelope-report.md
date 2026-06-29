# Control Plane envelope report

Дата: 2026-06-29  
Роль: `control_plane_envelope_integrator`  
Статус: envelopes подготовлены локально, задачи не отправлялись.

## Scope

Работа ограничена файлами:

- `ops/envelopes/*.json`
- `docs/agent-work/control-plane-envelope-report.md`

Серверные задачи, Control Plane submit, GitHub Project sync, внешние письма и
FormulaLM/model benchmark не запускались. Этот пакет предназначен для проверки
главным агентом и последующей отправки через:

```bash
ops/kolibri-dispatch submit --file <envelope.json>
```

## Envelope matrix

| Envelope | File | Status | Source package | Notes |
| --- | --- | --- | --- | --- |
| `KOL-DOCS-STEWARD-20260629` | `ops/envelopes/KOL-DOCS-STEWARD-20260629.json` | created | `docs/agent-work/docs-steward.md` | Developer portal, API/runbook/task-envelope/inter-agent docs. |
| `KOL-PREMIUM-LANDING-UI-20260629` | `ops/envelopes/KOL-PREMIUM-LANDING-UI-20260629.json` | created | `docs/agent-work/premium-ui-standard.md` | Premium landing `/`, `/app` remains chat-first, Control FAB guardrails. |
| `KOL-LIVING-BIRD-RD-20260629` | `ops/envelopes/KOL-LIVING-BIRD-RD-20260629.json` | created | `docs/agent-work/living-bird-rive-spec.md` | Rive/SVG compatible R&D slice, no fake Rive completion if asset is absent. |
| `KOL-INVESTOR-OUTREACH-20260629` | `ops/envelopes/KOL-INVESTOR-OUTREACH-20260629.json` | created | `docs/agent-work/investor-outreach-pack.md` | Safe first-wave artifacts only; no external sending or invented contacts. |
| `KOL-GITHUB-PROJECT-OPS-20260629` | `ops/envelopes/KOL-GITHUB-PROJECT-OPS-20260629.json` | created | `docs/agent-work/github-project-ops.md` | Project/issue/PR/CI sync with `Project sync: pending` fallback. |
| `KOL-SUBAGENT-POOL-SUPERVISOR-20260629` | `ops/envelopes/KOL-SUBAGENT-POOL-SUPERVISOR-20260629.json` | created | `docs/subagent-pool.md` | Supervisor report only; no spawning, closing or dispatching agents. |
| `KOL-PRODUCT-QA-E2E-20260629` | `ops/envelopes/KOL-PRODUCT-QA-E2E-20260629.json` | clarified | `docs/agent-work/product-qa-pack.md` | Adds release decision, P0/P1/P2 blockers, broader evidence and QA gates. |
| `KOL-FORMULALM-REMOTE-BENCH-6H-20260629` | `ops/envelopes/KOL-FORMULALM-REMOTE-BENCH-6H-20260629.json` | clarified | `docs/agent-work/formulalm-remote-rd-pack.md` | Remote-only wording tightened, dataset/pricebook/preflight made explicit. |

Existing envelopes not changed:

- `ops/envelopes/KOL-FORMULALM-RD-20260629.json`
- `ops/envelopes/KOL-CODEX-CLI-ROLLOUT-20260629.json`
- `ops/envelopes/KOL-SERVER-KFRM-PROBE-20260629.json`
- `ops/envelopes/KOL-META-MIMO-ORCHESTRATOR-20260629.json`
- `ops/envelopes/KOL-META-MIMO-ORCHESTRATOR-PRIMARY-20260629.json`

## Suggested submission order

1. `KOL-SUBAGENT-POOL-SUPERVISOR-20260629` - get owner-facing queue/report
   without launching replacements.
2. `KOL-DOCS-STEWARD-20260629` - stabilize developer portal and task envelope
   documentation.
3. `KOL-GITHUB-PROJECT-OPS-20260629` - sync issue/PR/Project trail or record
   `Project sync: pending` blocker.
4. `KOL-PREMIUM-LANDING-UI-20260629` - implement premium landing and app
   boundary.
5. `KOL-LIVING-BIRD-RD-20260629` - implement/spec the safe living bird R&D
   slice.
6. `KOL-INVESTOR-OUTREACH-20260629` - prepare safe first-wave artifacts after
   docs/evidence are visible.
7. `KOL-PRODUCT-QA-E2E-20260629` - run after implementation tasks are ready for
   owner handoff.
8. `KOL-FORMULALM-REMOTE-BENCH-6H-20260629` - submit only after Control Plane
   health and `server-kfrm` Linux/runtime heartbeat are confirmed.

## Safety notes

- Investor outreach envelope explicitly forbids external email sending,
  invented contacts, guessed emails and unsupported fundraising/model claims.
- Subagent pool supervisor envelope explicitly forbids direct spawn/close/handoff
  actions from that task; it returns recommendations for the main agent.
- FormulaLM benchmark remains remote-only and targeted to `server-kfrm`; Mac is
  a control/editing surface only.
- Product QA now requires a GO / NO-GO / GO WITH EXCEPTION decision and
  separates P0 blockers, P1 exceptions and P2 backlog.

## Validation

JSON validation was run after edits:

```bash
for f in ops/envelopes/*.json; do python3 -m json.tool "$f" >/dev/null; done
```

Result: all envelope JSON files parse successfully.
