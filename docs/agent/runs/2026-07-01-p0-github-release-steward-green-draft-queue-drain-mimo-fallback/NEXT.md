# Next

Owner-gated next actions:

1. Install or expose a read-only GitHub status tool on `mesh-agent-01`, then recheck each priority PR immediately before any owner decision.
2. If the snapshot still holds, consider owner approval for docs batch #88/#92 first.
3. After docs batch canaries, consider owner approval for runtime safety batch #96/#97.
4. After runtime safety canaries, consider owner approval for #85.
5. Re-evaluate #91 after #96/#97/#85 are resolved.
6. Re-evaluate #89 only after Telegram receiver/cutover safety evidence is current.
7. Re-evaluate #83 against #96 to decide whether it is additive, needs repair, or is superseded.

Required before any merge task:

- Current head SHA and CI check confirmation.
- Current mergeability confirmation.
- Draft/owner mark-ready approval.
- Diff whitespace check.
- Secret-pattern scan over changed files.
- Explicit post-merge canary owner.

Do not automate mark-ready, merge, approval, close, force-push, or push to `main` from this artifact.
