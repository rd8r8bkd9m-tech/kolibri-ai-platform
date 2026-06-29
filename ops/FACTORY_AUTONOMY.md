# Kolibri Factory Autonomy

This is the operating contract for scaling Kolibri Factory nodes and agents.

## Golden Node Profile

Every server should be bootstrapped with the same Agent Host profile:

```bash
KOLIBRI_FACTORY_CONTROL_URLS=http://10.99.0.2:9101 \
KOLIBRI_BOOTSTRAP_RESTART_JITTER=60 \
sudo -E ops/bootstrap_factory_node.sh
```

Default capabilities:

```text
read_only_probe,generic_implementation,review,image_generation,mesh_node,permission:*
```

Default permission pack:

```text
full_autonomy
```

Node identity is stable per machine. Worktrees and artifacts stay local to each
node under `/var/lib/kolibri-agent`; Control Plane stores manifests, leases,
state, and result references.

## Control Plane Rules

- All work enters through `/v1/tasks` or `ops/kolibri-dispatch submit --file`.
- Tasks requiring autonomous work use `kind: owner_remote_task` or
  `kind: generic_implementation`.
- Autonomous tasks default to `permission_pack: full_autonomy`.
- Lease is granted only when node capabilities and permissions match the task.
- Nodes must heartbeat; stale nodes are reported as `health: stale`.
- `ops/kolibri-dispatch status` defaults to a compact summary. Use `--full`
  only for targeted debugging.

## Role Catalog

Roles live in `ops/factory_role_catalog.json`. Do not hard-code unique server
personalities. New servers remain identical; role assignment happens per task
through `role_slot`, `role_goal`, `acceptance`, and optional `role_catalog`.

Key role slots:

- `product_director`
- `principal_engineer`
- `product_designer`
- `qa_lead`
- `factory_sre`
- `skill_librarian`
- `estimate_methodologist`
- `formulalm_researcher`
- `sales_operator`
- `reviewer`

## Skill Distribution

Skill bundle metadata lives in `ops/skill_bundle_manifest.json`. Distribute
skills through Control Plane tasks, not manual SSH sessions. Skill payloads must
avoid secrets and must be installed under the node-local skills root.

If a node cannot access a referenced skill source, it reports a missing-skill
artifact instead of silently continuing.

## GitHub Communication

GitHub is the fallback communication channel for agents and external teams.

- Agents commit verified work to branches.
- Review/correction happens through pull requests or GitHub-visible reports.
- An hourly Codex automation named `kolibri-hourly-verified-github-sync` checks
  this worktree, commits verified progress, and pushes to GitHub.
- Never commit secrets or local env files.

## Product QA Gate

Before owner handoff:

1. Run local focused tests and build checks.
2. Launch the SPA/PWA locally and verify the product flow manually or with
   browser automation.
3. Submit an independent factory QA task to `qa_lead`.
4. Fix all blockers.
5. Submit a second independent product QA pass.
6. Report readiness only after blockers are closed.

If required product data is missing, the owner is contacted through Telegram.

## Deterministic Estimates

Estimate generation must be deterministic for identical inputs:

- canonical input hash;
- fixed pricebook version;
- fixed region profile;
- deterministic totals in code;
- editable estimate after generation;
- model output may suggest scope, but totals and prices are normalized and
  recalculated outside the model.

The current baseline pricebook is `kolibri-ru-2026q2-v1`.

## FormulaLM R&D

`formulalm_researcher` owns the research track for formula-based LLM methods:

- collect reproducible FormulaLM/formula-discovery references;
- design deterministic formula extraction and comparison tests;
- run benchmark tasks only on remote factory nodes, never on the owner's Mac;
- report formulas, datasets, metrics, and risks as artifacts.

The Mac is a control/editing surface only. Model experiments, load tests,
benchmarks, and FormulaLM/Qwen comparisons must be dispatched through Control
Plane and executed on remote servers.
