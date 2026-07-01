# Next

Next exact task:

`P0_DEPLOY_FACTORY_CONTROL_AND_TELEGRAM_GATEWAY_CANARY_REPAIR_2026_07_02`

Objective:

On a server/control node, with owner approval for live runtime changes, run
preflight and then repair the remaining post-merge canary blockers:

1. Restart or redeploy only the existing allowed Factory Control unit so the
   live listener exposes PR #85 `/v1/fabric/*`, `/v1/fleet/*`, and `/v1/models`
   routes.
2. Run Telegram gateway preflight, confirm no Bot API mutation risk, then start
   or restart only the existing `kolibri-telegram-gateway.service` if approved.
3. Repair Python verification environment with an approved venv or system
   package path and rerun factory-status freshness tests.
4. Recheck GitHub PR queue metadata from a node with GitHub CLI/app auth.
5. Rerun the post-merge remote canary and record exact artifacts.

