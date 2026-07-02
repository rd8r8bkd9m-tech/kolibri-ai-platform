# Tests And Probes

Execution node:

- `hostname && uname -a && date -u +%Y-%m-%dT%H:%M:%SZ`
  - `kolibri`
  - `Linux kolibri 6.8.0-36-generic ... x86_64 GNU/Linux`
  - `2026-07-02T02:26:48Z`

Repository state:

- `git status --short --branch`
  - clean before artifact edits
- `git remote -v`
  - `origin git@github.com:rd8r8bkd9m-tech/kolibri-ai-platform.git`
- `git rev-parse --abbrev-ref HEAD`
  - `agent/P0_MAIN_PR_QUEUE_MERGE_DISCIPLINE_STEWARD_2026_07_02/generic`
- `git rev-parse HEAD`
  - `f7ac32c70406432a52752ca45d87e35d9f1facd3`
- `git ls-remote --heads origin main`
  - `f7ac32c70406432a52752ca45d87e35d9f1facd3 refs/heads/main`

GitHub metadata access:

- `command -v gh || true`
  - no `gh` binary found on this server
- `curl -fsSL ... https://api.github.com/repos/rd8r8bkd9m-tech/kolibri-ai-platform/pulls?...`
  - `404`, consistent with unauthenticated private-repo metadata blocker

PR #90 blocker probe:

- `git ls-remote origin 'refs/pull/90/*' 'refs/heads/p0/telegram-miniapp-owner-auth-contract-2026-07-01'`
  - branch/head `0fb48df868991ce2d23f326b87fe0e09e118bc3f`
  - merge ref `68f3d6f581816263a43b8edd947aff03be0fca0c`
- `git ls-tree -r --name-only HEAD -- docs/agent/runs/2026-07-01-p0-telegram-miniapp-owner-auth-contract`
  - no output; current `main` lacks the artifact path
- `git ls-tree -r --name-only 0fb48df868991ce2d23f326b87fe0e09e118bc3f -- docs/agent/runs/2026-07-01-p0-telegram-miniapp-owner-auth-contract`
  - exact canonical docs exist on PR #90 branch

Candidate hygiene probes:

- `git fetch --no-tags origin refs/pull/{65,84,87,88,90,99,100,101,102,103,104}/head:refs/remotes/origin/pr/{...}`
  - fetched successfully
- `git diff --check HEAD...refs/remotes/origin/pr/$pr`
  - pass: #84, #99, #100
  - fail: #65, #87, #88, #90, #101, #102, #103, #104
- Narrow secret-pattern scan over docs/README/artifact diffs for #65, #84, #87, #88, #90, #99, #100, #101, #102, #103, #104:
  - no hits

No product test suite was run because this pass only updates release stewardship documentation. Runtime/product PRs remain blocked on their own focused verification.
