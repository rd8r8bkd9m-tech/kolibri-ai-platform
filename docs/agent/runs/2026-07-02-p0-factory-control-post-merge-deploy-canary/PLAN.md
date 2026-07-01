# Plan

Task id: `P0_FACTORY_CONTROL_POST_MERGE_DEPLOY_CANARY_2026_07_02`

1. Confirm execution is on the server/control node, not a local Mac.
2. Back up the live Factory Control unit, legacy entrypoint, and target runtime files.
3. Stage the post-PR #103 Factory Control runtime files into the target repo path `/opt/kolibri-ai-platform`.
4. Run `scripts/preflight-factory-control-runtime.sh` on `/opt/kolibri-ai-platform` before any restart.
5. Restart only `kolibri-factory-control.service`.
6. Verify `/health`, `/v1/health`, `/v1/fabric/health`, `/v1/fabric/routes`, `/v1/fleet/nodes`, and `/v1/models`.
7. Apply rollback from the recorded backup if any required route fails.

