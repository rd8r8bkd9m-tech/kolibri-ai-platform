# Secondary Control Plane Watchdog

Last check: 2026-06-29T06:56:10Z

## Current Status

- Control Plane `http://10.99.0.2:9101/health`: OK.
- Redis: `PONG`.
- Nodes: 35 registered, 5 fresh/online, 30 stale or not fresh, 3 draining.
- Tasks: 65 queued, 0 active in compact summary.
- P0 miniapp deploy task `KOL-P0-DEPLOY-KOLIBRIAI-MINIAPP-20260629T0647Z`: running on main.

## Impact

No Control Plane or Redis outage detected during this run. Telegram Mini App production deployment remains in progress; public `https://kolibriai.ru` still requires deploy/DNS/TLS verification before it can be considered healthy.

## Last Successful Check

2026-06-29T06:56:10Z: `/health`, `/v1/nodes`, and `/v1/tasks?summary=1&compact=1` responded successfully.

## Safe Recovery Steps

- If `/health` stops responding, capture the exact HTTP/network symptom before changing services.
- If Redis stops returning `PONG`, inspect Redis and Control Plane logs through managed service tooling; do not flush or reset data.
- If deployment stalls, prefer a new Control Plane task or GitHub PR/deploy workflow over ad hoc SSH.
- Do not perform destructive restarts, hard resets, data wipes, or token rotation without explicit owner confirmation.
