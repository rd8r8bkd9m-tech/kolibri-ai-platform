# NEXT: P0 API-First Full-Control Fabric

## Next Recommended Task

Harden Agent Host generic runner contract so remote agents must:

- create exact required artifact paths;
- fail early when required filenames are missing;
- preserve useful work even when verifier checks fail;
- return structured result envelopes;
- expose a deterministic docs/artifact alignment mode.

Suggested task ID:

`P0_AGENT_HOST_GENERIC_RUNNER_CONTRACT_HARDENING_2026_07_01`

## Follow-Up Implementation Tasks

1. Add Fabric API schemas for request and response envelopes.
2. Implement `/v1/fleet/*` endpoints over Control Plane node cards.
3. Implement `/v1/agents/*` endpoint aliases over task submit/status/artifacts/cancel.
4. Implement `/v1/models`, `/v1/responses`, and `/v1/chat/completions` as the OpenAI-compatible fabric surface.
5. Add privileged admin endpoint stubs with deny-by-default gates.
6. Add fallback route classification for `api_unreachable`, `vpn_down`, `firewall`, `disk_full`, `auth_failed`, `dns`, and `unknown`.
7. Add node identity and key rotation implementation.
8. Add new server bootstrap implementation.
