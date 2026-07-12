# Kolibri AI OS program status

As of `2026-07-12T23:38:39Z` (UTC). Source commit: [`7fc3ff6a`](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/commit/7fc3ff6a24266caa204db02e8c4f05f4a4a2bbde).

This is the owner-facing source-backed ledger for the Home-first program. It reports only proven facts and explicit blockers. It does not derive readiness from heartbeat, does not turn missing evidence into zero, and does not report a completion percentage.

The machine-readable source for `/wallboard` is [`release/program-status.json`](../release/program-status.json).

## Proven facts

| Fact | Current evidence | Evidence ID |
| --- | --- | --- |
| Source | Commit `7fc3ff6a24266caa204db02e8c4f05f4a4a2bbde` | `commit:7fc3ff6a` |
| CI | Run `29213603299` is green: `ci`, `rust-1.97`, and `kolibri-shell` all succeeded | `ci-run:29213603299-green` |
| Home integration | Worktree fast-forwarded cleanly to exact commit `7fc3ff6a24266caa204db02e8c4f05f4a4a2bbde` | `home-integration:7fc3ff6a-clean` |
| Home toolchain | Codex CLI upgraded to `0.144.1`; root helper and sudoers are installed and validated; Home user can read the canonical manifest; `Linger=yes` | `home-codex-cli:0.144.1`, `home-account:helper-sudoers-manifest-linger` |
| Home Control Plane runtime | Active with `NRestarts=0` | `home-cp-runtime:active-nrestarts0` |
| Home Codex provider | Broker and safe credential provisioner are committed and CI-green; service is not activated, no provider canary exists, and dry-run is blocked by `current_user_codex_session_unavailable` | `home-provider:dry-run-session-unavailable` |
| Device login | The Mac screen is locked; official device login is waiting for owner unlock, not recorded as a generic authentication failure | `home-provider:dry-run-session-unavailable` |
| Credential migration | Initial apply failed with root state unchanged because the existing global binding was `mac-codex-provider-v1` epoch 1. The tested next-epoch migration succeeded: root binding is now node `home-codex-provider`, credential `home-codex-provider-v2`, epoch 2 | `home-provider:migration-epoch2` |
| Credential records | Owner and root records are mode `0600`; `secrets_returned=false`; both `mac-codex-provider` and `home-codex-provider` actors are drained | `home-provider:migration-epoch2` |
| Home Control Plane | Healthy when observed at `2026-07-12T21:54:12Z` | `home-cp-health:20260712T215412Z` |
| Runtime bundle | `sha256:de00339d64be94772896e956a8bc3e05d125b6db0677285dc6835f2884baa56c` | `runtime-bundle:de00339d` |
| Fleet proof | Campaign `factory-ca5e3a09-final-20260713` completed with 21 of 21 verified and zero failed | `fleet-campaign:factory-ca5e3a09-final-20260713` |
| Development seed baseline | 15 of 20 were previously verified | `development-seed-retry:KOL-IMPROVE-SEED-r2-3b01332c` |
| Development seed retry | Snapshot `sha256:df090eab9ecc4956d60f1a01fbf70d79ac702f4e8100997e5054f525591d951b`; prefix `KOL-IMPROVE-SEED-r2-3b01332c`; 5 of 5 terminal failed and zero completed, result hashes, or truth verdicts | `development-seed-retry:KOL-IMPROVE-SEED-r2-3b01332c` |
| Runner binding | Fix proven: all five bindings verified and all five leases cleared | `development-seed-retry:KOL-IMPROVE-SEED-r2-3b01332c` |

The 21 of 21 fleet proof is the first positive, independently bound fleet result. It proves that campaign only. It does not prove that the development seed, Portal, Shell, Improvement Controller, Rust authority, or production release is ready.

## Gate ledger

Only `completed`, `in_progress`, `not_started`, and `blocked` are valid gate states.

