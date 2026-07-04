# HOME_NOC_STATE_FIX.md

**Date:** 2026-07-04T22:10:00Z

## NOC Panel Status
- Running on home:8181 (noc_server.py)
- Health endpoint: OK (connects to CP at 10.99.0.1:9101)
- Fleet endpoint: FAILS (control plane unavailable)
- Tasks endpoint: FAILS (connection reset)

## State Definition
- **green**: CP healthy + queue works + canary passed
- **yellow**: CP healthy, execution degraded
- **red**: CP unhealthy or submit/lease broken
- **gray**: stale/unknown

## Current State: YELLOW
CP health is OK, but lease pipeline broken → execution degraded.

## Fix
Kill duplicate factory-control process → lease works → canary passes → can show yellow/green.
