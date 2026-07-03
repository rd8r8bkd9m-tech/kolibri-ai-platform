# Rollback

Rollback state for this route-escalation task: `not_needed`

Reason:

- This task created documentation and a dispatchable JSON envelope only.
- It did not submit the envelope.
- It did not run Home kiosk commands.
- It did not start, stop, restart, install, or modify any live service.
- It did not change MikroTik, GoMesh, DNS, DHCP, routes, firewall, NAT,
  credentials, or environment files.

Repository rollback, if the route artifacts must be withdrawn:

1. Revert the commit containing these files.
2. Confirm the following paths are absent or replaced by a superseding task:
   - `docs/agent/dispatcher/envelopes/P0_HOME_KIOSK_REPAIR_REMOTE_2026_07_03.json`
   - `docs/agent/runs/2026-07-03-p0-home-kiosk-route-escalation/`

Future Home-side rollback required from
`P0_HOME_KIOSK_REPAIR_REMOTE_2026_07_03`:

1. If a tmux session named `kolibri-home-kiosk` is created by that task, stop
   only that session:

   ```bash
   tmux kill-session -t kolibri-home-kiosk
   ```

2. If that task creates a user-level systemd unit for the kiosk, disable only
   the unit it created and leave production services alone:

   ```bash
   systemctl --user disable --now kolibri-home-kiosk.service
   systemctl --user daemon-reload
   ```

3. If that task launches a browser kiosk process, terminate only the process
   whose command line includes the task-created kiosk marker or profile path.
   Do not use broad process-kill patterns.

4. If that task only refreshes an existing session, rollback is to restore the
   previous session command recorded in its `ROLLBACK.md`; do not delete the
   owner's existing session without explicit approval.

5. If any MikroTik or GoMesh change is separately owner-approved in a later
   task, that later task must record the exact disable command before enabling
   the change. This route-escalation task authorizes no such change.
