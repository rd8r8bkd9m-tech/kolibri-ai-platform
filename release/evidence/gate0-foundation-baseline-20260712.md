# Gate 0 foundation baseline

Captured: 2026-07-12. Scope: local read-only Git/worktree evidence. Production was not contacted or changed. Secret-bearing files were not read.

## Selected clean base

- Branch: `codex/kolibri-ai-os-foundation-20260712`
- Base commit: `9028a20d8522649e419dcae31ce906bebf7ad6b1`
- Base tree: `7467d97d746c5a85e09c3fc21bb87099940a2f75`
- Reason: it is the newest clean tracked Home-first compatibility foundation and already contains the frozen contracts plus Rust task parity slice.

## Preserved donors

| Donor | State at capture | Handling |
| --- | --- | --- |
| Active Vista/product worktree | branch `codex/vista-full-os-integration-2026-07-08`, HEAD `19ef9014`, dirty | left untouched |
| Home-first donor | branch `codex/home-first-release-20260711`, HEAD `9028a20d`, important untracked Clean V2 files | left untouched; focused import only |
| OS implementation donor | branch `codex/kolibri-os-implementation-20260710`, HEAD `2a885d69` | left untouched |
| Rust swarm donor | branch `codex/kolibri-rust-swarm-core-20260710`, HEAD `69f3b844`, generated target tree | left untouched; source review only |
| Rust foundation donor | branch `p0/free-low-cost-model-provider-registry-20260704`, HEAD `bbeeec49`, dirty | left untouched; no wholesale merge |

## Initial contract truth

- `home` is the only Control Plane identity.
- Public model identity is `kolibri`.
- Membership, heartbeat freshness and execution proof are distinct facts.
- No claim of fresh `21/21` execution is made by this baseline.
- Clean V2 and Rust shadow tests are donor evidence, not production proof.

The next evidence record must contain the architectural legacy-authority scan and the pinned-toolchain test result.
