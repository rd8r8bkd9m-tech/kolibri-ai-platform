# Home development authority preflight

Captured: 2026-07-12. Method: read-only operator diagnostics over the existing trusted SSH path. No Home file, Git ref, service or process was changed.

## Existing canonical layout

| Path | Fact |
| --- | --- |
| `/home/ladik/src` | exists, owned by `ladik` |
| `/home/ladik/src/mirrors/kolibri-ai-platform.git` | existing mirror with canonical GitHub origin |
| `/home/ladik/src/kolibri-ai-platform/control` | existing clean worktree |
| `/home/ladik/src/kolibri-ai-platform/tasks` | exists; zero task worktrees at capture |
| `/home/ladik/src/kolibri-ai-platform/releases` | missing |

The existing control worktree is clean at commit `2a885d69f6156a7ec10e0cc6ac1a3060a0dc3e90` on branch `codex/home-control-integration-20260711`. Its upstream association is stale and does not match the branch name. The new foundation branch `codex/kolibri-ai-os-foundation-20260712` is not yet present in the Home mirror.

Home has Codex CLI `0.142.2`, Git `2.43.0`, Cargo, Node and Python `3.12.3`. The public npm registry reports Codex CLI `0.144.1` on the same date, so the owner-gated Home toolchain transition must pin/verify that newer version rather than silently assuming the existing CLI is current.

The clean candidate now pins Node.js `26.5.0` and Python `3.14.6`, the newest stable non-RC releases verified from the official Node.js and Python release sources on 2026-07-12. Home has not been upgraded. The owner-gated bootstrap will refuse an apply while either installed patch version differs; it does not install runtimes itself.

## Exact remaining Gate 1 transition

1. Finish and verify the clean foundation commit on Mac.
2. Publish that non-production branch to the canonical Git remote.
3. Run the owner-approved Home development bootstrap once. It will fetch the mirror, refuse a dirty control worktree, safely switch the clean worktree to the new branch, create the missing releases directory, and leave production services unchanged.
4. Prove the first task worktree, tests, commit and artifact originate on Home before calling Mac a thin client.

No `reset --hard`, production restart, deploy, DNS, credential copy, NFS or rsync operation belongs to this transition.
