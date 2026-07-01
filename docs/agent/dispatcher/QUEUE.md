# Dispatcher Queue

| Priority | Task ID | Agent type | Target node pool | Preferred nodes | Status | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| P0 | `P0_API_FIRST_FULL_CONTROL_FABRIC_2026_07_01` | implementation / API fabric / security policy | healthy server implementation nodes | `primary-candidate`, `home-live`, `home`, `main` | PR85_ci_green | PR #85 is source-of-truth branch at `9690361f02addeff37771c52fd37878aef455e13`; review/split before merge if needed |
| P0 | `P0_API_FIRST_FULL_CONTROL_FABRIC_FINALIZE_2026_07_01` | implementation finalization / PR / artifact contract | `primary-candidate` | `primary-candidate` | superseded_by_PR85_relay | finalizer created PR #85 but failed exact verifier; no further action on this task |
| P0 | `P0_API_FIRST_FULL_CONTROL_FABRIC_CONTRACT_ALIGN_2026_07_01` | docs-only contract alignment / PR branch update | `primary-candidate` | `primary-candidate` | superseded_by_PR85_relay | Control Plane state failed, but GitHub branch is now aligned through deterministic thin-client relay |
| P0 | `P0_AGENT_HOST_GENERIC_RUNNER_CONTRACT_HARDENING_2026_07_01` | implementation finalization / qa / review | healthy server implementation nodes | `primary-candidate`, then `home` | failed_verifier_pr83_ci_green | server agent pushed PR #83 branch to `5b5bfc17f2efc49974173ebe6287bf1501c44bc2`; remote suite reported `73 passed, 1 warning`; GitHub Actions run `28488999139` succeeded; Control Plane wrapper failed on mismatched expected run artifact path; treat PR #83 as source of truth and fix artifact canonicalization next |
| P0 | `P0_PR83_MERGE_READINESS_AND_RUNNER_PUBLISH_GATE_AUDIT_2026_07_01` | review / qa / narrow runner implementation if needed | healthy server review nodes | `primary-candidate`, then `home` | running | leased by `primary-candidate:agent-host-primary`; audit PR #83 against the observed failed-wrapper/pushed-branch case and decide merge_ready/needs_changes/split_required/blocked |
| P0 | `P0_KOLIBRI_UNIFIED_FABRIC_API_AND_SERVER_CONNECTIVITY_2026_07_01` | docs / API contract / connectivity | healthy server documentation nodes | `main`, then `primary-candidate`/`home` | prepared | new first foundation: unified API/connectivity before runner/feature work |
| P0 | `P0_AI_RUNNER_AUTH_AND_OWNER_REMOTE_TASK_ROUTING_DIAGNOSTIC_2026_07_01` | diagnostic / review / security | healthy control diagnostic nodes | `primary-candidate` | prepared | diagnose Codex/MIMO auth and owner_remote_task routing before more AI-runner tasks |
| P0 | `P0_PUBLIC_SITE_AND_BACKEND_VERTICAL_AUDIT_2026_07_01` | product audit / UX / SEO / backend | healthy server audit nodes | `primary-candidate` | prepared | audit live kolibriai.ru plus frontend/backend; no implementation |
| P0 | `P0_AGENT_HOST_GENERIC_RUNNER_CONTRACT_HARDENING_2026_06_30` | implementation / qa / review | healthy server implementation nodes | `primary-candidate`, `main`, `Home`, other healthy nodes | failed_remote_attempt | PR #83 exists/CI green, but Control Plane verifier failed due `python` not found; align next attempt with Fabric API |
| P0 | `P0_COMMAND_FABRIC_HA_AND_ANY_NODE_CONTROL_2026_07_01` | docs / architecture / review | healthy server documentation nodes | `primary-candidate`, `main`, `home` | prepared | submit before broad autopilot/MIMO rollout; docs-only |
| P0 | `P0_KOLIBRI_OPENAI_COMPATIBLE_FABRIC_API_STANDARD_2026_07_01` | docs / API contract / review | healthy server documentation nodes | `home`, then `primary-candidate`/`main` | superseded_by_unified_fabric | folded into `P0_KOLIBRI_UNIFIED_FABRIC_API_AND_SERVER_CONNECTIVITY_2026_07_01` |
| P0 | `P0_CREATE_SUPERFACTORY_DOCUMENTATION_PACKAGE_2026_07_01` | implementation / docs / review | healthy server implementation nodes | `primary-candidate`, `main`, `Home` | handoff_needed | remote agent must re-create or validate local docs draft before any GitHub PR |
| P0 | `P0_GITHUB_ALWAYS_CURRENT_CONTRACT_2026_07_01` | implementation / qa / review | healthy server implementation nodes | after P0 runner hardening | queued_after_p0 | dispatch after runner hardening result is authoritative |
| P0 | `P0_MIMO_UNIFIED_API_FLEET_ENABLEMENT_2026_07_01` | mimo / implementation / review | MIMO-capable server nodes | `main`, `mesh-9fts`, `mesh-agent-01..03` | prepared | submit to `main` first; exclude `qjns/uiap` until disk repair |
| P0 | `P0_REPAIR_QJNS_UIAP_DISK_2026_07_01` | devops / repair / qa | command/control repair nodes | `home`, `home-live`, then `main`/`primary-candidate` | prepared | read-only triage first; safe cleanup only; target disks `qjns/uiap` |

Rules:
- Do not execute product implementation on Mac.
- Primary control path is API-first Fabric. SSH is bootstrap, emergency recovery
  and diagnostics only.
- Do not return dead-end `server unavailable`; classify reason, use fallback API
  route where possible, and create repair task.
- Do not mark a task remote-executed without Control Plane task status or SSH
  dispatch record.
- Do not use `qjns` or `uiap` for implementation until disk/GitHub auth
  repair is confirmed.
