# SUBMIT_LEASE_ARTIFACT_FIXES.md

**Date:** 2026-07-04T22:10:00Z

## Submit: WORKS
POST /v1/tasks returns 201 with task_id, state=queued.

## Lease: BROKEN
POST /v1/tasks/lease returns connection reset.
Root cause: Two kolibri-factory-control processes on home (PIDs 863245, 4002668) 
conflict on port 9101. Need root access to kill duplicate.

## Artifact: WORKS (direct)
SSH to server-kfrm + mimo run successfully produces artifact at /tmp/START_FACTORY_OWNER_REPORT.md.

## Complete: BROKEN
POST /v1/tasks/{id}/complete returns connection reset (same root cause as lease).

## Fix Required
1. Kill duplicate factory-control process (requires root on home)
2. Verify single-process lease/complete works
3. Run end-to-end canary
