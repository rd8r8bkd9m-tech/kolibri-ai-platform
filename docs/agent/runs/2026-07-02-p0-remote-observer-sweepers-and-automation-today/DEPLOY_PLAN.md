# Deploy Plan

Deploy status: `not_required`

Reason:

This closeout is a repository artifact contract repair only. It creates missing
documentation artifacts and does not modify executable code, service units,
environment files, runtime configuration, or infrastructure.

Deployment actions:

1. Commit the artifact files on a non-main branch.
2. Push the branch to GitHub.
3. Open a draft PR for review.
4. Merge or accept the branch only through the normal owner/repository process.

Explicit non-actions:

- Do not restart `kolibri-agent-host.service`.
- Do not restart `kolibri-factory-control.service`.
- Do not restart `kolibri-telegram-gateway.service`.
- Do not call Telegram Bot API methods.
- Do not deploy to `/opt/kolibri-ai-platform`.
- Do not modify secrets or environment files.
