# START_FACTORY_TRUTH_GATE.md

**Date:** 2026-07-04T22:40:00Z

## Claim

"Start Factory works."

## Truth Conditions

This claim is true ONLY if ALL of the following are verified:

| # | Condition | Evidence Required | Status |
|---|-----------|-------------------|--------|
| 1 | Owner command creates task_id | API response with task_id | VERIFIED (KOL-TASK-ca9353c8620e) |
| 2 | Task accepted by Control Plane | POST /v1/tasks returns 201 | VERIFIED |
| 3 | Task visible in queue | GET /v1/tasks shows task | VERIFIED |
| 4 | Task leased by agent | POST /v1/tasks/lease returns 200 | VERIFIED |
| 5 | Task reaches final state | GET /v1/tasks shows completed | VERIFIED |
| 6 | result.json exists | File on disk | VERIFIED |
| 7 | Required artifact exists | File on disk | VERIFIED (/tmp/PROOF.md) |
| 8 | Artifact is readable | cat returns content | VERIFIED (221 bytes) |
| 9 | Artifact is content-bearing | Not generic completion | VERIFIED (Kolibri AI summary) |
| 10 | Owner gets report | OWNER_SUMMARY.md | IN PROGRESS |

## Current Verdict

**partial** (9/10 conditions met)

Missing: Owner summary delivered via Telegram/NO

## Confidence

**high** — all API and artifact evidence is verified

## Next Action

Deliver owner summary to complete the truth gate.
