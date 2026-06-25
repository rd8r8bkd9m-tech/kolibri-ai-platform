# Kolibri Agent Loader

This repository uses Codex as the chief orchestrator for the Kolibri project.

Mandatory instruction load order for every session:

1. Read this `AGENTS.md`.
2. Read and obey `AGENTS.override.md`.
3. Read `MASTER_DIRECTIVE.md` for the canonical product direction.
4. Treat `.factory/` and recorded artifacts as the durable control plane when
   present.

The permanent execution contract is in:

```text
AGENTS.override.md
```

The permanent product directive is in:

```text
MASTER_DIRECTIVE.md
```

If `AGENTS.override.md` is missing or unreadable, stop orchestration work and
report `BLOCKERS:` with the missing contract path.

If `MASTER_DIRECTIVE.md` is missing or unreadable, stop product rewrite work and
report `BLOCKERS:` with the missing directive path. Audit, backup, and test
work may continue because those actions preserve the project state.
