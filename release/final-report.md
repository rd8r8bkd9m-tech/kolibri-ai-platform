# Kolibri Foundation v1 Release Report

## Summary

- Собран foundation v0.1.0 для Kolibri Control Station: Rust-first self-hosted AI Factory OS с Tauri/React station shell, locald, control-plane/agent/scheduler skeletons, policy/sandbox/events/secrets/telemetry foundations, dev infra и release docs.
- Проверенный рабочий контур сейчас: `kolibri-locald` HTTP flow `health -> enroll agent -> heartbeat -> create task -> lease task -> complete task -> list artifacts -> deny terminal without approval`.
- Mock/skeleton части оставлены явно: central control-plane/PostgreSQL/NATS runtime, scheduler daemon loop, VPS agent long-running execution, production deployment and DNS.
- Намеренно отключено или gated: real PTY shell, direct UI shell execution, direct model shell execution, production deploy without approval, third-party GPT/OpenAI MCP packages without owner approval.

## Architecture Delivered

- Monorepo: Rust workspace plus pnpm workspace.
- Rust workspace: core domain, events, policy, proto, secrets, sandbox, telemetry, PTY, locald and service crates.
- Tauri station: `apps/station` with React/TypeScript shell and locald-facing client boundaries.
- locald: Axum/Tokio local control daemon with task, agent, events, artifacts and terminal-gating endpoints.
- control-plane: Rust service skeleton with health/task/node/agent direction.
- agent: Rust VPS agent skeleton ready for enrollment/heartbeat evolution.
- scheduler: Rust scheduler skeleton for task assignment evolution.
- event bus: NATS JetStream config/bootstrap skeleton and typed event subject mapping.
- policy: default-deny engine and approval cases.
- sandbox: mock/local allowlist abstraction with timeout and deny-by-default tests.
- artifacts: artifact service now hashes payloads with SHA-256 and rejects missing `task_run_id`.
- telemetry: tracing field conventions and initialization helpers.
- docs: architecture, security model, event model, MCP strategy, deployment/kiosk, release process and ADRs.

## End-to-End Flow

- E2E covered locally in `crates/kolibri-locald/tests/e2e_flow.rs`.
- The test starts a real `kolibri-locald` binary on localhost with isolated temp config.
- It enrolls an agent, records heartbeat, creates a public safe task, leases it to the agent, completes it, records artifact IDs and verifies terminal creation is forbidden without task-bound approval.
- This proves the foundation path needed for `task.created -> task.assigned-like lease -> completed -> artifact -> gated terminal` inside the local daemon boundary.

## Commands

```bash
make dev-up
make migrate
make control-plane
make scheduler
make locald
make agent
make station
make test
```

## Test Results

- `cargo fmt --check` passed.
- `cargo clippy --workspace -- -D warnings` passed.
- `cargo test --workspace` passed.
- `pnpm build && pnpm typecheck && pnpm test` passed.
- `make test` passed.
- `make dev-up` was not verified in this environment because Docker daemon/socket is unavailable.

## Security Notes

- Policy posture is default deny.
- Secret values are represented by refs/redacted wrappers and tests verify redaction behavior.
- UI does not execute shell directly.
- Model gateway skeleton does not execute tools directly.
- Real PTY shell is disabled/gated; terminal creation without task-bound approval is tested as forbidden.
- Artifact service does not accept artifacts without `task_run_id`.
- No API keys, passwords or tokens are included in release docs or manifests.

## GitHub Pages and DNS

- Public site source: `apps/site`.
- Pages workflow: `.github/workflows/pages.yml`.
- Custom domain file: `CNAME` with `kolibriai.ru`.
- DNS instructions: `release/dns-instructions.md`.
- REG.RU work must use an existing browser session only. If login, password, SMS, 2FA or CAPTCHA appears, stop with `USER_ACTION_REQUIRED`.
- `api.kolibriai.ru` remains pending until the production VPS IP is confirmed.

## Factory Coordination

- GPT/Codex action bridge was connected to visible factory threads through Codex thread actions.
- Attached server threads: Home, Paris, agent-04, agent-05, agent-06, agent-07, agent-08, agent-09, agent-10, Highload, Reserve242 and 9fts.
- Paris returned `THREAD_ATTACH_ACK` and confirmed coordination via Home/control channel `kolibri_factory_mvp:agent_messages`.
- agent-06 returned `THREAD_ATTACH_ACK` with docs/knowledge proxy binding and the same safety contract.
- 9fts delegated container returned `THREAD_ATTACH_ACK` in standby mode pending remote activation.

## Artifacts

- Release manifest: `release/manifest.json`.
- Artifact manifest: `release/artifact-manifest.json`.
- Release checklist: `release/checklist.md`.
- Final report: `release/final-report.md`.
- DNS instructions: `release/dns-instructions.md`.
- Site build output: `apps/site/dist`.
- Station build output: `apps/station/dist`.
- Aggregate release bundle SHA-256 at report time: `127fb047618a085d8cd000efe5739a85c75d4b195bbedacd81866bcd33e77286`.
- Bundle hash scope: content hash over release artifacts excluding `release/manifest.json`, `release/final-report.md`, `release/artifact-manifest.json` to avoid self-referential hashing.

## Known Limitations

- NATS JetStream and PostgreSQL runtime were not verified because local Docker is unavailable.
- Central control-plane still needs real PostgreSQL persistence and NATS publishing beyond skeleton/MVP handlers.
- Scheduler service still needs persistent event subscription and assignment tests outside locald.
- VPS agent still needs full enrollment/heartbeat/run loop and SQLite state.
- GitHub Pages is configured in code but requires push and GitHub Actions execution to publish.
- `kolibriai.ru`, `www.kolibriai.ru` and `api.kolibriai.ru` cannot be proven live until DNS is changed and propagated.
- Production deploy and HTTPS for `api.kolibriai.ru` remain pending owner-approved VPS target.

## Next Sprint

- Wire real control-plane persistence with PostgreSQL migrations and sqlx checks.
- Connect NATS JetStream publishing/subscription in control-plane, scheduler and agent.
- Implement real agent enrollment, heartbeat loop, task assignment subscription and safe demo execution through sandbox.
- Add remote artifact upload/listing and manifest generation.
- Add PTY approval workflow before enabling any real shell.
- Add browser/UI smoke tests for Station and public site.
- Push branch, run GitHub CI/Pages, then perform DNS with `USER_ACTION_REQUIRED` guard.

## Files Changed

- Rust locald routing and E2E: `crates/kolibri-locald/src/main.rs`, `crates/kolibri-locald/tests/e2e_flow.rs`.
- Artifact hashing and validation: `services/artifact-service/src/main.rs`.
- Public site and Pages: `apps/site`, `.github/workflows/pages.yml`, `CNAME`.
- CI/workspace checks: `.github/workflows/ci.yml`, `package.json`, `pnpm-workspace.yaml`, `apps/station/package.json`.
- Release docs: `release/manifest.json`, `release/artifact-manifest.json`, `release/checklist.md`, `release/final-report.md`, `release/dns-instructions.md`.
