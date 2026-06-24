# Kolibri launch conflict report

Run: `launch-20260624T212027Z`

## Resolved For This Run

- The permanent source of truth is `.factory/MASTER_DIRECTIVE.md`; it was copied
  from the owner-provided file and verified with SHA-256
  `03f66161f25be36c54bd394f79fd9aebeb629f84c413278199128d264cbf91cb`.
- The launch prompt is `.factory/LAUNCH_PROMPT.txt`; it was verified with SHA-256
  `bc330675f73e192b962dfc41ee7e6b6f64338e7e81c97ab2828b209b29f8d83f`.
- Root `AGENTS.md` now points to both files and declares historical instructions
  lower priority than `MASTER_DIRECTIVE.md`.
- Stale `KOL-CANARY-001` and `KOL-CANARY-002` task envelopes were moved from
  `.factory/tasks/running/` to `.factory/tasks/stale/`; status JSON and logs are
  retained as historical evidence.

## Active Conflicts

- Branch naming: existing Factory schemas use `factory/<task-id>-<slug>`, while
  `MASTER_DIRECTIVE.md` specifies `agent/<task-id>/<agent-id>/<slug>`. For this
  run, existing schema-compatible `factory/` branches remain in task envelopes
  until the schema is migrated deliberately.
- Task state naming: existing Factory uses ready/running/review/blocked files,
  while `MASTER_DIRECTIVE.md` defines `CREATED/QUEUED/ASSIGNED/...`. For this run,
  current file layout is preserved and launch run records map these states
  explicitly.
- Server count: previous Factory records describe 19 registered servers; the new
  directive says 20 existing servers. Current evidence still shows 19 entries in
  `ops/agents.yml`; the missing twentieth node must be identified before claiming
  a 20-node fleet.
- Product root: `frontend/`, `apps/frontend-v2`, and `apps/frontend-v3` coexist.
  For this launch, v3 is the priority product surface, while `frontend/` remains
  preserved and must not be replaced silently.

## Security Notes

- Passwords pasted into chat are not used in commands, stdin, files, or logs.
- Primary `78.17.4.108` key-only root access is working.
- Home `ladik@178.207.11.90:2222` key-only access is working; Home root key-only
  access is blocked.
- Protected remote copies `.env` and `.mimocode` found under
  `/opt/kolibri/repo` on Primary were removed without reading their contents.
