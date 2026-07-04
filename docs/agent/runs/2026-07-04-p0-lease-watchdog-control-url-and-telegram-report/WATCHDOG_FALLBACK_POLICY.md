# Watchdog Fallback Policy

Environment:

```bash
KOLIBRI_FACTORY_CONTROL_URLS=http://10.99.0.1:9101,http://10.99.0.10:9101,http://10.99.0.2:9101
```

Behavior:

1. Try each URL in order with bounded timeout.
2. Use the first URL whose `/v1/health` succeeds.
3. Record `control_plane_used`.
4. Record `failed_candidates` with URL, path, reachability, HTTP status, latency and reason.
5. If all fail, write status `control_plane_unavailable`.
6. If all fail and notification is enabled, send clear owner text: "Не удалось проверить очередь".

Timeout:

- Default per URL: `4` seconds.
- Configurable through `KOLIBRI_KFM_STEWARD_TIMEOUT`.
