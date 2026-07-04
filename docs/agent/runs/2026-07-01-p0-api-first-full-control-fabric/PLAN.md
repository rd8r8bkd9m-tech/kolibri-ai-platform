# PLAN: P0 API-First Full-Control Fabric

Task ID: `P0_API_FIRST_FULL_CONTROL_FABRIC_2026_07_01`

## Goal

Define Kolibri Factory as an API-first control fabric where Mac, Home, Telegram, main, primary-candidate and any trusted command node can control servers, agents, models, tasks, services and artifacts through one protected API.

## Scope

- Document SSH as bootstrap, emergency recovery and diagnostics only.
- Define mandatory Fabric API endpoints.
- Define canonical request and response envelopes.
- Define structured fallback behavior for unavailable nodes.
- Define owner full-control rights with authentication, authorization, audit, scoped writes and key rotation.
- Define node identity, key rotation and new server bootstrap contracts.
- Record follow-up implementation tasks.

## Execution Model

Mac is a thin command node. Remote execution and validation happen through Kolibri Control Plane, Agent Host and server-side worktrees. GitHub remains the source of truth.

## Non-Goals

- No destructive actions.
- No product deployment.
- No secret printing.
- No push to `main`.
- No bypass of provider or infrastructure limits.
