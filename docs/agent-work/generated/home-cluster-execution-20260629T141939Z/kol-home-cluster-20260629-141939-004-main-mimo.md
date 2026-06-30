# HTTPS/PWA Gate Artifact

Task id: `KOL-HOME-CLUSTER-20260629-141939-004-MAIN-MIMO-RERUN1-DELIVERABLE-RETRY`
Role slot: `mimo-slot-4`
Generated: `2026-06-30`

## Goal

Prepare the Kolibri frontend HTTPS/PWA readiness gate for manifest, service worker, and deployment asset availability. The gate result must be artifact-backed and include the exact implementation delta, touched paths, verification log, residual risks, and Telegram-ready summary.

## Implementation Delta

- Added a Vite-served PWA manifest at `/manifest.webmanifest` with standalone display metadata, theme/background colors, start URL, scope, and a maskable SVG icon.
- Added a static `/kolibri.svg` icon so the existing favicon reference and new manifest icon resolve from the production build.
- Added `/sw.js` with a conservative app-shell cache. It excludes non-GET requests, cross-origin requests, `/api/`, and `/ws/` so chat, upload, WebSocket, and backend interactions stay network-driven.
- Added `frontend/src/registerServiceWorker.js` and invoked it from the React entrypoint. Registration is limited to production builds and secure contexts, with localhost allowed by browser policy.
- Updated `frontend/index.html` with manifest, description, and mobile web app metadata.
- Updated `scripts/deploy.sh` so `frontend/public/` is copied to the main host before `npm run build`, making the manifest, service worker, and icon available during deployment.

## Affected Paths

- `frontend/index.html`
- `frontend/public/kolibri.svg`
- `frontend/public/manifest.webmanifest`
- `frontend/public/sw.js`
- `frontend/src/main.jsx`
- `frontend/src/registerServiceWorker.js`
- `scripts/deploy.sh`
- `docs/agent-work/generated/home-cluster-execution-20260629T141939Z/kol-home-cluster-20260629-141939-004-main-mimo.md`

## Verification Log

- `python -m json.tool frontend/public/manifest.webmanifest` failed because `python` is not installed in the container.
- `python3 -m json.tool frontend/public/manifest.webmanifest >/tmp/kolibri-manifest-check.json && echo manifest-json-ok` passed.
- `npm install --no-package-lock` passed: 238 packages installed, 239 packages audited, 0 vulnerabilities reported, no `package-lock.json` created.
- `npm run build` passed with Vite 8.1.1. Output included `dist/index.html`, `dist/assets/index-DKLo7Wi9.css`, and `dist/assets/index-BwDLTS6n.js`. Vite reported a non-fatal warning that one chunk is larger than 500 kB after minification.
- `test -f frontend/dist/manifest.webmanifest && test -f frontend/dist/sw.js && test -f frontend/dist/kolibri.svg && echo pwa-assets-emitted` passed.
- `test "$(find frontend/dist -maxdepth 1 -type f \( -name 'manifest.webmanifest' -o -name 'sw.js' -o -name 'kolibri.svg' \) | wc -l)" -eq 3 && echo dist-pwa-files-ok` passed.
- `grep -q 'serviceWorker' frontend/dist/assets/*.js && grep -q 'manifest.webmanifest' frontend/dist/index.html && echo dist-registration-links-ok` passed.
- `npm run test:mobile-layout` passed.
- `git diff --check` passed.

## Risks

- Production installability still depends on serving the app over HTTPS. The current checked-in Nginx sample listens on port 80 only, so TLS termination must be configured outside this artifact or added in a separate deployment change.
- The service worker caches the app shell and static same-origin GET assets only. Offline API/chat behavior is intentionally not provided.
- Browser PWA quality gates may still require raster PNG icon sizes for some stores or audits. The manifest uses SVG `sizes: "any"` and `purpose: "any maskable"`, which is acceptable for modern browser install prompts but not every distribution channel.
- Deploy script now copies `frontend/public/`; remote hosts must have permissions and enough disk space for that directory.

## Telegram Summary

HTTPS/PWA gate готов: добавлены manifest, SVG icon, production-only service worker registration, conservative `/sw.js`, deploy copy для `frontend/public/`, и artifact report. Остаточный риск: production HTTPS/TLS пока не подтвержден в репозитории, Nginx sample слушает только 80.

Telegram send tool was not available in this Codex fallback session, so the same summary was saved as fallback agent-message artifact:

- `docs/agent-work/generated/home-cluster-execution-20260629T141939Z/agent-message-kol-home-cluster-20260629-141939-004-main-mimo.md`
