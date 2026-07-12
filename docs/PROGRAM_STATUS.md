# Kolibri AI OS program status

As of `2026-07-12T22:53:20Z` (UTC). Source commit: [`3b01332c`](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/commit/3b01332c67db970cf054bb3331b5c76c20ddee11).

This is the owner-facing source-backed ledger for the Home-first program. It reports only proven facts and explicit blockers. It does not derive readiness from heartbeat, does not turn missing evidence into zero, and does not report a completion percentage.

The machine-readable source for `/wallboard` is [`release/program-status.json`](../release/program-status.json).

## Proven facts

| Fact | Current evidence | Evidence ID |
| --- | --- | --- |
| Source | Commit `3b01332c67db970cf054bb3331b5c76c20ddee11` | `commit:3b01332c` |
| CI | Red at commits `76e5d65e` and `3b01332c` due to a Python 3.14 timeout-classification race; the planned fix is in progress | `ci:76e5-3b013-red` |
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
| 0 | Evidence baseline and factual truth | `completed` | `commit:3b01332c`, `ci:76e5-3b013-red`, `runtime-bundle:de00339d` | Record the next accepted commit, CI verdict, runtime digest, and evidence timestamps before making any new readiness claim. |
| 1 | Home development authority | `in_progress` | `home-cp-health:20260712T215412Z`, `development-seed-retry:KOL-IMPROVE-SEED-r2-3b01332c` | Repair the Mimo rc=1 runtime path and the qjns illegal-access policy decision, then rerun the same five tasks until each returns completion, result hash, and truth verification. |
| 2 | Contract and design freeze | `in_progress` | `commit:3b01332c`, `ci:76e5-3b013-red` | Finish the Python 3.14 timeout-classification race fix and return CI to green, then freeze the Portal and Shell contracts and executable acceptance fixtures on one reviewed commit. |
| 3 | Durable foundation | `in_progress` | `home-cp-health:20260712T215412Z`, `runtime-bundle:de00339d` | Run the durable Rust foundation in shadow and pass restart, idempotency, event replay, and fencing parity fixtures without unexplained differences. |
| 4 | Factory fleet proof | `completed` | `fleet-campaign:factory-ca5e3a09-final-20260713`, `runtime-bundle:de00339d` | Repeat a fresh 21-node capability campaign for every release candidate and retain each result hash and independent verifier binding. |
| 5 | Portal, Shell, and providers | `blocked` | `development-seed-retry:KOL-IMPROVE-SEED-r2-3b01332c` | Clear the Mimo runtime and qjns policy failures, prove the five retries with hashes and truth verdicts, then pass production-like hello, streamed web answer, history, fallback, and mobile composer scenarios. |
| 6 | First useful vertical | `not_started` | — | After Gate 5, execute the source-backed estimate editor, immutable revision, PDF, and XLSX end-to-end release gate. |
| 7 | Full capability product | `not_started` | — | After Gate 6, prove Research, Documents, Code, Site or App preview, Browser, Media, Automations, and developer surfaces with real artifacts. |
| 8 | Rust authority and scale | `blocked` | `home-cp-health:20260712T215412Z` | Achieve shadow parity, keep it stable for the required observation window, then perform fenced authority canaries before scale benchmarks. |
| 9 | FormulaLM | `not_started` | — | Build the sanitized dataset manifest and independent evaluation path before admitting any model candidate to shadow inference. |
| 10 | Signed production release | `blocked` | `commit:3b01332c`, `ci:76e5-3b013-red`, `fleet-campaign:factory-ca5e3a09-final-20260713` | Complete the preceding product and authority gates, then build a signed candidate and run canary, progressive rollout, full end-to-end verification, and the required soak. |

## Current blockers

- Four retry tasks reached attempt 2 of 2; each terminal attempt failed with Mimo rc=1. The latest records do not prove the exact taxonomy of their first attempts.
- The `qjns` retry is `runner_policy_blocked` for `illegal_access` at attempt 1 of 2.
- CI is red at commits `76e5d65e` and `3b01332c` because of a Python 3.14 timeout-classification race; the fix is in progress.
- Runner binding is no longer a blocker: bindings are verified and leases are cleared for all five retry tasks.
- Portal is not ready.
- Shell is not ready.
- Improvement Controller is not ready.
- Rust authority is not ready.
- No product release or FormulaLM readiness claim is supported by the evidence currently recorded here.

## Update contract

Update the JSON first. Every gate update must include an evidence ID, an exact next action, and a UTC timestamp. A gate may become `completed` only when its named acceptance evidence exists. The Markdown view must be regenerated or edited in the same commit so owner and machine views cannot silently diverge.
