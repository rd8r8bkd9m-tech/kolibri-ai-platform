# Next

Recommended follow-up:

1. Keep `kolibri-factory-control.service` on the patched local runtime while monitoring lease latency and task count.
2. Port the live registry-preserving runtime changes back into the main branch rather than deploying this older rebroadcast branch wholesale.
3. Re-run the same 250-request lease canary after the main endpoint `10.99.0.2:9101` is updated; it still showed legacy 204 lease idle behavior during this run.
4. Do not run a full worker wave until the main endpoint also returns structured HTTP 200 lease idle/overload responses.
5. Preserve rollback directory `/opt/kolibri-ai-platform/.rollback/20260704T053602Z-stage250-lease-timeout` until the mainline code catches up and at least one more lease canary passes.

Exact next validation command:

```bash
python3 -m py_compile /opt/kolibri-ai-platform/ops/factory_control.py \
  && scripts/preflight-factory-control-runtime.sh /opt/kolibri-ai-platform \
  && systemctl is-active kolibri-factory-control.service
```

