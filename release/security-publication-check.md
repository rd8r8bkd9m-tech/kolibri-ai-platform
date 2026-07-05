# Security Publication Check

Date: 2026-07-05

## Checked

- `.gitignore`
- `README.md`
- `.github/`
- `.kolibri/`
- `docs/`
- `release/`
- `frontend/` excluding generated/dependency output
- `backend/` excluding dependency/cache output
- `ops/` policy by path, without reading `ops/telegram.env`

The scan skipped dependency/build/cache/runtime paths and did not read `.env` or `ops/telegram.env`.

## Result

- Public-file secret scan findings: none.
- Final scan count: `checked_public_files=543`, `findings=0`.
- `SECRET_RISK_FOUND_REDACTED`: no findings in scanned public files.
- `.gitignore` protects `.env`, `.env.*`, `ops/*.env`, `ops/telegram.env`, `*.secret`, `*.key`, `*.pem`, `secrets/`, and `credentials/`.

## Safe To Publish

- Source-of-truth docs.
- Public architecture/investor/security/roadmap docs.
- GitHub templates.
- Release reports and manifests generated in this pass.
- Frontend source and `frontend/CNAME`.

## Do Not Publish

- `.env` or `.env.*` except `.env.example`.
- `ops/telegram.env`.
- Private server inventory.
- Raw logs, cookies, tokens, SSH/private keys, `.pem`, `.key`, `.secret` files.
- `logs/`, `output/`, runtime DBs, generated caches.

## Recommendations Before Push/Public Release

1. Stage only the release-candidate files listed in `release/git-checkpoint.md`.
2. Run secret/path guard on staged files.
3. Keep DNS/REG.RU/deploy/bootstrap behind `USER_APPROVAL_REQUIRED`.
