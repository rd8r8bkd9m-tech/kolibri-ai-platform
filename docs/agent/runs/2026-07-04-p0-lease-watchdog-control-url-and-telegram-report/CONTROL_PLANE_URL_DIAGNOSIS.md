# Control Plane URL Diagnosis

Probe source: `server-kfrm`.

Candidates:

| URL | `/v1/health` | `/v1/fleet/registry` | `/v1/tasks/queue/diagnostics` | Role |
| --- | --- | --- | --- | --- |
| `http://10.99.0.2:9101` | timeout / HTTP 000 | timeout / HTTP 000 | timeout / HTTP 000 | inactive or unreachable from this node |
| `http://10.99.0.10:9101` | timeout / HTTP 000 | timeout / HTTP 000 | timeout / HTTP 000 | inactive or unreachable from this node |
| `http://10.99.0.1:9101` | HTTP 200 | HTTP 404 | HTTP 200 | active legacy/current endpoint |

Decision:

- `authoritative_control_plane`: `http://10.99.0.1:9101` for current `server-kfrm` watchdog path.
- `fallback_control_planes`: `["http://10.99.0.10:9101", "http://10.99.0.2:9101"]`.
- `bad_or_inactive_urls`: `["http://10.99.0.2:9101", "http://10.99.0.10:9101"]` until reachability is restored.

Note:

- `/v1/fleet/registry` is not available on `10.99.0.1` runtime, but queue diagnostics are available.
