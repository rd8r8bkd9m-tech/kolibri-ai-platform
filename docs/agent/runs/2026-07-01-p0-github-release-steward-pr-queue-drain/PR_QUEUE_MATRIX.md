# PR Queue Matrix

Source: server-created report from `P0_GITHUB_RELEASE_STEWARD_PR_QUEUE_DRAIN_2026_07_01`.

| PR | Title | Base | Group | Next action |
| --- | --- | --- | --- | --- |
| #96 | Enforce read-only Agent Host permission packs | `main` stale before PR #95 | repair | Rebase/update after PR #95, verify runner permission tests, then owner release decision. |
| #94 | Record PR85 release gate after Prompt3 repair | `main` stale before PR #95 | blocked | Keep blocked behind PR #85 docs whitespace repair and PR #85 release gate. |
| #93 | Record PR85 Fabric API gap review | `main` stale before PR #95 | stale | Superseded by #94 for PR #85 gate evidence; close/archive only by owner after #94/#85 decision. |
| #92 | Document fleet role and capability inventory | `main` stale before PR #95 | deeper-review | Rebase after #95, review docs for stale fleet claims, then merge only after #91 owner decision. |
| #91 | Fix MIMO runner output and auth classification | `main` stale before PR #95 | deeper-review | Owner release decision, then canary Agent Host deploy and direct MIMO probes. |
| #90 | Repair Telegram Mini App owner auth verifier contract | `main` stale before PR #95 | repair | Rebase after #95 and rerun exact venv verifier. |
| #89 | Telegram Superfactory bot and Mini App command layer | `main` stale before PR #95 | split | Split verifier/auth prerequisites, single receiver migration, and bot/Mini App layer. |
| #88 | docs: add factory dispatcher ledger | `main` stale before PR #95 | merge | Docs-only candidate after rebase and `git diff --check`. |
| #87 | docs: add Kwork revenue manager package | `main` stale before PR #95 | repair | Rebase and review business docs for current identity/confirmation gates. |
| #86 | Establish Kolibri GitHub Operating System | `main` stale before PR #95 | deeper-review | Governance PR requires owner approval and conflict repair after #95. |
| #85 | Finalize API-first full-control Fabric | `main` stale before PR #95 | repair | Run PR #85 whitespace fix, rebase after #95, rerun tests, then owner release decision. |
| #84 | Add Kolibri Superfactory master canvas | `main` stale before PR #95 | merge | Docs-only merge candidate after rebase and `git diff --check`. |
| #83 | Harden Agent Host runner contract | `main` stale before PR #95 | deeper-review | High-value runtime prerequisite; rebase after #95, rerun full tests, then owner canary/merge decision. |
| #81 | Live Telegram dialog without TGCHAT tasks | `main` stale before PR #95 | split | Separate runtime fixes from live Telegram behavior; wait for #83/#91/#89 sequencing. |
| #74 | FormulaLM R&D preflight artifacts | `codex/factory-autonomy-pwa-billing` | blocked | Blocked on #46 base decision and FormulaLM runtime restoration. |
| #65 | GoMesh rollout verification runbook | `factory/KOL-LAUNCH-20260624-control-plane` | merge | Docs/tooling candidate after base branch strategy decision; no whole-LAN rollout from merge. |
| #61 | Telegram miniapp and owner director bot | `main` stale before PR #95 | deeper-review | Likely superseded/overlapped by #89/#90/#81. |
| #60 | Home result capture | `codex/factory-autonomy-pwa-billing` | stale | Fold into #46 train or close after owner approval. |
| #46 | Factory autonomy, PWA billing, remote FormulaLM | `main` stale before PR #95 | split | Split into frontend/PWA, billing, factory runtime, estimator, and FormulaLM tracks. |
| #25 | Temporary Codex subagent bootstrap exception | old `main` | stale | Supersede with explicit expiry/closure plan after #83/#91 gates pass. |
| #24 | Directive compiler foundation | `codex/kolibri-vertical-slice` | deeper-review | Non-main base; needs branch-train decision. |
| #8 | Execution and Git contracts | old `main` | stale | Superseded by later governance/runtime docs. |
| #7 | Remote dispatch smoke | old `main` | stale | Historical canary proof; archive or close by owner. |
| #6 | Frontend v3 canvas shell | `factory/KOL-LAUNCH-20260624-control-plane` | deeper-review | Needs visual QA and current frontend strategy decision. |
| #5 | Estimate PDF totals pagination | `factory/KOL-LAUNCH-20260624-control-plane` | repair | Repair remote PDF QA dependencies or explicitly accept local QA. |
| #4 | Factory launch directive and Primary bootstrap evidence | `codex/public-proxy-chat-contract` | stale | Historical launch evidence on nested base. |
| #3 | Public chat proxy contract | `codex/mimo-orchestration` | repair | Rebase/port proxy contract onto current backend and run smoke. |
| #2 | Agent branch hostvds-agent-02 | `codex/mimo-orchestration` | stale | Inspect diff and close if no unique artifact. |
| #1 | Agent proof hostvds-agent-06 | `codex/mimo-orchestration` | stale | Archive proof artifact or close after owner approval. |
