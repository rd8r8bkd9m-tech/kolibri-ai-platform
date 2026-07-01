# Handoff To Control Plane

Task ID: `2026-06-30-project-intelligence-all-branches`

## Reason For Handoff

This request must run on a server node through the Kolibri Control Plane. The current executor is macOS on `MacBook-Air-Vladislav.local`, which violates the request's hard invariant for repository-wide scanning and all-branch analysis.

Do not continue this task on the Mac.

## Remote Execution Goal

Build a complete, safe, reproducible project intelligence package for the Kolibri project across:

- current dirty working tree;
- all local branches;
- all remote branches;
- all known servers and live Control Plane nodes;
- key subsystems;
- CI/PR state;
- documentation;
- risks;
- recommended next actions.

Primary output directory on the server-side project worktree:

```text
docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/
```

Most important artifact:

```text
docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/PROJECT_DIGEST_FOR_CHATGPT.md
```

## Required Remote Artifacts

Create these files from the server-side execution:

```text
EXECUTIVE_SUMMARY.md
PROJECT_MAP.md
BRANCH_MATRIX.md
BRANCH_DEEP_DIVE.md
DIRTY_TREE_REPORT.md
SUBSYSTEM_MAP.md
CI_GITHUB_REPORT.md
DOCS_INDEX.md
API_SURFACE_MAP.md
FRONTEND_MAP.md
DEVOPS_MAP.md
AI_LLM_MAP.md
FORMULALM_MAP.md
CONTROL_PLANE_MAP.md
TELEGRAM_REPORTING_MAP.md
ESTIMATES_BILLING_MAP.md
RISK_REGISTER.md
UNKNOWN_UNCLEAR_AREAS.md
SUPERFACTORY_READINESS.md
PROJECT_DIGEST_FOR_CHATGPT.md
NEXT_TASKS.md
SERVER_INVENTORY.md
```

Also create branch-specific reports under:

```text
docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/branches/
```

Also create server-specific reports under:

```text
docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/servers/
```

## Control Plane Submission Envelope

Submit this from an environment that is allowed to enqueue Control Plane work:

```json
{
  "task_id": "2026-06-30-project-intelligence-all-branches",
  "kind": "project_intelligence",
  "goal": "Build the full Kolibri Project Intelligence Pack across all local and remote branches and all known Kolibri servers/nodes from a server node, without modifying product code.",
  "source": {
    "requested_by": "Vladislav",
    "origin": "mac-thin-client-handoff",
    "mac_handoff_path": "docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/HANDOFF_TO_CONTROL_PLANE.md"
  },
  "constraints": {
    "autopilot_level": "A1/A2",
    "server_execution_required": true,
    "mac_thin_client_only": true,
    "code_implementation_forbidden": true,
    "product_code_modification_forbidden": true,
    "secrets_redaction_required": true,
    "destructive_git_commands_forbidden": true,
    "git_push_forbidden": true,
    "dirty_main_worktree_checkout_forbidden": true,
    "prefer_read_only_git_inspection": true,
    "use_temp_mirror_or_safe_worktree_for_branch_analysis": true
  },
  "acceptance": [
    "Execution happens on a server node through Control Plane, not on the Mac.",
    "Original working tree is left untouched except for generated intelligence documentation.",
    "All required intelligence files are created under docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/.",
    "All known servers and live Control Plane nodes are documented, including home, main, uiap, qjns, 9fts, new, primary-candidate, home-live, and mesh shadow nodes when present.",
    "PROJECT_DIGEST_FOR_CHATGPT.md is written in clear Russian and includes the requested machine-readable YAML summary block.",
    "Secrets, tokens, private keys, cookies, and credential values are not printed.",
    "Branch analysis uses read-only inspection and a temporary mirror clone or safe worktree approach.",
    "Failures in clone/auth/network/GitHub access are classified and documented, and local refs are used as fallback where safe."
  ]
}
```

Suggested dispatcher command, following the current Kolibri Factory Admin workflow:

```bash
ops/kolibri-dispatch submit --file /path/to/2026-06-30-project-intelligence-all-branches.envelope.json
```

## Remote Worker Instructions

