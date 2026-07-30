# Kolibri V3 runtime invariants

These rules apply to every task under `kolibri-v3/`.

## Canonical development runtime

- Start the complete local product only from this directory with `npm run dev`.
- Never start `uvicorn`, `next dev`, a legacy systemd unit, or a parent
  repository backend directly for V3.
- `npm run dev` must remain bound to `scripts/dev-stack.mjs`. The supervisor
  must start the backend only through `scripts/dev-backend.sh`.
- `scripts/dev-backend.sh` owns the development database and auth preflight. It
  must keep the working directory at the V3 root, use
  `sqlite:///./var/kolibri-v3.db`, apply all migrations, and require exactly
  one active platform owner before opening port `8002`.
- The V3 Python environment is `kolibri-v3/backend/venv`. Do not use the parent
  repository `backend/venv` or a `.venv` path.
- The frontend may start only after launch-bound backend health reports
  `status=ok`, `service=kolibri-v3`, and the supervisor's exact development
  instance ID. A backend exit must fence and restart the frontend.
- `npm run dev:web` is intentionally blocked. It allowed a stale or unrelated
  process on port `8002` to masquerade as the V3 backend.

After a runtime restart, verify all of the following before claiming success:

1. preflight reports the latest migration and `platform_owner=1`;
2. `GET http://127.0.0.1:8002/v1/health` reports `service=kolibri-v3` and a
   non-empty development instance ID;
3. `GET http://127.0.0.1:3103/app` returns HTTP 200;
4. the existing owner session or an explicitly authorized owner login reaches
   the server-backed workspace.

Never bootstrap, rename, rotate, or overwrite the existing owner credential
unless the product owner explicitly requests that mutation.

## Release lane

- `deploy/portable` is the only V3 production release lane.
- The portable builder must audit the complete Git commit, not only the V3
  subtree, and reject parent-level V3 Home/Primary/bare-metal release helpers.
- The retired parent V3 coordinator is allowed only as its byte-exact,
  read-only tombstone.
- The deleted `deploy/install-home.sh`, static V3 systemd units and static
  Nginx file are legacy paths and must not be restored.
- Do not use parent-level experimental bare-metal units to start or deploy V3.
- Production requires a clean committed candidate, the portable release gates,
  backup/restore and rollback rehearsal, canary evidence, and explicit owner
  GO.
