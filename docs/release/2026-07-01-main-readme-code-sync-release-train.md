# Main README/Code Sync Release Train - 2026-07-01

Task id: `P0_GITHUB_MAIN_README_CODE_SYNC_RELEASE_TRAIN_2026_07_01`

Execution node: remote server worktree at
`/var/lib/kolibri-agent/worktrees/P0_GITHUB_MAIN_README_CODE_SYNC_RELEASE_TRAIN_2026_07_01/P0_GITHUB_MAIN_README_CODE_SYNC_RELEASE_TRAIN_2026_07_01-attempt-1/repo`.

Main branch policy:

- No direct push to `main`.
- No merge without owner approval.
- Keep each PR focused; do not mix unrelated code, docs, operations, or release
  artifacts.
- Use CI evidence or record exact blocker classification before owner review.

## This PR Scope

Branch: `p0/main-readme-release-train-2026-07-01`

Scope: README and release-train documentation only.

Changed files:

- `README.md`
- `docs/release/2026-07-01-main-readme-code-sync-release-train.md`

PR creation blocker:

- `gh` is not installed on the remote server node.
- Unauthenticated GitHub REST metadata returned HTTP 404 for this private
  repository context.
- Branch push is the safe remote action available from this node. Owner can
  create the PR from:
  `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/compare/main...p0/main-readme-release-train-2026-07-01`

## Release Gate Matrix

Classification is based on `git ls-remote origin 'refs/pull/*'`, fetched PR
head/merge refs, latest commit subjects, branch names, and file diffs against
`origin/main`. GitHub PR title/review/status metadata was blocked from this
remote node, so `no-merge-ref` means the remote could not fetch a PR merge ref;
it must be treated as blocked/stale until GitHub UI or an authenticated owner
check proves otherwise.

