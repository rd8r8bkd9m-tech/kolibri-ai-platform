# Kolibri AI OS program status

As of `2026-07-13T06:40:10Z` (UTC). Source commit: [`12fc77f6`](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/commit/12fc77f67b54c0d177e877127ef26cf2eb5ce150).

This is the owner-facing source-backed ledger for the Home-first program. It reports only proven facts and explicit blockers. It does not derive readiness from heartbeat and does not turn missing evidence into zero.

The machine-readable source for `/wallboard` is [`release/program-status.json`](../release/program-status.json).

## Acceptance progress

- Completed: `2/11` gates (`18.2%` by equal gate count).
- In progress: `5/11`.
- Blocked: `2/11`.
- Not started: `2/11`.

The `18.2%` value is a transparent acceptance-gate ratio, not an effort estimate: the gates have unequal scope. The independently verified fleet campaign is `21/21`, while the product release is not ready.

## Proven facts

| Fact | Current evidence | Evidence ID |
| --- | --- | --- |
| Source | Commit `12fc77f67b54c0d177e877127ef26cf2eb5ce150` | `commit:12fc77f6` |
| CI | Run `29229464005` is green: `ci`, `rust-1.97`, and `kolibri-shell` all succeeded | `ci-run:29229464005-green` |
| Home integration | Worktree fast-forwarded cleanly to exact commit `12fc77f67b54c0d177e877127ef26cf2eb5ce150` | `home-integration:12fc77f6-clean` |
| Program Wallboard | Tracked `/wallboard` route and owner-only `/v1/program/status` API are committed and CI-green. They expose `live`, `partial`, `stale`, or `unavailable`, bypass public Shell bootstrap, and have no mock fallback. Home kiosk activation, protected owner browser session, and rendered kiosk evidence are not yet proven. | `wallboard-contract:c74a772d` |
| Home toolchain | Codex CLI upgraded to `0.144.1`; root helper and sudoers are installed and validated; Home user can read the canonical manifest; `Linger=yes` | `home-codex-cli:0.144.1`, `home-account:helper-sudoers-manifest-linger` |
| Home Control Plane runtime | Strict compatibility rollout of source `77aa7086` applied from digest-bound plan `sha256:bc393fdaae1344c8cc16f9741ab11e21d926fa96b64d0890faeff2f1c3fe225e`; service is active with `NRestarts=0` | `home-cp-strict-compat:77aa7086` |
| Home Codex provider | Broker is active, dry-run and readiness passed, and the Home actor is schedulable. Canary `KOL-PROVIDER-HOME-CODEX-CANARY-20260713T060518078Z` completed through the Control Plane with output `KOLIBRI_CODEX_HOME_PROVIDER_OK`. | `home-provider-canary:KOL-PROVIDER-HOME-CODEX-CANARY-20260713T060518078Z` |
| Home portal canary | Clean Home worktree built image `kolibri-portal:ec6f14e`; the side-by-side canary on Home passed browser chat, opened a preliminary estimate editor, and returned a 20,234-byte PDF with zero console errors. Production was not switched and the prices are not source-verified. | `home-portal-canary:ec6f14e` |
| Portal factory truth | Side-by-side portal commit `aff0816` reads Home Control Plane directly with no seeded fallback. Browser and API checks show 21 canonical/fresh/online/schedulable nodes, 21 idle agents, 0 active tasks, 0 queued tasks and 424 historical tasks; mutation controls are absent/read-only and browser console errors are zero. Production was not switched. | `home-portal-factory-adapter:aff0816` |
| Portal provider fallback | Commit `15ac722` removes implicit uncredentialed CFBT routing, prioritizes configured official routes, circuits failed providers and redacts upstream errors. Eleven focused tests passed. A Home side-by-side mock canary received 502 from the first route, completed through the next route with HTTP 200 and `KOLIBRI_PROVIDER_FALLBACK_OK`, then skipped the failed route on the second 30 ms request. Production was not switched. | `home-portal-provider-fallback:15ac722` |
| Provider proof | Attempt `KOL-PROVIDER-HOME-CODEX-CANARY-20260713T060518078Z-attempt-1`, fence `1`, result `sha256:ac1ba5efd4699498d9afa70ba908110cfb79e118b1600341d02f56053d0a60a7`, binding `sha256:79a390d5eac529db2150452493b34223c79c405f4fddc2dee6b4acb985d29516`; independent verifier `control-plane/home` passed with high-confidence truth verdict. | `home-provider-canary:KOL-PROVIDER-HOME-CODEX-CANARY-20260713T060518078Z` |
| Device login | Home current-user Codex session is authenticated. Credentials were not copied to workers or from the Mac. | `home-provider-canary:KOL-PROVIDER-HOME-CODEX-CANARY-20260713T060518078Z` |
| Credential migration | Initial apply failed with root state unchanged because the existing global binding was `mac-codex-provider-v1` epoch 1. The tested next-epoch migration succeeded: root binding is now node `home-codex-provider`, credential `home-codex-provider-v2`, epoch 2 | `home-provider:migration-epoch2` |
| Credential records | Owner and root records are mode `0600`; `secrets_returned=false`; `mac-codex-provider` remains drained and `home-codex-provider` is schedulable | `home-provider:migration-epoch2` |
| Home Control Plane | Healthy after strict rollout; Redis projection at observation was 422 tasks, queue 0, lease index 0 | `home-cp-strict-compat:77aa7086` |
| Runtime bundle | `sha256:de00339d64be94772896e956a8bc3e05d125b6db0677285dc6835f2884baa56c` | `runtime-bundle:de00339d` |
| Fleet proof | Campaign `factory-ca5e3a09-final-20260713` completed with 21 of 21 verified and zero failed | `fleet-campaign:factory-ca5e3a09-final-20260713` |
| Development seed baseline | 15 of 20 were previously verified | `development-seed-retry:KOL-IMPROVE-SEED-r2-3b01332c` |
| Development seed retry | Snapshot `sha256:df090eab9ecc4956d60f1a01fbf70d79ac702f4e8100997e5054f525591d951b`; prefix `KOL-IMPROVE-SEED-r2-3b01332c`; 5 of 5 terminal failed and zero completed, result hashes, or truth verdicts | `development-seed-retry:KOL-IMPROVE-SEED-r2-3b01332c` |
| Runner binding | Fix proven: all five bindings verified and all five leases cleared | `development-seed-retry:KOL-IMPROVE-SEED-r2-3b01332c` |

