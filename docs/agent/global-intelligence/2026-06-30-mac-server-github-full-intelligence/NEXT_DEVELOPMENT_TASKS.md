# Next development tasks

## 1. P0 Agent Host generic runner contract hardening

Why: runner artifact and constraint drift is the biggest factory safety blocker.

Scope:

- `ops/agent_host.py`
- runner envelope validation
- artifact directory verification
- no-push/read-only/product-code guardrails
- tests for missing required artifacts and unsupported kinds.

Where: implement in clean branch from `origin/main`; validate on server after CI.

Acceptance:

- required artifacts checked before success.
- forbidden git push cannot happen.
- unsupported task kind returns structured blocker.
- P0 integration audit can rerun and produce expected files.

## 2. P0 Fix `uiap` and `qjns` disk reserve

Why: both report 0.0 GB free and block queue health.

Scope:

- inspect disk usage via server route/CP safe command.
- remove only approved caches/logs/artifacts.
- add disk reserve alert.

Acceptance:

- at least several GB free on both nodes.
- node cards report nonzero disk.
- qjns can clone/fetch after auth fix.

## 3. P0 Server GitHub auth without secret leakage

Why: server runtime repos cannot noninteractively fetch/clone.

Scope:

- configure deploy key/token helper securely.
- never print token/private key/cookies.
- test `git ls-remote` with redacted output.

Acceptance:

- main, primary-candidate, qjns can fetch/clone.
- no secret value appears in logs/artifacts.

## 4. Preserve dirty runtime diffs

Why: server dirty files may contain important hotfixes or drift.

Scope:

- read-only diff capture from `main` and `primary-candidate`.
- redact secrets.
- write artifacts under docs/agent/server-dirty-audit.

Acceptance:

- every dirty file is classified as keep/drop/unknown.
- no product code is modified during capture.

## 5. Split PR #46

Why: current PR is too large to merge safely.

Scope:

- PWA only.
- billing only.
- factory contracts/runner only.
- deterministic estimates only.
- FormulaLM harness only.

Acceptance:

- each PR has focused tests and rollback story.
- no cross-subsystem coupling hidden in one branch.

## 6. Rerun integration contract audit

Why: previous audit failed from artifact path drift.

Prerequisite: runner hardening merged/deployed.

Acceptance:

- expected docs under `docs/agent/integration/...` exist.
- backend/frontend/API contract blockers are classified.

## 7. Server reachability map

Why: direct Mac SSH cannot reach 18/20 nodes.

Scope:

- document correct host aliases/jump paths.
- compare direct SSH, CP card and mesh IP view.

Acceptance:

- every node has a known access route or explicit blocker.

## 8. FormulaLM boundary contract

Why: FormulaLM is spread across training scripts, provider hooks and large branch.

Acceptance:

- remote-only benchmark guard is enforceable.
- Mac cannot accidentally run heavyweight benchmark.
- branch split plan exists.

## 9. Billing contract

Why: billing is mixed into PR #46.

Acceptance:

- billing scaffold is isolated.
- secrets/payment credentials are not committed.
- API/frontend contract is documented.

## 10. Telegram deploy review

Why: Telegram PRs are closer to merge, but runtime impacts are real.

Acceptance:

- PR #61 and #81 are reviewed against current `origin/main`.
- deploy/rollback commands are known.

## 11. Queue dispatchability repair

Why: backlog and stale leases keep recurring.

Acceptance:

- stale active_task handling tested.
- unschedulable task reporting is clear.
- target node missing cases are actionable.

## 12. Worktree/branch hygiene

Why: 30 worktrees and 126 matrix rows create context risk.

Acceptance:

- prunable worktrees are cleaned after approval.
- useful artifacts preserved first.
- old branches labeled/archive candidates.

## 13. GitHub CI failure inspection

Why: one recent CI failure exists.

Acceptance:

- run `28443763496` cause summarized.
- branch owner/task linked.
- fix/ignore decision documented.

## 14. Control Plane filesystem endpoint decision

Why: `/v1/filesystem` returned 404 in prior scan.

Acceptance:

- endpoint intentionally absent or implemented.
- callers stop relying on missing endpoint.
