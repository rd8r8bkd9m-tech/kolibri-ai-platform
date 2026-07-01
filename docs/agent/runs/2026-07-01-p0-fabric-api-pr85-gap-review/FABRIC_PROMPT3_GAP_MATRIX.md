# FABRIC_PROMPT3_GAP_MATRIX

Task: `2026-07-01-p0-fabric-api-pr85-gap-review`
Reviewer: `Алексей — Fabric API Reviewer`
Node: `primary-candidate:agent-host-primary`

| requirement_id | requirement_text | source_prompt_section | implemented_in_pr85 | files_evidence | tests_evidence | risk | required_action | can_merge_without_this |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FAPI-001 | API-first control path and SSH emergency/bootstrap-only posture | Prompt #3 core principle; API-first addendum | partial | README, docs/superfactory/API_FIRST_CONTROL_FABRIC.md, ops/kolibri-dispatch | tests/test_fabric_control.py partial | medium | Keep; align endpoint aliases | yes |
| FAPI-002 | GET /v1/fleet/nodes, /topology, /route, /capabilities | Prompt #3 Health and discovery | no | Mentioned in docs/runbook; implementation uses narrower /v1/fabric/* | missing | high | Implement fleet aliases and tests | no |
| FAPI-003 | GET /v1/models | Prompt #3 OpenAI-compatible model/agent registry | no | No implementation evidence | missing | high | Add model registry safe response/test | no |
| FAPI-004 | POST /v1/responses | Prompt #3 Primary task/model interface | no | No implementation evidence | missing | high | Add OpenAI-compatible responses contract/stub/test | no |
| FAPI-005 | POST /v1/chat/completions | Prompt #3 Compatibility interface | no | No implementation evidence | missing | high | Add compatibility contract/stub/test | no |
| FAPI-006 | POST /v1/agents/tasks plus status/artifacts/cancel | Prompt #3 Agent task interface | partial | Existing /v1/tasks/* remains; /v1/agents/* aliases absent | missing alias tests | high | Add /v1/agents aliases over existing task endpoints | no |
| FAPI-007 | POST /v1/admin/exec/service/git/bootstrap-node/rotate-keys | API-first full-control fabric addendum | no | Docs mention admin endpoints; implementation has safe /v1/fabric/bootstrap only | missing | high | Add deny-by-default admin stubs with auth/scope/audit envelopes | no |
| FAPI-008 | Canonical request envelope with task_id, trace_id, owner, source, command_node, role, target, fallback, write_scope, constraints | API-first addendum request shape | partial | Documented; no shared validator/schema evidence | missing schema tests | high | Add helper/schema and validation tests | no |
| FAPI-009 | Canonical response envelope with status, node, route_used, fallback_nodes, artifacts, blocked_reason, repair_task, next_action | API-first addendum response shape | partial | Some blocked envelopes exist; not canonical across endpoints | missing schema tests | high | Add response helper/schema and endpoint tests | no |
| FAPI-010 | Structured unavailable errors with fallback and repair task | Prompt #3 error model | partial | fabric route/control-plane errors exist; taxonomy incomplete | partial tests | medium | Expand reason taxonomy and tests | no |
| FAPI-011 | Owner full-control API authenticated, authorized, scoped, logged, rotated | API-first trust plane/full rights policy | partial | Policy docs exist; enforcement mostly absent/safe-stub | missing auth gate tests | high | Keep deny-by-default until auth gates implemented | no |
| FAPI-012 | Node identity and key rotation policy/API | Node identity and key rotation prompt | partial | Docs/policy endpoint; no rotation action | missing | medium | Label as contract-only or add safe blocked rotate endpoint | yes |
| FAPI-013 | New server bootstrap through API | New server bootstrap contract | partial | /v1/fabric/bootstrap safe stub exists; /v1/admin/bootstrap-node missing | partial tests | medium | Add admin bootstrap alias/stub and tests | no |
| FAPI-014 | No unrelated product scope | Owner policy/GitHub discipline | partial | PR #85 touches infra/network/config.json and backend/main.py besides docs/control plane | CI only | medium | Review/split if unrelated to Fabric API repair | yes |
| FAPI-015 | PR #91 dependency for MIMO runner output/auth | Review scope dependency check | yes | PR #91 accessible, draft, CI-green per ledger; useful but not hard dependency | PR91 focused tests in prior artifacts | low | Merge/deploy PR91 before broad MIMO fanout, not required for PR85 endpoint repair | yes |
