# Scoped Context And Access Delegation

Snapshot: 2026-07-02

## Rule

The Mac remains under owner and director control. Remote servers and agents do
not receive broad personal-computer access, broad filesystem access or open
secret access. They receive only the minimum context needed for a specific
task, request or repair.

The director may issue missing information to a remote agent, but only as a
scoped grant.

## Scoped Grant

A scoped grant is a bounded information packet:

- `grant_id`;
- `task_id`;
- receiving node or pool;
- purpose;
- allowed use;
- forbidden use;
- expiry or one-shot lifetime;
- data classification;
- exact files, snippets, URLs or artifact references included;
- redaction status;
- owner approval reference when required.

## Allowed Grants

- non-secret project docs and architecture context;
- task-specific server inventory excerpts;
- sanitized logs;
- artifact references;
- scoped API route instructions;
- read-only diagnostic output;
- temporary credentials only when explicitly approved and technically required.

## Forbidden Grants

- full Mac filesystem access;
- full owner browser/profile/session access;
- raw private keys, passwords, cookies, OAuth tokens or Telegram tokens;
- unrestricted provider control panels;
- broad "use everything" memory dumps;
- indefinite access without an expiry or revocation path.

## Missing Context Request Flow

1. Remote agent reports a `context_missing` blocker with exact missing item.
2. Director decides whether the item is safe, needs redaction, or needs owner
   approval.
3. Director issues a scoped grant or rejects the request with a safe
   alternative.
4. Agent records the grant id in its artifacts.
5. Grant is retired after task completion or expiry.

## Director Authority

The director can issue non-secret scoped context without asking the owner.

The director asks the owner before issuing:

- paid provider access;
- secrets or credentials;
- personal account/session access;
- destructive administrative rights;
- production write access without rollback;
- Telegram receiver ownership changes.

## Audit

Every grant must be visible in owner-facing status:

- which task received it;
- what category of data was sent;
- whether secrets were included;
- expiry;
- revocation status;
- next safe action.