The 21 of 21 fleet campaign and the first Home Codex task are separate positive proofs. The canary proves a real API-dispatched lease, fenced completion, artifact hash, and independent verdict on Home. Neither proof establishes continuous 24/7 development, Portal, Shell, Improvement Controller, Rust authority, or production release readiness.

## Gate ledger

Only `completed`, `in_progress`, `not_started`, and `blocked` are valid gate states.

| Gate | Scope | Status | Evidence | Exact next action |
| --- | --- | --- | --- | --- |
| 0 | Evidence baseline and factual truth | `completed` | `commit:77aa7086`, `ci-run:29227617842-green`, `runtime-bundle:de00339d` | Record the next accepted commit, CI verdict, runtime digest, and evidence timestamps before making any new readiness claim. |
| 1 | Home development authority | `in_progress` | `home-cp-runtime:active-nrestarts0`, `home-integration:77aa7086-clean`, `wallboard-contract:c74a772d`, `home-codex-cli:0.144.1`, `home-account:helper-sudoers-manifest-linger`, `home-provider:migration-epoch2`, `home-cp-strict-compat:77aa7086`, `home-provider-canary:KOL-PROVIDER-HOME-CODEX-CANARY-20260713T060518078Z`, `development-seed-retry:KOL-IMPROVE-SEED-r2-3b01332c` | Visually prove the protected Home Wallboard, execute the exact checkpoint-to-task-to-tests-to-commit-to-PR continuity scenario on Home, and repair then rerun the five Mimo development seed tasks. |
| 2 | Contract and design freeze | `in_progress` | `commit:77aa7086`, `ci-run:29227617842-green`, `wallboard-contract:c74a772d` | Freeze the Portal and Shell interaction contracts, responsive component inventory, and executable acceptance fixtures on one reviewed commit. |
| 3 | Durable foundation | `in_progress` | `home-cp-health:20260712T215412Z`, `runtime-bundle:de00339d` | Run the durable Rust foundation in shadow and pass restart, idempotency, event replay, and fencing parity fixtures without unexplained differences. |
| 4 | Factory fleet proof | `completed` | `fleet-campaign:factory-ca5e3a09-final-20260713`, `runtime-bundle:de00339d` | Repeat a fresh 21-node capability campaign for every release candidate and retain each result hash and independent verifier binding. |
| 5 | Portal, Shell, and providers | `in_progress` | `home-portal-canary:ec6f14e`, `home-provider-canary:KOL-PROVIDER-HOME-CODEX-CANARY-20260713T060518078Z` | Keep the proven Home portal as the canonical donor, then finish durable chat/history, source-backed estimates, and the signed switch. |
| 6 | First useful vertical | `in_progress` | `home-portal-canary:ec6f14e` | Add dated regional price sources, immutable revisions, and XLSX verification to the already working estimate editor and PDF path. |
| 7 | Full capability product | `not_started` | — | After Gate 6, prove Research, Documents, Code, Site or App preview, Browser, Media, Automations, and developer surfaces with real artifacts. |
| 8 | Rust authority and scale | `blocked` | `home-cp-health:20260712T215412Z` | Achieve shadow parity, keep it stable for the required observation window, then perform fenced authority canaries before scale benchmarks. |
| 9 | FormulaLM | `not_started` | — | Build the sanitized dataset manifest and independent evaluation path before admitting any model candidate to shadow inference. |
| 10 | Signed production release | `blocked` | `commit:77aa7086`, `ci-run:29227617842-green`, `wallboard-contract:c74a772d`, `home-provider-canary:KOL-PROVIDER-HOME-CODEX-CANARY-20260713T060518078Z`, `fleet-campaign:factory-ca5e3a09-final-20260713` | Complete the preceding product and authority gates, then build a signed candidate and run canary, progressive rollout, full end-to-end verification, and the required soak. |

