# Deploy Plan

No deploy, DNS, REG.RU, server, firewall, or bootstrap action was performed in Phase 2.

## 1. GitHub Pages Deploy

- Repo: current KolibriAI Platform repository.
- Branch: publish after approved push/merge, normally `main`.
- Workflow: `.github/workflows/pages.yml`.
- Build command: `cd frontend && npm install && npm run build`.
- Output directory: `frontend/dist`.
- CNAME: `frontend/CNAME` contains `kolibriai.ru`.
- Expected URL after approval: `https://kolibriai.ru`.
- Rollback: revert Pages commit or disable Pages/custom domain in GitHub settings.

## 2. kolibriai.ru DNS

Approval required before changing records.

GitHub Pages apex A records:

```text
185.199.108.153
185.199.109.153
185.199.110.153
185.199.111.153
```

Recommended `www` record:

```text
www CNAME <github-pages-hostname>
```

REG.RU steps after approval:

1. Open DNS zone for `kolibriai.ru`.
2. Add/verify the four apex A records.
3. Add/verify `www` CNAME.
4. Do not change MX/SPF/DKIM unless separately approved.
5. Wait for propagation and verify HTTPS in GitHub Pages.

## 3. api.kolibriai.ru

- Target server: not confirmed in this branch.
- Target service: FastAPI backend plus Fabric/factory sidecar.
- Deploy method: protected; likely `scripts/deploy.sh` or systemd/ops path after review.
- Health endpoint: `/api/health` now; future canonical `/health` or `/v1/status` after compatibility work.
- TLS method: not confirmed; likely reverse proxy/ACME on target server.
- Rollback: restore previous service unit/artifact bundle and DNS/API routing.
- Approval required: yes.

## 4. Bootstrap

Existing protected paths:

- `scripts/deploy.sh`
- `ops/install-telegram-secret.sh`
- `docs/superfactory/NEW_SERVER_API_BOOTSTRAP.md`
- `.factory/runs/*bootstrap*`
- `bootstrap.js`

Safe actions:

- read static docs/code;
- lint/review;
- prepare dry-run plan.

Protected actions:

- live bootstrap;
- secret install/rotation;
- production deploy/restart;
- server reinstall/reboot;
- firewall/public exposure changes.
