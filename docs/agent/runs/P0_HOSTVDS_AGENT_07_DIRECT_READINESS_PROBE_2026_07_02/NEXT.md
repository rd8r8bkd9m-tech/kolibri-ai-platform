# Next Exact Repair Task

Next task id:

`P0_REPAIR_HOSTVDS_AGENT_07_GITHUB_CLI_AND_LOCAL_CONTROL_ALIAS_2026_07_02`

Task:
- Install or restore the approved non-interactive GitHub CLI/auth path for `hostvds-agent-07 / mesh-agent-07` without printing tokens, account names, credential helper output or environment file contents.
- Verify GitHub auth only through a redacted classification result: `ok`, `missing` or `blocked_unknown`.
- Preserve `10.99.0.10:9101` as the working Control Plane route and either document it as canonical for this node or repair the local `127.0.0.1:9101` alias if required by dispatcher tooling.
- Confirm the exact task id appears in Control Plane task visibility or document why direct lease execution is intentionally not mirrored in `docs/agent/dispatcher/QUEUE.md`.
- Produce artifacts under `docs/agent/runs/P0_REPAIR_HOSTVDS_AGENT_07_GITHUB_CLI_AND_LOCAL_CONTROL_ALIAS_2026_07_02/`.

Non-goals:
- No product-code changes unless the local route alias is proven to require a code-level contract fix.
- No credential rotation in an unattended task.
- No push unless owner-approved repair scope explicitly includes it.

