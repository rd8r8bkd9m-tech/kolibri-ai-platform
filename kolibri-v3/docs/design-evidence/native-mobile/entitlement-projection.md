# Construction estimate entitlement projection

Date: 2026-07-30

## Decision

Use the existing identity/session response instead of a second mobile-only
endpoint. The projection is recalculated from the database for the exact
authenticated `tenant_id` and `user_id`.

The client cannot submit capability or entitlement claims. Attempts to add
them to mobile login are rejected by the strict request schema.

## Persistence

`backend/migrations/038_product_entitlement_projection.sql` creates
`product_entitlement_grants` with:

- composite tenant/user/entitlement identity;
- one compiled entitlement:
  `construction.estimates.use`;
- deny-by-default absence semantics;
- active/revoked lifecycle;
- monotonically fenced `grant_epoch`;
- immutable subject scope;
- explicit server-side source.

Migration adoption grants only the already trusted singleton platform owner.
Fresh owner bootstrap performs the same grant from the trusted server command.
Regular users receive no product grant.

The platform-owner control plane can assign or revoke the exact compiled
entitlement for an existing customer. It derives tenant scope from the target
user, requires the current grant epoch, advances the epoch on every transition
and records the before/after projection in the existing platform audit log.

## Projection

`backend/app/product_entitlements.py` maps the persisted entitlement to the
bundled capability `construction.estimates.workspace`. Unknown database values
cannot broaden the response because the mapping is compiled in the server.

`UserView` returns:

- combined platform and product `capabilities`;
- server-owned `entitlements`.

The same view is used by browser session/profile and native login/refresh/
bearer-session responses.

## Authorization boundary

The client projection is not treated as the security boundary.
`require_product_entitlement` protects the server routes that read or mutate
the construction vertical:

- document catalog, estimate read/history/edit/export and copies;
- estimate calculations and price-source mutations;
- construction project context and counterparties;
- normative search/read and the personal price catalog.

Estimate chat requests are checked during atomic run acceptance. Delayed
estimate widget materialization re-checks the persisted active grant for the
original run actor, so revocation remains effective after an agent run has
already started.

## Client boundary

The Expo client validates bounded, unique claim arrays before accepting a
mobile token response. The `construction.estimates` navigation registration
requires the exact capability, entitlement and bundled renderer key. Any
missing or malformed input produces a disabled boundary.

## Verification

- backend focused identity/migration/product tests: passed;
- backend full suite: 222 passed;
- native typecheck and lint: passed;
- native focused contracts: 5 passed;
- Expo Doctor: 20/20 passed.
