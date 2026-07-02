# Plan

Task: `P0_EXEC_KOLIBRIAI_FACTORY_PANEL_DURABLE_BACKEND_2026_07_02`

Goal: replace the tactical public factory panel status repair with a durable backend/proxy contract for `kolibriai.ru`.

## Steps

1. Verify repository state and existing factory-panel API/frontend/proxy wiring.
2. Probe public `kolibriai.ru` endpoints without printing secrets.
3. Make the backend factory status route durable for public panel use:
   - return a stable JSON contract even when the control plane is unreachable,
   - expose explicit compatibility aliases for the panel and cluster route.
4. Make nginx route ownership explicit:
   - exact factory status API locations before generic `/api/`,
   - websocket headers retained,
   - deploy script installs nginx config with a timestamped rollback copy.
5. Add tests for backend fallback semantics, route aliases, nginx exact routes, and deploy rollback behavior.
6. Run focused verification and document result, risks, and next action.
