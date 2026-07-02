# Next

1. Review and merge this focused Factory Control change.
2. Deploy/restart Factory Control through the approved server Agent Host path; do not mutate live services from a local Mac.
3. Run `./ops/kolibri-dispatch backlog-audit` after deploy.
4. Requeue only entries with:
   - `safe_action: requeue_now`, or
   - `safe_action: requeue_after_github_clone_repair` after GitHub clone repair is verified.
5. Supersede, rather than retry, failed tasks with useful artifacts or explicit replacement tasks.