| Gate | Scope | Status | Evidence | Exact next action |
| --- | --- | --- | --- | --- |
| 0 | Evidence baseline and factual truth | `completed` | `commit:7fc3ff6a`, `ci-run:29213603299-green`, `runtime-bundle:de00339d` | Record the next accepted commit, CI verdict, runtime digest, and evidence timestamps before making any new readiness claim. |
| 1 | Home development authority | `in_progress` | `home-cp-runtime:active-nrestarts0`, `home-integration:7fc3ff6a-clean`, `home-codex-cli:0.144.1`, `home-account:helper-sudoers-manifest-linger`, `home-provider:migration-epoch2`, `home-provider:dry-run-session-unavailable`, `development-seed-retry:KOL-IMPROVE-SEED-r2-3b01332c` | Unlock Mac, complete official device login, install and start the service, pass readiness, run a fenced provider canary, then undrain; afterward repair and rerun the five Mimo development seed failures. |
| 2 | Contract and design freeze | `in_progress` | `commit:7fc3ff6a`, `ci-run:29213603299-green` | Freeze the Portal and Shell interaction contracts, responsive component inventory, and executable acceptance fixtures on one reviewed commit. |
| 3 | Durable foundation | `in_progress` | `home-cp-health:20260712T215412Z`, `runtime-bundle:de00339d` | Run the durable Rust foundation in shadow and pass restart, idempotency, event replay, and fencing parity fixtures without unexplained differences. |
| 4 | Factory fleet proof | `completed` | `fleet-campaign:factory-ca5e3a09-final-20260713`, `runtime-bundle:de00339d` | Repeat a fresh 21-node capability campaign for every release candidate and retain each result hash and independent verifier binding. |
| 5 | Portal, Shell, and providers | `blocked` | `home-provider:dry-run-session-unavailable`, `development-seed-retry:KOL-IMPROVE-SEED-r2-3b01332c` | Unlock Mac, complete device login, install and start the service, pass readiness, run a fenced canary, and undrain; then clear the Mimo failures and pass the provider and Shell end-to-end scenarios. |
| 6 | First useful vertical | `not_started` | — | After Gate 5, execute the source-backed estimate editor, immutable revision, PDF, and XLSX end-to-end release gate. |
| 7 | Full capability product | `not_started` | — | After Gate 6, prove Research, Documents, Code, Site or App preview, Browser, Media, Automations, and developer surfaces with real artifacts. |
| 8 | Rust authority and scale | `blocked` | `home-cp-health:20260712T215412Z` | Achieve shadow parity, keep it stable for the required observation window, then perform fenced authority canaries before scale benchmarks. |
| 9 | FormulaLM | `not_started` | — | Build the sanitized dataset manifest and independent evaluation path before admitting any model candidate to shadow inference. |
| 10 | Signed production release | `blocked` | `commit:7fc3ff6a`, `ci-run:29213603299-green`, `home-provider:dry-run-session-unavailable`, `fleet-campaign:factory-ca5e3a09-final-20260713` | Complete the preceding product and authority gates, then build a signed candidate and run canary, progressive rollout, full end-to-end verification, and the required soak. |

## Current blockers

- Four retry tasks reached attempt 2 of 2; each terminal attempt failed with Mimo rc=1. The latest records do not prove the exact taxonomy of their first attempts.
- The `qjns` retry is `runner_policy_blocked` for `illegal_access` at attempt 1 of 2.
- The Home Codex provider service is not activated and no provider canary has run. The dry-run blocker is `current_user_codex_session_unavailable`.
- The Mac screen is locked, so official device login is waiting for owner unlock.
- The only current Codex activation blocker is `current_user_codex_session_unavailable`; service activation and canary are subsequent uncompleted gates.
- Credential migration and drained actor provisioning are complete and are no longer blockers.
- Runner binding is no longer a blocker: bindings are verified and leases are cleared for all five retry tasks.
- Portal is not ready.
- Shell is not ready.
- Improvement Controller is not ready.
- Rust authority is not ready.
- No product release or FormulaLM readiness claim is supported by the evidence currently recorded here.

Historical evidence retains the earlier CI red result for commits `76e5d65e` and `3b01332c`, caused by the Python 3.14 timeout-classification race. It is no longer a current blocker because run `29213029860` is green.

## Update contract

Update the JSON first. Every gate update must include an evidence ID, an exact next action, and a UTC timestamp. A gate may become `completed` only when its named acceptance evidence exists. The Markdown view must be regenerated or edited in the same commit so owner and machine views cannot silently diverge.
