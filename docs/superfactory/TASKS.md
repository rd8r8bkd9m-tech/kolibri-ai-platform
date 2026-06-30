# Kolibri Superfactory Task Ledger

Date: 2026-07-01

This ledger is the ordered prompt queue for the factory canvas. It is not a
claim that later tasks are implemented.

| Order | Prompt | Status | Branch/PR | Notes |
| --- | --- | --- | --- | --- |
| 0 | Master canvas | drafted | PR #84 | Global law and execution order captured. |
| 1 | Runner hardening | in review | PR #83 | Current implementation focus. |
| 2 | Superfactory docs package | pending | separate branch | Create full docs/superfactory manual. |
| 3 | GitHub always-current | pending | separate branch | GitHub curator role and policies. |
| 4 | Fleet inventory | pending | server/control-plane read-only | Classify all 20 nodes. |
| 5 | uiap/qjns + server GitHub auth repair | pending | server recovery task | Requires inventory first. |
| 6 | Dirty runtime diffs | pending | read-only preservation | Preserve `main` and `primary-candidate` runtime diffs. |
| 7 | Skill registry | pending | separate branch | Discover broadly, install selectively. |
| 8 | Team mesh | pending | separate branch | Human-language team protocol. |
| 9 | Anti-degradation | pending | separate branch | Quality gates and audit loop. |
| 10 | Integration audit rerun | pending | Control Plane/server task | After runner hardening. |
| 11 | Split PR #46 | pending | analysis first | Do not merge PR #46 as-is. |
| 12 | Server skill sync | pending | server rollout | Approved skills only. |
| 13 | 100000 logical agents | pending | design-only | Logical agents are not physical processes. |
| 14 | Local LLM / FormulaLM model factory | pending | design-only first | No blind model downloads. |
| 15 | Business engine | pending | policy/design first | No spam or automatic money movement. |
| 16 | Phone/video relay policy | pending | policy-only | Observation by default. |
| 17 | Video avatars | pending | design/prototype task | No paid provider requirement by default. |
| 18 | START autopilot spec | pending | specification-only | Do not enable autopilot yet. |

## Next Exact Prompt

After PR #83 is owner-approved and merged, run:

`PROMPT 2 - P0_CREATE_KOLIBRI_SUPERFACTORY_DOCUMENTATION_PACKAGE`

If PR #83 is not merged yet, continue review/validation of Prompt 1 only.
