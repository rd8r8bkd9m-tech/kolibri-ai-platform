# CONTRADICTION_LEDGER.md

**Date:** 2026-07-04T22:40:00Z

## Known Contradictions

| ID | Claims | Evidence | Severity | Owner Impact | Repair Task |
|----|--------|----------|----------|--------------|-------------|
| X-001 | "Control Plane healthy" vs "POST /v1/tasks/lease fails" | API logs show 500 | high | Factory cannot execute | Kill duplicate factory-control |
| X-002 | "21 servers online" vs "only 1 fresh in CP" | Fleet summary vs state index | high | Most servers degraded | Fix agent-host control URLs |
| X-003 | "completed" vs "required_artifacts_missing" | Task records vs artifact check | high | Fake completion possible | Add artifact gate |
| X-004 | "agent-10 exists" vs "no heartbeat" | Server list vs CP records | medium | Quarantine needed | Mark quarantined |
| X-005 | "running=12" vs "active=0" | State index vs active summary | medium | Phantom running tasks | Rebuild running index |
| X-006 | "Home NOC green" vs "queue submit broken" | NOC UI vs API response | medium | Misleading status | Fix NOC data source |
| X-007 | "MIMO available" vs "permission denied on external dirs" | mimo run output | low | Limited execution | Configure permissions |

## Rules

1. Every contradiction must have repair task
2. High severity contradictions block completion
3. Contradictions are logged, not hidden
4. Owner must be informed of high-severity contradictions
