# Label Taxonomy

## Required Labels

Priority:

- `P0`
- `P1`
- `P2`
- `P3`

Type:

- `type:bug`
- `type:feature`
- `type:docs`
- `type:infra`
- `type:security`
- `type:test`
- `type:refactor`
- `type:research`
- `type:agent-task`

Subsystem:

- `area:frontend`
- `area:backend`
- `area:control-plane`
- `area:agent-host`
- `area:telegram`
- `area:formula-lm`
- `area:estimates`
- `area:billing`
- `area:github-ci`
- `area:devops`
- `area:fleet`
- `area:model-factory`
- `area:docs`

Status:

- `status:ready`
- `status:blocked`
- `status:needs-review`
- `status:needs-split`
- `status:waiting-ci`
- `status:in-progress`
- `status:stale`
- `status:owner-approval`

Risk:

- `risk:low`
- `risk:medium`
- `risk:high`
- `risk:dangerous`

Agent:

- `agent:codex`
- `agent:mimo`
- `agent:api`
- `agent:review`
- `agent:qa`
- `agent:human`

## Current Gap

Existing labels are sparse and mostly legacy/default. They do not support factory-scale routing, risk gates or subsystem ownership.

## Application Policy

Create missing labels only after owner approval or as part of a dedicated GitHub metadata maintenance task. Label application to PRs/issues must be additive and must not replace existing labels without explanation.
