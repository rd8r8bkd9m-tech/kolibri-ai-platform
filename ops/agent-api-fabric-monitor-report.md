# Agent API Fabric Monitor Report

Run: 2026-06-29T07:20:11Z  
Workspace: `/Users/kolibri/.codex/worktrees/6ff4/kolibri-ai-platform`  
Branch: `codex/factory-autonomy-pwa-billing`  
Probe mode: read-only; no tokens issued, no permissions changed, no destructive actions.

## Summary

Control Plane is reachable at `http://10.99.0.2:9101` and exposes the expected
factory fabric endpoints for tasks, nodes, and inter-agent messages. The local
owner-facing app on `http://127.0.0.1:5173` was previously looking degraded
because its backend adapter preferred the internal DNS URL and collapsed node
state to legacy online counts. The active branch now has local fallback URLs,
normalized node summaries, degraded response shape, and frontend rendering for
fresh/canonical/registered node counts.

`http://localhost:5173` is not the same app on this machine: it is served by
`/Users/kolibri/kolibri-estimate/frontend`. Use `http://127.0.0.1:5173` for the
Kolibri AI Platform Vite app in this worktree.

## Available APIs

| Surface | Probe result | Notes |
| --- | --- | --- |
| `GET /health` | OK | Redis-backed Control Plane returned `status=ok`, `queue_backend=redis`. |
| `GET /v1/health` | OK | Same health contract as `/health`. |
| `GET /v1/nodes` | OK | Returned 42 registered nodes with summary. |
| `GET /v1/tasks?summary=1&compact=1&limit=20` | OK | Returned queue prefix and compact summary; queue length was 65. |
| `GET /v1/agent-messages?target=all&limit=10` | OK | Returned live task events. |
| GitHub repo | OK | `rd8r8bkd9m-tech/kolibri-ai-platform` reachable with `gh`. |
| GitHub issues/PR | OK | Open P0 issues and open PRs are visible; current branch is represented by PR #46. |
| GitHub Project | OK | Project #2 is visible with project scope; 14 items, 18 fields. |

## Runtime Signals

Read-only `/v1/nodes` direct sample at 2026-06-29T07:19Z:

- registered nodes: 42;
- canonical nodes: 22;
- fresh nodes: 6;
- fresh non-draining nodes: 3;
- fresh canonical generic implementation nodes: 1;
- mesh shadow duplicates: 19;
- duplicate hostname groups: `plastilin`, `server-kfrm`.

Compact `/v1/tasks` sample at 2026-06-29T07:19Z:

- queue length: 65;
- returned queue prefix: 20 tasks;
- states in returned prefix: 20 queued;
- `scan_truncated=true`, so the compact summary must not be treated as full
  fleet state.

## Messages Passing

`GET /v1/agent-messages?target=all&limit=10` returned live events including:

- `task_leased` for `KOL-PRODUCT-QA-E2E-20260629-6d0317c5-home`;
- `task_started` for the same task;
- `task_failed` with artifact reference
  `/var/lib/kolibri-agent/artifacts/KOL-PRODUCT-QA-E2E-20260629-6d0317c5-home/.../result.json`.

No write smoke was sent during this run because the queue was active and the
read-only feed already proved message transport.

## GitHub Trail

Verified through `gh` without exposing token material:

- repo: `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform`;
- project: `https://github.com/users/rd8r8bkd9m-tech/projects/2`;
- active PRs include #46 `codex/factory-autonomy-pwa-billing`, #60 factory
  result capture, and #61 Telegram miniapp/owner director bot;
- current open P0 issues include #55-#59 for queue scheduling, remote-only
  FormulaLM paths, Control Plane reachability, compact summary accuracy, and
  stale `active_task` cleanup.

## Fallback And Manual Gaps

- Local backend process is not persistently managed by `nohup` from this Codex
  shell because background children are cleaned up after the shell command
  exits. The app is currently running through a foreground Codex exec session:
  `/opt/homebrew/bin/uvicorn main:app --host 127.0.0.1 --port 8000`.
- The `/opt/homebrew/bin/uvicorn` runtime accepts `/ws/chat` WebSocket upgrades.
  Frontend HTTP fallback and reconnect backoff remain useful when another
  Python environment lacks `websockets`/`wsproto`.
- `/v1/tasks?summary=1&compact=1` reports a bounded queue prefix when truncated.
  It is safe for quick backlog visibility, but not enough for full active-work
  accounting while issue #56 remains open.
- Registered node count is inflated by mesh shadow duplicates. UI now surfaces
  registered/canonical/fresh separately instead of pretending all registered
  nodes are physical capacity.
- Public deploy to `http://104.253.43.117` remains manual-blocked by SSH path
  reachability from this Mac control surface, as documented in the central page
  audit.

## Safe Repair Actions

1. Keep the active backend fallback order: `KOLIBRI_FACTORY_CONTROL_URLS`, then
   explicit `KOLIBRI_FACTORY_CONTROL_URL`, then local mesh URLs
   `http://10.99.0.2:9101` and `http://127.0.0.1:9101`, then internal DNS.
2. Install a real project-local backend venv with `uvicorn[standard]` or at
   least `websockets`/`wsproto`; do not borrow another worktree venv for
   production-like local runs.
3. Extend compact task summary to include active/leased/running state outside
   the returned queue prefix, or expose a separate read-only active summary.
4. Continue deduping mesh shadow nodes in owner-facing views; use canonical
   counts for capacity and registered counts for registry hygiene.
5. Keep GitHub Project sync degraded-state explicit as `Project sync: pending`
   when project APIs fail; do not silently fall back to private local notes.
6. Do not issue new tokens or broaden permissions for this monitor. Existing
   `gh` scopes are sufficient for read-only repo/issues/PR/Project checks.

## Local App Repair Snapshot

Implemented in this worktree:

- backend Control Plane fallback and degraded status shape;
- local writable data path fallback for Mac development;
- frontend factory status helper and live cluster summary;
- Control Panel UI states for loading/degraded/empty, duplicates, stale/drain,
  and canonical/fresh counts;
- WebSocket reconnect backoff so missing local WebSocket support does not spam
  the backend.

Verification:

- `npm run lint` passed with existing warnings only;
- `npm run build` passed with Vite chunk-size warning only;
- focused pytest passed earlier in the available automation venv; repeat with
  the current system `python3` is blocked because this interpreter has no
  `pytest` installed;
- Playwright screenshots captured for desktop, mobile, and app views.
- local backend check passed on `http://127.0.0.1:8000/api/factory/status` with
  `status=online`, Control Plane URL `http://10.99.0.2:9101`, 42 registered
  nodes, 25 fresh nodes, and 22 canonical nodes.