| PR | Branch evidence | Gate class | Diff scope | Owner action |
| --- | --- | --- | --- | --- |
| #1 | `factory/agent-hostvds-agent-06-docs-commit-proof` | stale large train candidate | 236 files across baseline/factory/docs | Do not merge in README train; needs separate owner triage. |
| #2 | `factory/agent-visible-pr-hostvds-agent-02` | stale large train candidate | 230 files across baseline/factory/docs | Do not merge in README train; needs separate owner triage. |
| #3 | `codex/public-proxy-chat-contract` | stale large train candidate | 236 files across baseline/factory/docs | Do not merge in README train; needs separate owner triage. |
| #4 | `factory/KOL-LAUNCH-20260624-control-plane` | stale large train candidate | 257 files across baseline/factory/docs | Do not merge in README train; needs separate owner triage. |
| #5 | `agent/KOL-PDF-PAGINATION-20260625-001/primary/pdf-pagination` | stale large train candidate | 257 files across baseline/backend/frontend/docs | Do not merge in README train; needs separate owner triage. |
| #6 | `agent/KOL-FE-V3-SHELL-CONTRACT-20260625-001/primary/canvas-shell` | stale large train candidate | 276 files across frontend/baseline/docs | Do not merge in README train; needs separate owner triage. |
| #7 | `codex/remote-canary-20260625T100429Z` | small ops canary | 4 files in agent/ops docs | Separate canary review only. |
| #8 | `codex/kolibri-vertical-slice` | small ops canary | 3 files in agent/ops docs | Separate canary review only. |
| #9 | `codex/ci-minimal-20260625T102650Z` | blocked/no merge ref | `.github` only | Owner/authenticated check required. |
| #10 | PR ref only | blocked/no merge ref | `ops`, `tests` | Owner/authenticated check required. |
| #11 | PR ref only | blocked/no merge ref | `ops`, `tests` | Owner/authenticated check required. |
| #12 | PR ref only | blocked/no merge ref | `ops` | Owner/authenticated check required. |
| #13 | PR ref only | blocked/no merge ref | `tests` | Owner/authenticated check required. |
| #14 | `codex/telegram-gateway-canary` | blocked/no merge ref | `ops`, `tests` | Owner/authenticated check required. |
| #15 | `codex/telegram-gateway-ascii-taskids` | blocked/no merge ref | `ops`, `tests` | Owner/authenticated check required. |
| #16 | `codex/telegram-natural-language-router` | blocked/no merge ref | `ops`, `tests` | Owner/authenticated check required. |
| #17 | `codex/telegram-real-agent-chat` | blocked/no merge ref | `ops`, `tests` | Owner/authenticated check required. |
| #18 | `codex/remove-xiaomi-readme-label` | blocked/no merge ref | `README.md` | Superseded by this README branch; close or rebase if still needed. |
| #19 | PR ref only | blocked/no merge ref | `ops`, `tests` | Owner/authenticated check required. |
| #20 | PR ref only | blocked/no merge ref | `ops`, `tests` | Owner/authenticated check required. |
| #21 | PR ref only | blocked/no merge ref | `ops`, `tests` | Owner/authenticated check required. |
| #22 | PR ref only | blocked/no merge ref | `ops`, `tests` | Owner/authenticated check required. |
| #23 | PR ref only | blocked/no merge ref | `ops`, `tests` | Owner/authenticated check required. |
| #24 | `codex/kol-boost-011-brain-compiler` | feature candidate | 29 files across backend/deploy/ops/docs | Separate product review; not part of README train. |
| #25 | `factory/KOL-TEMP-SUBAGENTS-UNLOCK-001` | blocked/no merge ref | factory policy/ops | Owner/authenticated check required. |
| #26 | `codex/KOL-CLIENT-SDK-CONTRACTS-001` | focused frontend candidate | 1 frontend file | Can be reviewed independently after CI. |
| #27 | `codex/KOL-MOBILE-COMPOSER-SAFE-AREA-001` | focused frontend candidate | 2 frontend files | Can be reviewed independently after CI. |
| #28 | `factory/kol-mobile-composer-safe-area-fix-20260626-0232` | mixed duplicate frontend/factory candidate | 5 files | Compare with #27; owner should choose one path. |
| #29 | `factory/kol-agent-host-generic-runner-20260626` | focused ops candidate | 1 ops file | Can be reviewed independently after CI. |
| #30 | `factory/primary-remote-git-canary-20260626t041635z` | focused ops canary | 1 ops file | Merge only if owner still wants canary artifact. |
| #31 | `factory/kol-live-factory-status-ui-20260626-050716` | no-diff/no merge ref | no diff vs main | Close or confirm already landed. |
| #32 | `factory/kol-factory-status-fast-health-20260626t061059z` | blocked/no merge ref | backend | Owner/authenticated check required. |
| #33 | `factory/kol-pdf-estimator-engines-20260626t065932z` | no-diff/no merge ref | no diff vs main | Close or confirm already landed. |
| #34 | `factory/kol-mobile-shell-p0-r6-20260626t073609z` | no-diff/no merge ref | no diff vs main | Close or confirm already landed. |
| #35 | PR ref only | blocked/no merge ref | `ops`, `tests` | Owner/authenticated check required. |
| #36 | `factory/kol-kimi-fin-remote-integration-fallback-20260626t155937z` | large integration candidate | 127 integration files | Separate integration review; not part of README train. |
| #37 | `codex/factory-ha-spool-20260627` | mixed backend/ops/docs candidate | 14 files | Separate release review; do not combine here. |
| #38 | `agent/KOL-GENERIC-RUNNER-SMOKE-20260627T082501Z/impl/factory-smoke` | focused test candidate | 1 test file | Can be reviewed independently after CI. |
| #39 | PR ref only | no-diff/no merge ref | no diff vs main | Close or confirm already landed. |
| #40 | PR ref only | blocked/no merge ref | `ops`, `tests` | Owner/authenticated check required. |
| #41 | PR ref only | no-diff/no merge ref | no diff vs main | Close or confirm already landed. |
| #42 | PR ref only | no-diff/no merge ref | no diff vs main | Close or confirm already landed. |
| #43 | PR ref only | no-diff/no merge ref | no diff vs main | Close or confirm already landed. |
| #44 | PR ref only | no-diff/no merge ref | no diff vs main | Close or confirm already landed. |
| #45 | PR ref only | no-diff/no merge ref | no diff vs main | Close or confirm already landed. |
| #46 | `codex/factory-autonomy-pwa-billing` | very large mixed train candidate | 262 files across backend/frontend/docs/ops | Do not merge in README train; needs separate owner triage. |
| #60 | `agent/KOL-HOME-GENERIC-RUNTIME-SMOKE-RERUN4-20260629/result-capture` | very large mixed train candidate | 203 files across app/docs/scripts | Do not merge in README train; needs separate owner triage. |
| #61 | `p0/telegram-miniapp-kolibriai-deploy` | product candidate | 25 backend/frontend/ops/test files | Separate product review after CI. |
| #65 | `codex/gomesh-docs-rollout-safety` | very large mixed train candidate | 266 files across baseline/docs | Do not merge in README train; needs separate owner triage. |
| #74 | `codex/formulalm-rd-integration-20260629` | very large mixed train candidate | 268 files across backend/frontend/docs/ops | Do not merge in README train; needs separate owner triage. |
| #81 | `codex/telegram-live-director-primary` | focused ops/test candidate | 5 ops/test files | Separate Telegram review after CI. |
| #83 | `p0/agent-host-runner-contract-hardening-2026-06-30` | current P0 candidate | 60 docs/ops/test files | Owner decide after CI; do not merge with README train. |
| #84 | `codex/kolibri-superfactory-master-canvas-2026-07-01` | current docs candidate | 6 docs files | Owner decide before dependent product work. |
| #85 | `p0/api-first-full-control-fabric-2026-07-01` | current P0 product candidate, release gated | 38 README/backend/docs/infra/ops/test files | Blocked by release gate below; do not ignore. |
| #86 | `p0/github-operating-system-2026-06-30` | current governance docs candidate | 38 `.github`/docs/security files | Owner decide as GitHub operating-system base. |
| #87 | `p0/kwork-revenue-manager-2026-07-01` | current business docs candidate | 38 `.agents`/docs files | Separate owner decision. |
| #88 | `codex/factory-dispatcher-ledger-2026-07-01` | current large docs ledger | 190 docs files | Separate docs review; likely squash or archive decision. |
| #89 | `p0/telegram-superfactory-bot-miniapp-2026-07-01` | current product/docs candidate | 48 artifacts/docs/frontend/ops/test files | Separate Telegram/MiniApp release review. |
| #90 | `p0/telegram-miniapp-owner-auth-contract-2026-07-01` | current auth/docs candidate | 24 run artifact files | Separate owner-auth release review. |
| #91 | `p0/mimo-runner-output-auth-contract-repair-2026-07-01` | current focused ops/test/docs candidate | 7 files | Useful reliability candidate; not hard blocker for #85. |
| #92 | `p0/fleet-role-capability-inventory-2026-07-01` | current docs candidate | 9 docs files | Separate inventory review. |
| #93 | `p0/fabric-api-pr85-gap-review-2026-07-01` | current #85 gate review artifact | 11 docs files | Review before #85 owner decision. |
| #94 | `agent/P0_PR85_RELEASE_GATE_AFTER_PROMPT3_SURFACE_REPAIR_2026_07_01/generic` | current #85 gate artifact | 11 docs files | Review before #85 owner decision. |

