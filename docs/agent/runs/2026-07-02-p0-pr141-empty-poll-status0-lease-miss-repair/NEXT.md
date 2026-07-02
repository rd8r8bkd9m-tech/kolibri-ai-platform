# NEXT

Run the strict runtime canary from a separate deploy/canary task after this branch is deployed through the normal release path.

Required checks:

- Empty-poll transport status `0` count remains zero at stages 250, 500, and 1000.
- `created_tasks == leased_tasks` through stage 1000.
- Thread count remains within the established canary gate.
- No `5xx` lease responses occur.
