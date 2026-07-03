# Service Endpoint Registry

Service source: `SERVICE_ENDPOINT_REGISTRY` in `ops/factory_registry.py`.

| Service | URL | Unit | Health |
| --- | --- | --- | --- |
| control_plane | http://10.99.0.10:9101 | kolibri-factory-control.service | /v1/health |
| backend_staging | http://10.99.0.10:19131 | kolibri-staging-pr31-backend.service | /api/health |
| frontend_preview | http://10.99.0.10:19132 | kolibri-staging-pr31-frontend.service | / |
| frontend_dev | http://10.99.0.10:5173 | kolibri-frontend-5173.service | / |
| mesh_bridge | http://10.99.0.10:9101 | kolibri-mesh-control-bridge.service | /v1/health |
| redis | redis://127.0.0.1:6379 | redis-server.service | PING |

Agents must check this registry before telling the owner which URL to open.

