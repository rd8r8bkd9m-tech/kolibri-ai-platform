# Home Visibility Recovery Diagnostic Plan

Task ID: `P0_HOME_HOME_LIVE_AGENT_HOST_RECOVERY_DIAGNOSTIC_2026_07_02`

Execution node: `mesh-agent-13` lease running on Linux host `kolibri`.

Russian owner-facing agent: `Анна — Home Recovery And Wallboard`.

## Scope

1. Prove the task is executing on a server Agent Host, not on the local Mac.
2. Verify the Home visibility path through safe, read-only probes.
3. Check Home Agent Host reachability, wallboard visibility, short SSH aliases, and GitHub clone/auth.
4. Avoid printing secrets, changing credentials, restarting production services, destructive git commands, force push, and push to `main`.
5. Produce exact canonical artifacts with state, node, probes, blockers, and next action.

## Method

- Use local server identity probes from the checked-out lease worktree.
- Use existing SSH alias configuration in read-only mode.
- Attempt bounded SSH probes with `BatchMode=yes` and short connection timeouts.
- Use Fabric/Control Plane HTTP visibility as the fallback source of truth when SSH is blocked.
- Treat missing runtime proof as a blocker, not completion.

