# Deploy Preflight

Preflight script:

`scripts/preflight-factory-control-runtime.sh`

Remote worktree result:

```text
factory_control_runtime_preflight=ok
```

The preflight is read-only and must run on the target control node before any
future `kolibri-factory-control.service` restart.

Required live rollout sequence after PR merge:

1. Confirm the authoritative deployed repo path on the target control node.
2. Run:
   `bash scripts/preflight-factory-control-runtime.sh <deployed_repo_path>`.
3. Confirm it prints `factory_control_runtime_preflight=ok`.
4. Backup the current runtime entrypoint/unit state.
5. Restart only `kolibri-factory-control.service`.
6. Verify:
   - `/health`
   - `/v1/health`
   - `/v1/fabric/health`
   - `/v1/fabric/routes`
   - `/v1/fleet/nodes`
   - `/v1/models`
7. Roll back immediately if the service enters auto-restart or any health
   endpoint fails.

