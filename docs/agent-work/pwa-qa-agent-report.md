# PWA QA agent report

Дата: 2026-06-29 14:35 MSK  
Роль: QA-ревизор PWA  
Публичный URL: `http://104.253.43.117`  
Область: SPA/PWA доступность, manifest, service worker/assets, mobile viewport smoke, right-bottom Control FAB. Код приложения не редактировался.

## Verdict

`NO-GO для PWA release`, `GO WITH EXCEPTIONS для базового SPA/browser smoke`.

Публичная SPA доступна: `/`, `/app`, assets, icons, manifest и `service-worker.js` отдаются с `200`, browser smoke не нашёл console/page errors и horizontal overflow на `1440x1000`, `390x844`, `360x740`.

PWA-функции не проходят на публичном origin: сайт открыт только как `http://104.253.43.117`, `https:443` отказывает соединение, Chromium видит `window.isSecureContext=false` и `serviceWorker in navigator=false` во всех browser runs. Offline reload `/app` после online load падает в `chrome-error://chromewebdata/` с `net::ERR_INTERNET_DISCONNECTED`.

## Commands / tooling

- `command -v npx` -> not found. Стандартный Playwright CLI wrapper недоступен.
- `python3 -m playwright --version` -> `Version 1.58.0`.
- `python3 -m playwright install chromium` -> установлен browser runtime в пользовательский cache, репозиторий не менялся.
- `curl -sS -L --max-time 15 ... http://104.253.43.117/{,/app,/manifest.webmanifest,/service-worker.js,/pwa-register.js,/assets/index-CrRciCNz.css,/assets/index-tdp0IbRm.js,/icons/...}`.
- Python Playwright smoke: desktop/mobile screenshots, DOM accessibility sanity, secure-context/SW facts, Control FAB click, offline reload.
- `file /tmp/kolibri-pwa-icon192.png /tmp/kolibri-pwa-icon512.png /tmp/kolibri-pwa-apple.png`.
- HTTPS socket probe to `104.253.43.117:443` -> `ConnectionRefusedError(61, 'Connection refused')`.

Artifacts:

- Browser JSON: `/tmp/kolibri-pwa-public-qa-20260629-143314/results.json`
- Screenshots dir: `/tmp/kolibri-pwa-public-qa-20260629-143314/`
- Key screenshots: `landing-desktop-1440.png`, `landing-mobile-390.png`, `app-mobile-390.png`, `app-mobile-390-control-open.png`, `app-mobile-360-control-open.png`, `offline-reload-mobile-390.png`.

## HTTP / assets evidence

| Probe | Result |
| --- | --- |
| `/` | `200`, `text/html`, `2321` bytes, SPA shell |
| `/app` | `200`, `text/html`, `2321` bytes, SPA fallback OK |
| unknown route `/does-not-exist-pwa-qa` | `200`, `text/html`, SPA fallback OK |
| `/manifest.webmanifest` | `200`, `application/octet-stream`, `681` bytes |
| `/service-worker.js` | `200`, `application/javascript`, `2167` bytes |
| `/pwa-register.js` | `200`, `application/javascript`, `358` bytes |
| `/assets/index-CrRciCNz.css` | `200`, `text/css`, `39857` bytes, cache `public, max-age=3600` |
| `/assets/index-tdp0IbRm.js` | `200`, `application/javascript`, `518836` bytes, cache `public, max-age=3600` |
| `/icons/icon-192.png` | `200`, PNG `192 x 192` |
| `/icons/icon-512.png` | `200`, PNG `512 x 512` |
| `/icons/apple-touch-icon.png` | `200`, PNG `180 x 180` |

Manifest JSON валиден:

- `name`: `Фабрика Колибри`
- `short_name`: `Колибри`
- `start_url`: `/`
- `scope`: `/`
- `display`: `standalone`
- `orientation`: `portrait`
- `theme_color`: `#f0f4f8`
- icons: `/icons/icon-192.png` and `/icons/icon-512.png`, both `purpose: any maskable`.

HTML meta/link smoke:

- `lang=ru`, `<title>Фабрика Колибри</title>`.
- `viewport`: `width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover`.
- `link rel=manifest` present.
- `apple-touch-icon` present.
- light/dark `theme-color` meta present.
- `apple-mobile-web-app-capable`, `mobile-web-app-capable`, `format-detection=telephone=no` present.