## PR #85 Release Gate

PR #85 must stay in the release train and must not be skipped.

Evidence from fetched PR artifacts:

- PR #93 decision: `repair_in_pr85`.
- Initial #85 blocker: Prompt #3 required canonical `/v1/fleet/*`,
  `/v1/models`, `/v1/responses`, `/v1/chat/completions`, `/v1/agents/*`, and
  `/v1/admin/*` contracts, while #85 originally implemented a narrower
  `/v1/fabric/*` surface.
- PR #94 post-repair decision: `merge_ready_after_minor_docs_fix`.
- Remaining #85 blocker: `git diff --check origin/main...HEAD` failed on extra
  blank lines at EOF in new `docs/superfactory/*.md` files.
- Reported #85 test evidence in PR #94: focused tests `11 passed`, full
  server-side suite `71 passed, 1 warning`, `py_compile` passed, GitHub Actions
  `Kolibri CI / ci` was reported successful for head
  `06adeb54c0e7d7132c7f0817ea4755786cd3f092`.

Owner decision required:

1. Fix the #85 docs whitespace blocker in a focused PR/commit.
2. Rerun CI for #85 after the whitespace fix.
3. Owner decides whether to mark #85 ready and merge.

## Suggested Train Order

1. Merge or close this README/release-train documentation PR after owner review.
2. Resolve #85 whitespace blocker and rerun CI.
3. Owner review #93 and #94 gate artifacts, then decide #85.
4. Separately triage governance/docs PRs #84, #86, #92, #93, #94.
5. Separately triage current product PRs #83, #89, #90, #91.
6. Close no-diff/no-merge-ref stale PRs after authenticated GitHub UI
   confirmation.
7. Split or archive very large mixed PRs before any merge consideration.
