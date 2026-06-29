# Mobile And GoMesh Integration

Kolibri's first mobile target is an installable SPA/PWA for Android and iOS.
Native wrappers are optional distribution layers, not separate products.

## Mobile Strategy

- Keep the core app as one React SPA/PWA.
- Preserve installability with a valid manifest, icons, service worker, HTTPS,
  offline shell, and standalone display mode.
- Android path: installable PWA first; Trusted Web Activity or Capacitor later
  when Play Store distribution or deeper native APIs are required.
- iOS path: Home Screen web app first; Capacitor later when App Store
  distribution, native share extensions, or restricted device APIs are required.
- Product QA must cover Android Chrome and iOS Safari/Home Screen behavior
  before owner handoff.

## GoMesh Boundary

GoMesh is treated as an external active development track owned by another
agent/team. Do not rewrite or take ownership of their code without an explicit
handoff.

Kolibri may integrate with GoMesh through documented contracts:

- mesh node registration;
- message/task bridge;
- health and backpressure signals;
- signed service-to-service requests;
- feature flag `KOLIBRI_GOMESH_ENABLED`;
- fallback path through current Control Plane when GoMesh is unavailable.

## Server Technology Standard

Use proven server primitives for reliability:

- Go or Python services behind systemd;
- idempotent bootstrap;
- health endpoints;
- structured logs;
- graceful shutdown;
- bounded concurrency and backpressure;
- Redis-backed leases/queues where appropriate;
- artifact-first task results.

## QA Requirements

Before a mobile-ready release:

- `npm --prefix frontend run build`;
- PWA manifest and service worker syntax checks;
- desktop browser smoke;
- mobile viewport smoke;
- Android installability pass;
- iOS Home Screen pass;
- offline shell pass;
- chat/control FAB flow pass;
- billing and deterministic estimate smoke;
- independent factory QA pass.
