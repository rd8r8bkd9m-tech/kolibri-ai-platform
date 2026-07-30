# Local Storage Admin control-plane evidence

Captured: 2026-07-30 16:18 MSK

Candidate state: dirty development tree on `codex/v3-home-deploy`.

This evidence covers local control-plane contracts and responsive UI only. It
does not authorize or claim a storage mutation, executor deployment or
production change.

## Implemented boundary

- Access is owner-only through `platform.storage.manage` and the current
  platform authority epoch.
- Mutating requests require CSRF and recent-auth checks.
- The API accepts fixed node/category identifiers rather than arbitrary paths
  or shell commands.
- Operation reconciliation is server-side and status-only; it never executes
  an operation.
- Retained quarantine can be restored only after a fresh preview and explicit
  typed confirmation `RESTORE`.
- The Rust executor boundary uses a strict versioned protocol and validates
  the response and policy digest.
- The Home AF_UNIX adapter is opt-in and disabled by default.
- Primary has no approved executor transport until the mTLS boundary exists.

## Fail-closed release position

Storage mutation must remain blocked and capacity-only until the executor can
prove exhaustive live guard evidence, including all relevant references and
revalidation at the mutation boundary. Enumerated or omitted evidence must not
be treated as complete.

Primary mTLS and a true step-up authentication flow remain P1 work. No backend
or node executor was installed or enabled on Home or Primary as part of this
evidence.

## Rust capacity-only security gate

The enumerated guard-evidence foundation is non-authorizing in every shipped,
debug and ordinary custom build. Inventory therefore exposes capacity and
topology only, with `executeEnabled=false`, empty `guardedScopes` and zero
actionable candidates. Preview and execute fail
`guard_evidence_unavailable`. The mutation seam exists only under
`cfg(test)` and is absent from the executor binary.

The earlier false-completeness, parser fail-open, debug-build authority,
mountinfo bind-root, post-staging live-reference, uppercase-ID and durable
status-scope findings were remediated. An independent second review found no
remaining P0/P1 for the shipped capacity-only binary.

Rust 1.85 gates run on the exact local source:

- formatting: passed;
- clippy for all targets/features with `-D warnings`: passed;
- debug tests: `27/27`;
- release tests: `27/27`;
- locked optimized release build: passed.

Linux-only mountinfo tests are present but could not execute on this macOS
host. Exhaustive live enumeration/generation attestation and
descriptor-relative no-follow evidence traversal remain documented future
work. Neither can authorize mutation in the current binary.

## Browser QA

The authenticated owner UI was exercised on desktop and at a 390×844 mobile
viewport:

- the owner-only “Управление платформой” section was visible;
- Home and Primary showed honest unavailable-executor states;
- Home reported the root logical volume and the 19.83 GiB unallocated VG
  reserve as separate capacity facts;
- no destructive controls were exposed while an executor was unavailable;
- the 390 px document width remained 390 px with no horizontal overflow;
- the browser console contained no warnings or errors.

## Verification context

The surrounding local candidate gates were green:

- Backend: `257 passed`.
- Web: `116/116`.
- Portable release contracts: `12/12`.
- TypeScript typecheck: passed.
- Production web build: passed.

The control plane is ready for continued guarded integration. It is not
evidence that storage deletion is release-ready.
