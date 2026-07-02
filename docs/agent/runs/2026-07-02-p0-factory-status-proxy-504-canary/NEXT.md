# Next

1. Canary deploy backend status adapter on one server Agent Host with `KOLIBRI_FACTORY_CONTROL_URLS=http://10.99.0.10:9101,http://10.99.0.2:9101` and `FACTORY_STATUS_FETCH_TASKS=0`.
2. Smoke `http://127.0.0.1:8000/api/factory/status` and confirm HTTP 200, bounded latency, `source=control-plane`, and `control_plane.url=http://10.99.0.10:9101`.
3. Repair public edge TLS/request routing for `kolibriai.ru`; current public probes do not reach a valid backend response.
4. After edge repair, smoke strict HTTPS without `-k`: `curl --max-time 8 -fsS https://kolibriai.ru/api/factory/status`.

