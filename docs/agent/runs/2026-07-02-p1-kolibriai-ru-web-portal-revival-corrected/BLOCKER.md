# P1 kolibriai.ru Web Portal Revival Corrected

Task id: `P1_KOLIBRI_WEB_APP_PORTAL_REVIVAL_KOLIBRIAI_RU_CORRECTED_2026_07_02`

Branch: `p1/kolibriai-ru-web-portal-revival-2026-07-02`

Worker: `mesh-agent-20`

Execution path:
`/var/lib/kolibri-agent/logical-workers/mesh-agent-20/worktrees/P1_KOLIBRI_WEB_APP_PORTAL_REVIVAL_KOLIBRIAI_RU_CORRECTED_2026_07_02/P1_KOLIBRI_WEB_APP_PORTAL_REVIVAL_KOLIBRIAI_RU_CORRECTED_2026_07_02-attempt-1/repo`

## Status

`blocked_missing_selected_source`

Implementation was not performed because the corrected source-of-truth path
`remote/kolibriai-frontend` is absent from the task worktree, the cloned
repository, and all fetched GitHub branches. The owner instruction explicitly
marks root `frontend/` as the wrong source for this task unless the worker
produces live deployment evidence to the contrary. The available live audit
evidence does not establish root `frontend/` as the deployed kolibriai.ru app.

## Evidence

The assigned task worktree initially had no Git checkout:

- `pwd`: this task `repo` path.
- `git status --short --branch`: failed with `fatal: not a git repository`.
- `find . -maxdepth 3 -type d`: only `.`.
- `rg --files`: no files.

The worker environment provided `KOLIBRI_REPO_URL`, so the repository was cloned
into the empty task `repo` directory:

- `KOLIBRI_REPO_URL=git@github.com:rd8r8bkd9m-tech/kolibri-ai-platform.git`
- `git clone "$KOLIBRI_REPO_URL" .`: succeeded.
- `origin/main`: `f7ac32c70406432a52752ca45d87e35d9f1facd3`

Selected source lookup:

- `find remote/kolibriai-frontend -maxdepth 3 -type f`: `No such file or directory`.
- Remote branch scan for a top-level `remote/kolibriai-frontend` tree returned
  no matches.
- `git ls-tree -r --name-only origin/main` contains root `frontend/`, but no
  `remote/kolibriai-frontend`.
- `origin/p1/web-portal-revival-2026-07-02` contains root `frontend/`, but no
  `remote/kolibriai-frontend`.
- `origin/agent/TG-20260626080929-4297-kolibriairu/impl/kolibriairu` contains
  root `frontend/`, but no `remote/kolibriai-frontend`.
- `origin/agent/P0_AUTOPILOT_EXTRA_42_KOLIBRIAI_PUBLIC_SITE_GATE_2026_07_02/generic`
  contains root `frontend/` and live audit docs, but no `remote/kolibriai-frontend`.

Existing live audit artifact inspected:

- `docs/agent/runs/2026-07-02-p0-kolibriai-public-site-gate/RESULT.md`
- `docs/agent/runs/2026-07-02-p0-kolibriai-public-site-gate/result.json`

That audit reports `kolibriai.ru` currently resolves to `178.207.11.90`, serves
`MikroTik File Sharing` at `/`, has a TLS certificate for
`hcs0844dw9m.routingthecloud.net`, and returns HTTP `400` JSON at `/public`.
This is evidence of a wrong live route/origin, not evidence that root
`frontend/` is the deployed kolibriai.ru application source.

## Not Changed

- Root `frontend/` was not edited.
- Backend contracts were not changed.
- No factory-status compatibility shim was added.
- No destructive Git command was used.
- No local Mac work was performed.

## Exact Patch Plan Once Unblocked

1. Provide or restore the selected source at `remote/kolibriai-frontend` in the
   task worktree, or provide explicit live deployment evidence that authorizes
   using another path.
2. Inspect existing audit artifacts adjacent to that selected source and record
   the current live/backend contract endpoints before editing.
3. Create the smallest portal revival in the selected app source:
   keep the first screen as an actual Kolibri AI app/chat portal, preserve the
   existing chat/API contract, and avoid marketing-only or admin-dashboard
   layout.
4. Add only a tiny factory-status compatibility shim if the selected frontend
   already calls a status route that is known to differ from the deployed
   backend envelope.
5. Build the selected frontend and capture exact evidence:
   package manager version, install command, build command, output directory,
   PWA manifest/service-worker files, and any relevant smoke output.
6. If the source app has runtime tests or a Playwright smoke, run them against
   the built app and capture the artifact paths.
7. Commit only selected-source and evidence files to
   `p1/kolibriai-ru-web-portal-revival-2026-07-02`.

