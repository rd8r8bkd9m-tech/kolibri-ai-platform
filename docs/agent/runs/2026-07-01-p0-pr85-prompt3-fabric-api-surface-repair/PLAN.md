# Plan

Task: `P0_PR85_PROMPT3_FABRIC_API_SURFACE_REPAIR_2026_07_01`

Executor: remote server node `kolibri` via Control Plane/Agent Host. Mac is dispatcher only.

Goal: repair PR #85 so the Prompt #3 API-first Fabric surface has executable server-side routes, canonical response envelopes, safe model/admin stubs, and tests.

Planned scope:

- Inspect PR #85 baseline at `9690361f02addeff37771c52fd37878aef455e13`.
- Implement the required `/v1/fleet/*`, `/v1/models`, `/v1/agents/*`, `/v1/responses`, `/v1/chat/completions`, and `/v1/admin/*` surface in `ops/factory_control.py`.
- Keep privileged admin actions deny-by-default until authenticated owner/admin scope exists.
- Add tests that verify endpoint declarations, canonical envelopes, fallback taxonomy, safe stubs, and agent artifact/status helpers.
- Produce run artifacts and verification evidence.

Out of scope:

- No deploy or service restart.
- No merge approval.
- No force push or push to main.
- No secret printing.
