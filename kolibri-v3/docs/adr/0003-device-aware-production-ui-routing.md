# ADR 0003: Device-aware production UI routing

- Status: accepted
- Date: 2026-08-02
- Owners: Kolibri V3 product owner

## Context

The public `/app` endpoint must serve the desktop Next.js interface to desktop
browsers and the Expo web interface to mobile devices. The previous portable
release started only Next.js, so a client-side mobile handoff could loop or
fail and the mobile bundle was not present in production.

## Decision

The portable release builds both interfaces and runs them behind the existing
same-origin UI gateway. Next.js listens on an internal desktop port, the
exported Expo web bundle is served on an internal mobile port, and the gateway
owns the public frontend port. Direct `/app` selection is based on device
signals before stale query or cookie affinity. Nginx continues to own TLS and
proxies `/v1/` directly to the canonical backend.

## Consequences

Mobile devices receive mobile HTML on the first request while desktop devices
remain on the desktop interface. The frontend service now supervises three
child processes, and a failure in any child restarts the complete UI stack.
The release build takes longer because it installs, tests, and exports the
mobile web client.

## Verification

Gateway integration tests assert separate mobile and desktop routing. The
portable smoke test builds both clients, starts the production UI stack, and
checks the mobile response with an iPhone user agent. Activation health checks
verify desktop health and mobile `/app` before accepting a release.

## Rollback

The portable installer retains the previous immutable release and service
configuration. Its existing rollback path restores the previous `current`
symlink and frontend unit without modifying the production database.
