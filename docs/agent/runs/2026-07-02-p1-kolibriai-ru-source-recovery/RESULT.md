# KolibriAI.ru Source Recovery Result

Task: `P1_KOLIBRIAI_RU_SOURCE_RECOVERY_AND_WEB_REVIVAL_2026_07_02`

## Result

Recovered source-like Kolibri chat/PWA frontend material from primary-candidate server-local paths and copied it into the repository under:

`remote/kolibriai-frontend`

The import intentionally excludes generated dependency and build output directories:

- `node_modules/`
- `dist/`

## Provenance

Source path:

`/srv/kolibri/kimi-agent-kolibrifin/kolibri-v2`

Evidence that this is source-like material:

- `src/App.tsx`, `src/main.tsx`, route pages and shared components are present.
- `src/pages/ChatPage.tsx` implements the Kolibri chat UI.
- `public/manifest.json` and `public/sw.js` provide PWA material.
- `package.json`, `package-lock.json`, `vite.config.ts`, `tsconfig*.json`, Tailwind and ESLint config are present.
- Built output existed separately under the source path's `dist/` directory and was not imported.

## Guardrails Honored

- Did not edit root `frontend/**`.
- Did not decompile built/minified/static output.
- Did not use local Mac-only artifacts.
- Did not import `node_modules`.

## Follow-Up

The recovered frontend should be build-validated from `remote/kolibriai-frontend` and then mapped against backend `/api/v1` routes before public deployment.

## Validation

Run from `remote/kolibriai-frontend`:

- `npm ci`: passed.
- `npm run lint`: passed after recovered-frontend-only lint cleanup.
- `npm run build`: passed and produced a Vite production bundle locally.

Warnings observed:

- The worker has Node.js `18.19.1`; Vite `7.3.0` reports that Node `20.19+` or `22.12+` is required.
- `npm ci` reported audit findings in third-party dependencies. No dependency upgrades were applied in this recovery task.

Generated validation directories `node_modules/` and `dist/` were removed before staging.
