# PR85_RELEASE_OR_REPAIR_DECISION

Task: `2026-07-01-p0-fabric-api-pr85-gap-review`
Reviewer: `Алексей — Fabric API Reviewer`
Node: `primary-candidate:agent-host-primary`

Decision: `repair_in_pr85`

Allowed decision set: `merge_ready`, `merge_ready_after_minor_docs_fix`, `repair_in_pr85`, `split_required`, `blocked`.

Rationale:

- PR #85 is open, draft, mergeable and CI-green, but not ready for merge.
- It implements a narrower `/v1/fabric/*` surface while the master canvas Prompt #3 requires canonical `/v1/fleet/*`, `/v1/models`, `/v1/responses`, `/v1/chat/completions`, `/v1/agents/*`, and `/v1/admin/*` contracts.
- Request/response envelopes, fallback taxonomy, admin gates and OpenAI-compatible compatibility routes need implementation or safe deny-by-default stubs with tests.
- PR #91 is useful for MIMO/Agent Host runner reliability but is not a hard dependency for PR #85 endpoint repair.

Merge recommendation: keep PR #85 draft and repair in-place with `P0_PR85_PROMPT3_FABRIC_API_SURFACE_REPAIR_2026_07_01`; only then rerun CI and owner release review.
