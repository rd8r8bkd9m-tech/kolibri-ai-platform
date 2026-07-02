# Next

After merge/deploy, submit a GoMesh development handoff:

```bash
curl -sS -X POST http://127.0.0.1:9101/v1/gomesh/dev/handoff \
  -H 'Content-Type: application/json' \
  --data '{"objective":"Continue concrete GoMesh app development and produce a PR branch with tests, rollback notes and artifacts.","branch":"agent/P0_PRODUCT_GOMESH_APP_DEV_AGENT_HANDOFF_PR_2026_07_02/generic","active_agent":{"node":"mesh-agent-22","cwd":"/var/lib/kolibri-agent/logical-workers/mesh-agent-22/worktrees/P0_PRODUCT_GOMESH_APP_DEV_AGENT_HANDOFF_PR_2026_07_02/P0_PRODUCT_GOMESH_APP_DEV_AGENT_HANDOFF_PR_2026_07_02-attempt-1/repo","branch":"agent/P0_PRODUCT_GOMESH_APP_DEV_AGENT_HANDOFF_PR_2026_07_02/generic"}}'
```

Do not include tokens, PSKs, private keys or full environment values in the
request.

