# Plan

Task id: `P0_30MIN_SECOND_WAVE_PRIMARY_RELEASE_GATE_2026_07_02`

Status: `completed`

Objective: run the second 30-minute primary-candidate release gate wave for
exiting P0, using checked-in tests plus live non-secret runtime probes.

Scope:

- Verify the checked-out branch is aligned with `origin/main`.
- Run focused Factory Control, Agent Host, Fabric API, MIMO, Telegram gateway
  contract, and mesh bridge tests.
- Run Factory Control runtime preflight.
- Probe live Factory Control primary routes on `10.99.0.10:9101`.
- Check systemd active state for Factory Control and Telegram Gateway without
  reading secrets or calling Telegram Bot API methods.
- Compute a 30-minute node freshness summary from `/v1/fleet/nodes`.
- Record pass/block decision and follow-up tasks in canonical artifacts.

Non-goals:

- No service restart.
- No deploy.
- No Telegram Bot API mutation.
- No PR merge, approval, mark-ready, force-push, or push to `main`.
- No credential inspection or secret printing.
