# Rollout Policy

Scaling order:

```text
0. local dry-run
1. two read-only canaries
2. four read-only agents
3. eight read-only agents
4. controlled mutation on one server
5. 18/19-node queue
6. production deploy only after human approval
```

Do not optimize for number of busy servers. Optimize for independent useful
work with reviewable output.

No two concurrent tasks may mutate the same files unless `.factory/memory/decisions.md`
contains a written integration plan.
