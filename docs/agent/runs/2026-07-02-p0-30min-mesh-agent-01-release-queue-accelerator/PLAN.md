# Plan

Task id: `P0_30MIN_MESH_AGENT_01_RELEASE_QUEUE_ACCELERATOR_2026_07_02`

Node: `mesh-agent-01`

Goal: run a bounded release queue accelerator that moves Kolibri PR queue exit
out of P0 by separating completed post-merge work, runtime-only blockers, and
metadata-only PR evidence gaps.

Scope:

- Do not mutate GitHub PRs, `main`, credentials, services, or Telegram state.
- Use read-only repository and `git ls-remote` evidence.
- Create reusable queue classification code for nodes without `gh`.
- Produce exact run artifacts with the queue exit decision and next tasks.

Exit rules:

- Pull ref visibility alone is not an open-PR blocker because GitHub keeps pull
  refs visible after merge.
- Previously recorded merged PRs stay out of P0 unless a post-merge canary
  fails with product/runtime evidence.
- Owner merge decisions still require live GitHub metadata before mark-ready,
  approve, merge, close, or force-push actions.
