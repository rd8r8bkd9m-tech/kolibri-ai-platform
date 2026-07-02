# Next

Next exact task:

`P0_REPAIR_HOSTVDS_AGENT_10_FABRIC_ROUTE_AND_GITHUB_AUTH_2026_07_02`

Objective:

Repair or precisely classify the Agent 10 route and GitHub auth blockers.

Required scope:

- Target `mesh-agent-10` as the live alias for `hostvds-agent-10`.
- Add or restore the deployed Control Plane route endpoint expected by the
  API-first contract, or update dispatchers/docs to the deployed supported
  route endpoint if the contract moved.
- Finish target-local GitHub auth classification without printing tokens:
  install `gh` if approved, then run `gh auth status` summary only, no env dump,
  no credential file output.
- Install/register the expected runner on `mesh-agent-10`, then verify an
  active runner service or `Runner.Listener` process without printing
  credentials.
- Preserve no-destructive-git, no-force-push, and no-push-to-main constraints.
- If GitHub auth is missing or expired, create an owner-approved credential
  repair task instead of running interactive login.

Acceptance:

- `hostvds-agent-10` and `mesh-agent-10` alias mapping is explicit.
- API route returns a structured completed or blocked envelope, not `404`.
- Target-local GitHub auth is classified as ready, missing, expired, or blocked
  by provider policy.
- Result includes node, agent name, blockers, artifacts, and next action.
- Russian owner-facing summary is included.
