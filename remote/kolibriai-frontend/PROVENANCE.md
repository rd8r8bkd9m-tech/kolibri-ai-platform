# KolibriAI Frontend Provenance

Recovered on 2026-07-02 from primary-candidate server-local deployment material.

## Source Material

- Source path copied from: `/srv/kolibri/kimi-agent-kolibrifin/kolibri-v2`
- Copied into repository path: `remote/kolibriai-frontend`
- Excluded from copy: `node_modules/`, `dist/`
- Included source indicators:
  - `src/**/*.tsx`, `src/**/*.ts`, `src/**/*.css`
  - `vite.config.ts`
  - `tsconfig*.json`
  - `package.json` and `package-lock.json`
  - PWA files under `public/manifest.json` and `public/sw.js`
  - deployment files `Dockerfile` and `nginx.conf`

## Classification

This is source-like material, not a decompiled build:

- React and TypeScript source files are present.
- Vite, TypeScript, Tailwind and ESLint configuration files are present.
- Lockfile and package manifest are present.
- Built output existed separately at the source path under `dist/` and was intentionally not imported.

## Recovery Scope

The task explicitly forbids editing root `frontend/**`. This recovery only adds files under `remote/kolibriai-frontend/**`.

## Known Runtime Shape

- App framework: React + TypeScript + Vite.
- PWA files: `public/manifest.json`, `public/sw.js`.
- Main routes: home, chat, library, apps, estimates, documents, agents, servers, settings, login.
- API base: `/api/v1` in `src/lib/api.ts`.

## Next Materialization Steps

1. Validate `npm ci` and `npm run build` from `remote/kolibriai-frontend`.
2. Compare backend route availability against `src/lib/api.ts`.
3. Wire deployment to serve `remote/kolibriai-frontend/dist` only after build validation.
4. Keep root `frontend/**` unchanged unless a future task explicitly changes the source-of-truth decision.
