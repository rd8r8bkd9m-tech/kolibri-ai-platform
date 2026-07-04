# CONTROL_PLANE_AUTHORITY_AND_FALLBACK

## Result

`active_control_plane`: `http://10.99.0.1:9101`

`standby_control_plane`: none currently proven reachable from this host.

`bad_urls`:

- `http://10.99.0.10:9101`: timed out from this host.
- `http://10.99.0.2:9101`: timed out from this host.

`fallback_order`:

```text
http://10.99.0.10:9101,http://10.99.0.2:9101,http://10.99.0.1:9101
```

## Evidence

- `http://10.99.0.1:9101/v1/health`: HTTP 200, Redis `PONG`.
- `http://10.99.0.1:9101/v1/tasks/queue/diagnostics`: HTTP 200.
- `http://10.99.0.1:9101/v1/fleet/nodes`: HTTP 200.
- `http://10.99.0.1:9101/v1/fleet/registry`: HTTP 404, route not implemented.
- `http://10.99.0.1:9101/v1/fleet/drift`: HTTP 404, route not implemented.
- `http://10.99.0.10:9101/*`: timeout.
- `http://10.99.0.2:9101/*`: timeout.

## Gateway behavior

The gateway tries every configured URL with bounded timeout. A dead `10.99.0.2` no longer blocks the request when a later endpoint is reachable.

If all endpoints fail, the gateway returns:

```json
{
  "status": "blocked",
  "repair_task": "P0_REPAIR_CONTROL_PLANE_API",
  "blocked_reason": "control_plane_unavailable"
}
```
