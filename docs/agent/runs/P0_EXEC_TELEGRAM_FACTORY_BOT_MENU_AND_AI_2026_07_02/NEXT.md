# Next

Next exact task:

Deploy the scoped `kolibri-telegram-gateway.service` update on the control node, then run a live owner-approved canary:

1. Confirm `TELEGRAM_UPDATE_RECEIVER=polling` and no webhook conflict.
2. Restart only `kolibri-telegram-gateway.service`.
3. Send `/help`, a natural-language task, `/status <task_id>`, and `/artifacts <task_id>` from the owner Telegram account.
4. Verify no command menu mutation API calls are made during startup.
5. Record sanitized canary output under a new `docs/agent/runs/<deploy-task-id>/` directory.

Rollback:

Restart the previous deployed gateway revision or revert this branch before deployment; no database or token rotation is required by this change.