1. Start with a Phase 0 environment and safety check on the server node.
2. Confirm the node is not macOS and is registered/leased through the Control Plane.
3. Record hostname, user, working directory, OS release, date/time, git version, current branch, redacted remotes, disk space, dirty state, and server/Mac classification in `ENVIRONMENT.md`.
4. If the remote node is also a Mac, create a new handoff and stop.
5. Inspect the current working tree without checkout, stash, reset, or cleanup.
6. Use a temporary mirror clone or safe worktree outside the main working tree for all-branch analysis.
7. Fetch branch metadata safely. If fetch/clone/auth/network fails, classify the failure and continue from available local refs.
8. Build the branch matrix, per-branch deep dives, subsystem maps, docs index, API/frontend/devops/LLM/FormulaLM/Control Plane/Telegram/estimates/billing maps, GitHub/CI report, risk register, unknowns, readiness report, and next tasks.
9. Build `SERVER_INVENTORY.md` and `servers/<node>.md` reports for every known server and every live Control Plane node.
10. Write `PROJECT_DIGEST_FOR_CHATGPT.md` as the primary Russian-language digest for future ChatGPT and agent handoff.
11. Do not modify product code, fix bugs, reformat files, delete files, force push, push, reset, clean, or checkout branches in a dirty main worktree.

## Important Branches And Areas To Prioritize

Prioritize:

- `main`;
- `primary-candidate`;
- `qjns`;
- branches touching Control Plane;
- branches touching FormulaLM;
- branches touching estimates;
- branches touching billing;
- branches touching Telegram reports;
- branches touching frontend/PWA;
- branches touching GitHub/CI;
- branches with large diffs;
- branches with recent activity;
- branches with agent-generated changes.

Subsystems to map:

- Control Plane;
- Agent Host;
- FormulaLM;
- AI/LLM provider stack;
- Telegram reports;
- deterministic estimates;
- billing;
- frontend/PWA;
- DevOps/bootstrap;
- GitHub/CI/PR.

Servers/nodes to map:

- `home` / `10.99.0.1` / training hub, Redis, mesh coordinator/chat;
- `main` / `10.99.0.2` / API gateway, frontend, likely Control Plane;
- `uiap` / `10.99.0.3` / RAG and knowledge base;
- `qjns` / `10.99.0.4` / agent executor, possibly quarantined;
- `9fts` / `10.99.0.5` / inference and implementation worker;
- `new` / reviewer node mentioned in dispatcher;
- `primary-candidate` / director or logical Control Plane node if registered;
- `home-live` / default mesh executor if registered;
- every `mesh-*` shadow node registered by `ops/mesh_control_bridge.py`.

Each server report must include OS, uptime, CPU/RAM/disk, Kolibri services, listening ports, Control Plane heartbeat, Agent Host capabilities, repo branch/commit/dirty status, artifact/worktree summary, health checks, redacted env names, blockers, and recommended action.

## Digest Requirements

`PROJECT_DIGEST_FOR_CHATGPT.md` must explain in Russian:

- what Kolibri Factory is;
- what exists in the repo;
- what branches exist;
- what each important branch contains;
- what is dirty;
- what is finished, running, and blocked;
- where Control Plane, Agent Host, FormulaLM, Telegram, estimates, billing, PWA, bootstrap, and docs live;
- what is known about each server/node and what remains unknown;
- what the next correct action should be.

End the digest with:

```yaml
project: Kolibri Factory
task_id: 2026-06-30-project-intelligence-all-branches
default_branch: ...
current_branch: ...
important_branches:
  - name: ...
    purpose: ...
    status: ...
    risk: ...
dirty_tree:
  status: ...
  subsystems: [...]
main_blockers:
  - ...
next_tasks:
  - ...
must_read_files:
  - ...
thin_client_invariant: true
server_execution_required: true
```

## Local Mac Work Performed

Only these safe local actions were performed before stopping:

- read the attached task text;
- checked minimal Phase 0 environment facts;
- confirmed the executor is macOS;
- confirmed the pre-handoff working tree appeared clean;
- created this handoff and `ENVIRONMENT.md`.

No repository-wide scan, fetch, branch checkout, dependency installation, CI inspection, or product-code modification was performed on the Mac.
