# Next

1. Deploy this branch to a canary Control Plane instance and verify all new read-only endpoints.
2. Compare `/v1/fleet/summary` with `/v1/nodes` and systemd worker counts.
3. Repair backend factory status proxy returning degraded/zero nodes.
4. Prove Home kiosk end-to-end by completing or re-routing queued Home deploy tasks.
5. Prove Telegram end-to-end through the active primary receiver, not the standby gateway.

## GitHub Blocker

Push/PR creation is blocked on this machine because the configured GitHub SSH key is read-only. Install a write-capable deploy key or push this local branch from a machine with write access, then open a draft PR titled `P0: establish factory source of truth and routing diagnostics`.
