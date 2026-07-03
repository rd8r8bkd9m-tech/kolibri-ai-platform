# Port Registry

Port source: `PORT_REGISTRY` in `ops/factory_registry.py`.

| Port | Service IDs | Notes |
| --- | --- | --- |
| 6379 | redis | Local-only Redis backend |
| 5173 | frontend_dev | Dev frontend only when service is running |
| 9101 | control_plane, mesh_bridge | Fabric API path |
| 19131 | backend_staging | Staging backend |
| 19132 | frontend_preview | Stable preview frontend |

Port 5173 is not the stable preview. If unavailable, agents should suggest 19132 only after checking service state.

