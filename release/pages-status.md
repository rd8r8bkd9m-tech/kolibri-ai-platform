# GitHub Pages Status

Status: prepared for controlled publication; DNS not changed in this pass.

## Current Site

- Static site path: `frontend`.
- Package: `frontend/package.json`.
- Build command: `npm run build`.
- Output directory: `frontend/dist`.
- CNAME source: `frontend/CNAME`.
- CNAME value: `kolibriai.ru`.
- Workflow: `.github/workflows/pages.yml`.

## Notes

- `frontend/vite.config.js` currently uses `/kolibri-ai-platform/` when `GITHUB_ACTIONS` is set. This supports project Pages paths, but custom domain publication may require confirming the desired base path before final Pages rollout.
- DNS/REG.RU changes require `USER_APPROVAL_REQUIRED`.
- Backend/API publication is separate from GitHub Pages.

## Next Safe Step

Run `cd frontend && npm run build`, then inspect `frontend/dist/CNAME` and build output.
