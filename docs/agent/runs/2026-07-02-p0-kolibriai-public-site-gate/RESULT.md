# kolibriai.ru/public README Freshness Gate

Task id: `P0_AUTOPILOT_EXTRA_42_KOLIBRIAI_PUBLIC_SITE_GATE_2026_07_02`

Agent: `autonomous_engineer`

Node:

- Host: `kolibri`
- User: `root`
- Kernel: `Linux kolibri 6.8.0-36-generic #36-Ubuntu SMP PREEMPT_DYNAMIC Mon Jun 10 10:49:14 UTC 2024 x86_64`
- Execution path: `/var/lib/kolibri-agent/logical-workers/mesh-agent-42/worktrees/P0_AUTOPILOT_EXTRA_42_KOLIBRIAI_PUBLIC_SITE_GATE_2026_07_02/P0_AUTOPILOT_EXTRA_42_KOLIBRIAI_PUBLIC_SITE_GATE_2026_07_02-attempt-1/repo`
- Classification: server-side mesh worker; not a Mac local product-code run.

## Status

`blocked_external_release_task_required`

Repo/GitHub freshness is OK from the available server-side evidence. The live
`kolibriai.ru/public` surface is not serving the repo README or current frontend
artifact.

## Evidence

Commands run from the assigned server-side worker:

- `hostname -f; whoami; date -u +%Y-%m-%dT%H:%M:%SZ; uname -a`
- `git status --short --branch`
- `git ls-remote origin refs/heads/main`
- `git rev-parse HEAD`
- `git rev-parse origin/main`
- `git log -1 --format='%H%n%cI%n%s' origin/main -- README.md`
- `curl -fsSIL --max-time 20 https://kolibriai.ru/public`
- `curl -k -fsSIL --max-time 20 https://kolibriai.ru/public`
- `curl -k -sS -D - --max-time 15 https://kolibriai.ru/`
- `curl -k -sS -D - --max-time 15 https://kolibriai.ru/public`
- `getent ahosts kolibriai.ru`
- `openssl s_client -connect kolibriai.ru:443 -servername kolibriai.ru | openssl x509 -noout -subject -issuer -dates -ext subjectAltName`

Important outputs:

- `HEAD`: `f7ac32c70406432a52752ca45d87e35d9f1facd3`
- `origin/main`: `f7ac32c70406432a52752ca45d87e35d9f1facd3`
- `git ls-remote origin refs/heads/main`: `f7ac32c70406432a52752ca45d87e35d9f1facd3`
- Latest README-touching commit on `origin/main`: `1b08c43a86f8e1ee943edea592f77988b45f41d9`, `2026-07-01T23:41:03+03:00`, `p0: finalize API-first full-control Fabric (#85)`.
- `gh` is not installed on this worker, so GitHub CLI metadata was unavailable.
- `https://raw.githubusercontent.com/.../main/README.md` returned 404, consistent
  with private-repo unauthenticated raw access, not with stale Git refs.
- DNS: `kolibriai.ru` and `www.kolibriai.ru` resolve to `178.207.11.90`.
- HTTPS certificate subject: `CN = hcs0844dw9m.routingthecloud.net`.
- HTTPS certificate SAN: `DNS:hcs0844dw9m.routingthecloud.net`; no
  `kolibriai.ru` SAN.
- `https://kolibriai.ru/` serves `MikroTik File Sharing` HTML with
  `Last-Modified: Tue, 21 Oct 2025 07:32:52 GMT` and
  `Cache-Control: max-age=31536000`.
- `https://kolibriai.ru/public` returns HTTP `400` JSON:
  `{"error": "Invalid request."}`
- Plain HTTP `http://kolibriai.ru/public` returned an empty reply.

## Root Cause

The stale/wrong public content is not explained by a stale repo checkout or a
stale GitHub `main` ref. The public domain is routed to a MikroTik/back-to-home
file-sharing surface at `178.207.11.90`, with a certificate for
`hcs0844dw9m.routingthecloud.net` and long-lived HTML cache headers. That
surface does not know how to serve `/public` as Kolibri README/current-site
content, so it returns an invalid-request response.

## Blockers

- `github_cli_missing`: `gh` is unavailable on the worker.
- `github_raw_private_404`: unauthenticated raw GitHub access cannot read the
  private repository README.
- `public_tls_wrong_san`: live TLS certificate does not cover `kolibriai.ru`.
- `public_route_wrong_origin`: live `kolibriai.ru` route serves MikroTik file
  sharing instead of the Kolibri public site.
- `public_html_cache_too_long`: live HTML response advertises one-year caching.

## Artifacts

- `docs/agent/runs/2026-07-02-p0-kolibriai-public-site-gate/RESULT.md`
- `docs/agent/runs/2026-07-02-p0-kolibriai-public-site-gate/result.json`

## Next Exact Task

Create and run:

`P0_PUBLIC_SITE_DEPLOY_ROUTE_TLS_AND_README_FRESHNESS_CANARY_2026_07_02`

Exact scope:

1. On a server/control node, verify current `origin/main` SHA before deployment.
2. Decide the canonical `/public` contract: static rendered `README.md`, public
   landing page, or redirect to the repo/Docs surface.
3. Repoint `kolibriai.ru`/`www.kolibriai.ru` away from the MikroTik file-sharing
   virtual host or put a reverse proxy in front of it with an explicit
   `/public` route.
4. Issue/install a valid TLS certificate covering `kolibriai.ru` and
   `www.kolibriai.ru`.
5. Remove one-year cache headers from HTML and `/public`; use no-cache or short
   cache for freshness-gated documents.
6. Deploy the chosen `/public` artifact from `origin/main` and expose a visible
   freshness marker containing the source commit SHA.
7. Add a server-side canary that fetches `https://kolibriai.ru/public`, verifies
   HTTP 200, valid TLS hostname, absence of MikroTik file-sharing markers, and a
   README/source SHA matching the latest accepted main release.
8. Do not push to `main`; open a focused PR or record an owner-approved
   operational release artifact.

## Owner Summary RU

Проверка выполнена на серверном mesh worker `kolibri`, не на локальном Mac.
Код продукта не менялся. Git-источник свежий: `HEAD`, `origin/main` и удаленный
`main` указывают на `f7ac32c70406432a52752ca45d87e35d9f1facd3`; README уже
содержит актуальное описание после `#85`.

Проблема не в GitHub и не в README. Домен `kolibriai.ru` сейчас ведет на
`178.207.11.90` и отдает страницу MikroTik File Sharing с сертификатом
`hcs0844dw9m.routingthecloud.net`, а `/public` возвращает `400 Invalid request`.
Поэтому владелец видит старую/чужую публичную поверхность: живой роутинг и TLS
не подключены к текущему Kolibri public site из репозитория.

Следующая точная задача: `P0_PUBLIC_SITE_DEPLOY_ROUTE_TLS_AND_README_FRESHNESS_CANARY_2026_07_02`.
Нужно починить DNS/reverse-proxy/TLS для `kolibriai.ru`, определить контракт
`/public`, задеплоить артефакт из текущего `origin/main` и добавить canary,
который проверяет SHA README/релиза на живом сайте.
