# Tests

Verification commands run:

```bash
python3 ops/kolibri-dispatch fabric-routes
python3 ops/kolibri-dispatch --control-url http://10.99.0.10:9101 fabric-routes
python3 ops/kolibri-dispatch --control-url http://10.99.0.10:9101 fabric-route reserve242 --required-capability read_only_probe
```

Endpoint matrix:

| Base | Route | HTTP | Result |
| --- | --- | ---: | --- |
| `http://10.99.0.2:9101` | `/health` | 200 | primary control listener reachable |
| `http://10.99.0.2:9101` | `/v1/health` | 200 | primary control listener reachable |
| `http://10.99.0.2:9101` | `/v1/fabric/health` | 404 | live listener lacks Fabric aliases |
| `http://10.99.0.2:9101` | `/v1/fabric/routes` | 404 | primary API route unavailable |
| `http://10.99.0.2:9101` | `/v1/fleet/nodes` | 404 | primary fleet alias unavailable |
| `http://10.99.0.2:9101` | `/v1/models` | 404 | primary model alias unavailable |
| `http://10.99.0.10:9101` | `/health` | 200 | fallback control listener reachable |
| `http://10.99.0.10:9101` | `/v1/health` | 200 | fallback control listener reachable |
| `http://10.99.0.10:9101` | `/v1/fabric/health` | 200 | fallback Fabric API available |
| `http://10.99.0.10:9101` | `/v1/fabric/routes` | 200 | fallback route list available |
| `http://10.99.0.10:9101` | `/v1/fleet/nodes` | 200 | fallback fleet list available |
| `http://10.99.0.10:9101` | `/v1/models` | 200 | fallback model alias available |
| `http://127.0.0.1:9101` | `/health` | 000 | no local listener expected in worker worktree |
| `http://31.57.26.242:9101` | `/health` | 000 | direct reserve242 Agent/Fabric listener refused connection |

Focused route results:

- `reserve242` route on fallback Fabric API: `status=ok`, `route.type=direct_fabric_api`, advertised endpoint `/v1/nodes/reserve242`, fallback relay `/v1/fabric/relay`.
- `mesh-reserve242` route on fallback Fabric API: HTTP 503 structured `status=blocked`, `reason=target_node_unavailable`, `can_continue_elsewhere=true`.
- Advertised direct node detail endpoints `/v1/nodes/reserve242` and `/v1/nodes/mesh-reserve242` returned 404 on the fallback listener.
