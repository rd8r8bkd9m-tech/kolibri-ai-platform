# Home Visibility Recovery Diagnostic Next

## Next Action

Run a focused SSH-route repair from a node that can reach both Control Plane and Home network, then rerun the Home runtime probes.

Recommended next task ID:

`P0_HOME_SSH_ROUTE_AND_WALLBOARD_RECOVERY_2026_07_02`

## Required Follow-Up Scope

1. From a known-good bootstrap node, test SSH to `kolibri-main`, `home`, `kolibri-home`, and `kolibri-home-root`.
2. If `kolibri-main` is the ProxyJump for Home, verify sshd, firewall, routing, and tunnel path on the jump node without exposing keys.
3. On Home, verify:
   - `systemctl is-active kolibri-agent-host.service`
   - `systemctl show -p SubState,MainPID,ExecStart,WorkingDirectory kolibri-agent-host.service`
   - `tmux ls`
   - expected Russian wallboard session name and owner attach command
   - repo checkout path and `git ls-remote --exit-code origin HEAD` with prompts disabled
4. If the Home wallboard is absent, restart or recreate only the tmux wallboard session, not production services.
5. Update Control Plane node cards after host-level verification.

## Owner-Facing Russian Summary

Сейчас Home виден в Control Plane, но прямой серверный SSH до Home не работает, поэтому wallboard и Home GitHub clone/auth нельзя считать восстановленными. Следующее действие: чинить SSH route/jump path, затем одной read-only командой подтвердить Agent Host, tmux wallboard и GitHub read на самом Home.

