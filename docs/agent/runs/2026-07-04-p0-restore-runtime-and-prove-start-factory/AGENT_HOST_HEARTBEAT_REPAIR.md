# AGENT_HOST_HEARTBEAT_REPAIR.md

**Date:** 2026-07-04T22:00:00Z

## Root Cause
Agent-host processes on main, uiap, new, qjns pointed to dead CP at 10.99.0.2:9101.

## Fix Applied
Force-killed all agent-host processes on affected servers and restarted with correct control URL:
```
--control-url http://10.99.0.1:9101
```

## Result
- Before: online=5, degraded=65, stale=47
- After: online=74, degraded=24, stale=20
- All key servers (main, qjns, primary, server-kfrm, home) now online
