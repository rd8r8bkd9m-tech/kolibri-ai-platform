# Tests And Probes

## Automated Tests

```bash
python3 -m pytest backend/tests/test_factory_status_fast_health.py tests/test_factory_status.py -q
```

Result: `8 passed in 0.06s`.

```bash
python3 -m py_compile backend/factory_status.py backend/main.py
```

Result: passed.

```bash
git diff --check
```

Result: passed.

## Live Read-Only Probes

```bash
hostname && uname -n
```

Result: `kolibri`, `kolibri`.

```bash
curl -sS -o /tmp/kolibri_control_v1_health.json -w 'cp_v1_health=%{http_code} time_total=%{time_total} remote_ip=%{remote_ip}\n' --max-time 8 http://127.0.0.1:9101/v1/health
```

Result: connection refused on `127.0.0.1:9101`; this worktree host is not the local Control Plane listener.

```bash
curl -sS -o /tmp/probe.out -w 'http://10.99.0.2:9101/v1/health http=%{http_code} time=%{time_total} ip=%{remote_ip}\n' --max-time 5 http://10.99.0.2:9101/v1/health
```

Result: HTTP 200, about 0.100s, `redis=PONG`, `status=ok`.

```bash
curl -sS -o /tmp/probe.out -w 'http://10.99.0.2:9101/v1/nodes http=%{http_code} time=%{time_total} ip=%{remote_ip} bytes=%{size_download}\n' --max-time 8 http://10.99.0.2:9101/v1/nodes
```

Result: HTTP 200, about 6.45s, about 55 KB.

```bash
curl -sS -o /tmp/probe.out -w 'http://10.99.0.10:9101/v1/health http=%{http_code} time=%{time_total} ip=%{remote_ip}\n' --max-time 5 http://10.99.0.10:9101/v1/health
```

Result: HTTP 200, about 0.002s, canonical envelope with `status=completed`, `data.redis=PONG`.

```bash
curl -sS -o /tmp/cp_10_99_0_10_nodes.json -w 'fast_nodes_http=%{http_code} time=%{time_total} bytes=%{size_download}\n' --max-time 3 http://10.99.0.10:9101/v1/nodes
```

Result: HTTP 200, about 0.025s, about 53 KB; observed counts at probe time: total 53, fresh 25, online 25, stale 26, degraded 2.

```bash
curl -sS -o /tmp/tasks_probe.out -w 'http://10.99.0.10:9101/v1/tasks http=%{http_code} time=%{time_total} ip=%{remote_ip} bytes=%{size_download}\n' --max-time 3 http://10.99.0.10:9101/v1/tasks
```

Result: HTTP 200, about 0.57s, about 15.5 MB. This is why task aggregation is disabled by default for the status endpoint.

```bash
curl -sS -o /tmp/kolibri_factory_status_public.json -w 'public_status=%{http_code} time_total=%{time_total} remote_ip=%{remote_ip}\n' --max-time 12 https://kolibriai.ru/api/factory/status
```

Result: TLS verification failed because the certificate subject does not match `kolibriai.ru`; no backend status could be verified through strict public HTTPS.

```bash
curl -k -sS -o /tmp/kolibri_factory_status_public_insecure.json -w 'public_insecure_status=%{http_code} time_total=%{time_total} remote_ip=%{remote_ip} bytes=%{size_download}\n' --max-time 15 https://kolibriai.ru/api/factory/status
```

Result: HTTP 400, about 0.41s, body `{"error": "Invalid request."}`.

```bash
curl -sS -o /tmp/kolibri_http_factory_status.txt -w 'public_http_status=%{http_code} time_total=%{time_total} remote_ip=%{remote_ip} bytes=%{size_download} redirect=%{redirect_url}\n' --max-time 12 http://kolibriai.ru/api/factory/status
```

Result: empty reply from `178.207.11.90`.