Service worker source is structurally present:

- `CACHE_NAME = "kolibri-ai-pwa-v1"`.
- `APP_SHELL` includes `/`, manifest, SVG, apple icon, 192/512 icons.
- `install`, `activate`, `fetch` handlers present.
- Navigation fallback caches `/`.
- `/api` and `/ws` are excluded from fake cached success.

## Browser smoke evidence

| Run | Status | secureContext | SW API | Standalone | Horizontal overflow | Console/page errors |
| --- | ---: | --- | --- | --- | --- | --- |
| `/` desktop `1440x1000` | `200` | `false` | `false` | `false` | `false` | none |
| `/app` desktop `1440x1000` | `200` | `false` | `false` | `false` | `false` | none |
| `/` mobile `390x844` | `200` | `false` | `false` | `false` | `false` | none |
| `/app` mobile `390x844` | `200` | `false` | `false` | `false` | `false` | none |
| `/` mobile `360x740` | `200` | `false` | `false` | `false` | `false` | none |
| `/app` mobile `360x740` | `200` | `false` | `false` | `false` | `false` | none |

Accessibility smoke:

- Landing: `lang=ru`, title present, `mainCount=1`, `navCount=1`.
- App: `lang=ru`, title present, no unnamed focusables, no visible images without `alt`, no visible input naming issues.
- App caveat: DOM audit found `mainCount=0`, `navCount=0` on `/app`; this is not blocking PWA installability, but should be improved for screen-reader navigation.

Offline smoke:

- After online load of `/app`, `context.set_offline(true)` and reload failed with `Page.reload: net::ERR_INTERNET_DISCONNECTED`.
- Final URL: `chrome-error://chromewebdata/`.
- Screenshot: `/tmp/kolibri-pwa-public-qa-20260629-143314/offline-reload-mobile-390.png`.

## Control FAB evidence

Right-bottom Control FAB is available and clickable on `/app`.

| Viewport | FAB rect | Open panel rect | Result |
| --- | --- | --- | --- |
| Desktop `1440x1000` | `x=1294 y=840 w=126 h=48` | `x=994 y=224 w=430 h=760`, `role=dialog` | PASS |
| Mobile `390x844` | `x=334 y=694 w=44 h=44` | `x=0 y=101 w=390 h=743`, `role=dialog` | PASS |
| Mobile `360x740` | `x=304 y=590 w=44 h=44` | `x=0 y=89 w=360 h=651`, `role=dialog` | PASS |

No horizontal overflow after opening the panel on desktop/mobile. Visual screenshots show the FAB above the composer/send area and the mobile panel as a bottom sheet.

## Blockers

1. `P0` Public origin is not a secure context. `http://104.253.43.117` has no working HTTPS listener on `443`; Chromium reports `window.isSecureContext=false` and `serviceWorker in navigator=false`. Result: service worker registration cannot run, installability is blocked, offline reload fails.
2. `P0` Offline evidence fails. Reloading `/app` offline after first online load returns Chromium network error, not app shell.
3. `P1` Manifest is served as `application/octet-stream`. JSON content is valid, but production should serve `manifest.webmanifest` as `application/manifest+json` or at least `application/json` for better browser/tool compatibility.

## Non-blocking findings

- SPA fallback works, including `/app` and an unknown route returning shell `200`.
- `pwa-register.js` exists and would call `navigator.serviceWorker.register("/service-worker.js", { scope: "/" })`, but the enclosing HTML guard never loads it when `serviceWorker` is absent on HTTP.
- Mobile/desktop smoke did not find runtime console errors, request failures, page errors, unnamed visible focusables, missing visible image alts, input naming issues, or horizontal overflow.
- `/app` should add semantic `main`/`nav` landmarks when convenient.

## Recommended release gate

Before PWA sign-off:

1. Put the public app behind HTTPS on a domain or HTTPS-enabled host and redirect HTTP to HTTPS.
2. Serve `manifest.webmanifest` with a manifest/json content type.
3. Re-run installability/offline browser pass and verify service worker activation plus cache `kolibri-ai-pwa-v1`.
4. Capture Android/iOS install/standalone evidence if this is a release candidate, not only Chromium desktop/mobile emulation.
