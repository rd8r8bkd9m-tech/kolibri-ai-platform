# Next

Next exact task: `P0_REPAIR_HOSTVDS_AGENT_03_ALIAS_AND_SSH_READINESS_2026_07_02`

## Objective

Repair or canonicalize HostVDS Agent 03 routing so factory dispatch can target it unambiguously.

## Required Work

1. Decide the canonical dispatch name:
   - preferred short-term: `mesh-agent-03`,
   - repair target: `agent-03`,
   - optional alias: `hostvds-agent-03`.
2. Restore direct SSH bootstrap diagnostics to `hostvds-agent-03` or document that SSH is intentionally disabled and Fabric is the only approved route.
3. Re-register a fresh canonical `agent-03` heartbeat with hostname, disk, runner status, permissions, and active task.
4. Register or remove the literal `hostvds-agent-03` route alias so dispatchers do not target a nonexistent node id.
5. Run GitHub auth/tooling status from an approved authenticated node without printing credentials.
6. Re-run readiness and produce a final `ready_for_factory_work` or exact blocker result.

## Constraints

- No secrets printed.
- No product code changes.
- No destructive git commands.
- No service restart unless explicitly scoped and owner-approved.
- No force push, no push to main.