## Current blockers

- Four retry tasks reached attempt 2 of 2 because Mimo returned `Session not found`; this is now classified as `mimo_session_not_found`, without retaining provider-private stderr in the API result and without a pointless retry.
- The `qjns` retry is `runner_policy_blocked` for `illegal_access` at attempt 1 of 2.
- Program Wallboard source and owner-only API contract are CI-green, but the protected owner browser session, Home kiosk activation, and rendered kiosk evidence are not proven.
- Home Codex activation is no longer a blocker: the service is active, its heartbeat contract is accepted, the actor is schedulable, and the fenced canary passed.
- Credential migration and actor provisioning are complete and are no longer blockers.
- The complete Home CLI continuity path from exact checkpoint through tests, commit, push, and PR is not yet proven.
- Runner binding is no longer a blocker: bindings are verified and leases are cleared for all five retry tasks.
- The Home portal side-by-side canary works for chat, preliminary estimate creation/editor, and PDF, but it is not production-switched and its estimate prices are not source-verified.
- Shell is not ready.
- Improvement Controller is not ready.
- Rust authority is not ready.
- No product release or FormulaLM readiness claim is supported by the evidence currently recorded here.

Historical evidence retains the earlier CI red result for commits `76e5d65e` and `3b01332c`, caused by the Python 3.14 timeout-classification race. It is no longer a current blocker because run `29213029860` is green.

## Update contract

Update the JSON first. Every gate update must include an evidence ID, an exact next action, and a UTC timestamp. A gate may become `completed` only when its named acceptance evidence exists. The Markdown view must be regenerated or edited in the same commit so owner and machine views cannot silently diverge.
