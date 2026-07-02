# Verification

Task: `P0_CANONICAL_20_SERVER_READINESS_MATRIX_2026_07_02`

Commands run:

```sh
pwd && hostname && uname -a
git status --short --branch
curl -fsS --max-time 4 http://10.99.0.10:9101/v1/health
curl -fsS --max-time 4 http://10.99.0.10:9101/v1/fleet/nodes
git ls-remote --heads origin main
command -v codex
command -v mimo
git diff --check -- docs/agent/runs/2026-07-02-p0-canonical-20-server-readiness-matrix
test -f docs/agent/runs/2026-07-02-p0-canonical-20-server-readiness-matrix/CANONICAL_20_SERVER_READINESS_MATRIX.md
test -f docs/agent/runs/2026-07-02-p0-canonical-20-server-readiness-matrix/RESULT.md
```

Results:

- Server execution verified on `kolibri` Linux.
- Control Plane `/v1/health` returned `status=completed`, `node=main`, `redis=PONG`.
- Control Plane `/v1/fleet/nodes` returned node cards used for the matrix.
- Git remote fetch visibility for `origin/main` passed and returned `f7ac32c70406432a52752ca45d87e35d9f1facd3`.
- `codex` and `mimo` binaries are present on this Agent Host.
- No provider-auth smoke, GitHub push, service restart, infrastructure mutation, or secret read was performed.
