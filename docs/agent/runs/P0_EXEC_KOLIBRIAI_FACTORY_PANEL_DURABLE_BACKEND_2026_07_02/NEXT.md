# Next

Exact next task:

1. Open and merge the branch for this run after review/CI:

```text
https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/new/agent/P0_EXEC_KOLIBRIAI_FACTORY_PANEL_DURABLE_BACKEND_2026_07_02/generic
```

2. Deploy the main node:

```bash
./scripts/deploy.sh main
```

3. Verify production:

```bash
curl -k -sS -D /tmp/kolibri-factory-status.headers https://kolibriai.ru/api/factory/status -o /tmp/kolibri-factory-status.json
curl -k -sS -D /tmp/kolibri-panel.headers 'https://kolibriai.ru/?telegram=1' -o /tmp/kolibri-panel.html
```

Expected result after deployment:

- `/api/factory/status` returns HTTP 200 with JSON containing `status`, `source`, `control_plane`, `nodes`, and `node_list`.
- `/?telegram=1` remains HTTP 200.

If the public URL still returns the MikroTik file-sharing page or generic `Invalid request.`, repair the upstream public edge route so `kolibriai.ru` forwards `/api/*`, `/ws/*`, and the app root to `kolibri-main` nginx instead of the MikroTik file server.
