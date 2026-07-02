# Next

Next exact task:

`P0_GOMESH_OWNER_RULES_MONITOR_REVIEW_LOOP_2026_07_02`

Next exact command:

```bash
curl --noproxy '*' -sS http://10.99.0.10:9101/v1/agents/status/P0_GOMESH_OWNER_RULES_MONITOR_REVIEW_LOOP_2026_07_02
```

Expected next outcome:

- If leased by `primary-candidate:agent-host-primary`, let it run and collect `/v1/agents/artifacts/P0_GOMESH_OWNER_RULES_MONITOR_REVIEW_LOOP_2026_07_02`.
- If still queued after the current `primary-candidate` active task finishes, repair agent-host leasing on `primary-candidate` before dispatching more GoMesh work.
- If it completes with a PR URL, review that PR only for GoMesh scope, artifact quality, rollback/canary evidence, and no mixed subsystem changes.
