# Kolibri Shell Next: clean component boundary contract

This application is a clean-room shell. Its executable source is authored in
this directory and may depend only on packages declared in its own
`package.json`.

## Non-negotiable boundary

- No source, stylesheet, component, generated bundle, or runtime import may
  come from `apps/kolibri-shell`, `frontend`, or any other application tree.
- No symlink may make source or public assets depend on another application.
- The only approved donor byte sequence is `public/kolibri-bird.png`. It is a
  regular copied file with SHA-256
  `6f30357f75c963e5e4d85b464b10eadb2545d2a6b40aced54861571c4322c3d7`.
- Cross-layer imports use the aliases below. A relative import must remain
  inside its current layer.

## Layers

| Layer | Responsibility | May import internal layers |
| --- | --- | --- |
| `src/domain` | framework-free state, values, reducers, calculations | `domain` |
| `src/services` | browser/API adapters and safe stream normalization | `services`, `domain` |
| `src/components` | accessible presentational primitives | `components`, `domain` |
| `src/features` | chat, work trace, estimate, project, composer and owner wallboard use cases | `features`, `components`, `services`, `domain` |
| `src/app` | composition, responsive shell and global styling | `app`, `features`, `components`, `services`, `domain` |
| `src/dev` | deterministic local visual-QA fixture only | all layers except `app` |

Aliases are `@app`, `@features`, `@components`, `@services`, `@domain`, and
`@dev`. Production modules must never statically import `@dev`. The development
fixture is reached only behind `import.meta.env.DEV`; its sentinel must not be
present in the production build.

## Runtime contract

- Production has no sample response fallback. Missing or failed backend state
  is presented as an explicit unavailable/retry state.
- Browser code talks only to the unified same-origin gateway. It never selects
  a provider or Control Plane endpoint.
- `/wallboard` bypasses public Shell bootstrap and consumes only the
  owner-authenticated `/v1/program/status` projection. A missing, stale or
  unauthorized ledger is explicit; the UI never substitutes zero counts.
- Work Trace renders normalized, user-safe events. Raw prompts, credentials,
  hidden reasoning, internal hostnames, and provider secrets are not UI data.
- The estimate artifact owns deterministic arithmetic; totals are derived from
  line items, never accepted as an unrelated display constant.
- Every visible control in the primary flow has a keyboard-accessible action,
  state change, or explicit unavailable explanation.

`tests/architecture.test.mjs` is the executable gate for this contract.
