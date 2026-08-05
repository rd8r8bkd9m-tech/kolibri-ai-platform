# Repository operating boundary

## Canonical product

The only active product source of truth is `kolibri-v3/`.

All product development must stay inside that directory:

- web/PWA desktop and browser UI: `kolibri-v3/app`, `kolibri-v3/components`;
- native mobile client: `kolibri-v3/apps/kolibri-mobile`;
- product backend and migrations: `kolibri-v3/backend`;
- Rust kernels: `kolibri-v3/packages`;
- deployment and operations: `kolibri-v3/deploy`;
- product documentation and release evidence: `kolibri-v3/docs`,
  `kolibri-v3/release`.

Read `kolibri-v3/AGENTS.md` before changing or running V3.

## Legacy boundary

Parent-level `backend/`, `frontend/`, `kolibri-backend/`, `kolibri-v2/`,
`apps/`, `ops/`, `sites/`, and `kolibri-v3-new/` are historical or separate
contours. They are not V3 upstreams, fallbacks, deployment inputs, or places
for new V3 work.

Do not copy code from them into V3 or run them for a V3 task unless the owner
explicitly requests a reviewed migration. Do not delete legacy data merely
because it is outside the canonical subtree.

## Canonical commands

Run from `kolibri-v3/`:

```bash
npm run dev
npm run verify
```

The root `scripts/project-verify.sh` is only a compatibility wrapper that
delegates to `kolibri-v3/scripts/verify.sh`.
