# Kolibri V3 runtime invariants

These rules apply to every task under `kolibri-v3/`.

## Product structure and change placement

- `docs/PROJECT_MAP.md` is the canonical map of code ownership, dependency
  direction, and where new code belongs. Do not create a new top-level source
  directory without an accepted architecture decision record (ADR).
- Keep transport code thin. Next route handlers live in `app/api/`, FastAPI
  routers in `backend/app/`, and neither is the home of reusable business
  rules.
- Browser business contracts and clients live in `lib/<domain>/`; reusable
  product UI lives in `components/<surface>/`; generic visual primitives live
  in `components/ui/` and must not depend on product surfaces.
- Backend domain behavior lives in a domain module/package under
  `backend/app/`. Database migrations are append-only in
  `backend/migrations/`; do not hide schema changes in application startup.
- Cross-runtime contracts have one declared authority. Follow the ownership
  table in `docs/SOURCE_OF_TRUTH.md`; generated copies must not be edited by
  hand.
- A change that introduces a new subsystem, reverses a dependency, changes a
  persistence boundary, or adds a deployment lane requires an ADR under
  `docs/adr/`.
- `npm run verify:structure` is the executable structure contract and is part
  of every verification run. Update the documentation and checker together
  when an accepted ADR changes the structure.

## Canonical development runtime

- Start the complete local product only from this directory with `npm run dev`.
- Never start `uvicorn`, `next dev`, a legacy systemd unit, or a parent
  repository backend directly for V3.
- `npm run dev` must remain bound to `scripts/dev-stack.mjs`. The supervisor
  must start the backend only through `scripts/dev-backend.sh`.
- `scripts/dev-backend.sh` owns the development database and auth preflight. It
  must keep the working directory at the V3 root, use
  `sqlite:///./var/kolibri-v3.db`, apply all migrations, and require exactly
  one active platform owner before opening port `8002`.
- The V3 Python environment is `kolibri-v3/backend/venv`. Do not use the parent
  repository `backend/venv` or a `.venv` path.
- The frontend may start only after launch-bound backend health reports
  `status=ok`, `service=kolibri-v3`, and the supervisor's exact development
  instance ID. A backend exit must fence and restart the frontend.
- `npm run dev:web` is intentionally blocked. It allowed a stale or unrelated
  process on port `8002` to masquerade as the V3 backend.

After a runtime restart, verify all of the following before claiming success:

1. preflight reports the latest migration and `platform_owner=1`;
2. `GET http://127.0.0.1:8002/v1/health` reports `service=kolibri-v3` and a
   non-empty development instance ID;
3. `GET http://127.0.0.1:3103/app` returns HTTP 200;
4. the existing owner session or an explicitly authorized owner login reaches
   the server-backed workspace.

Never bootstrap, rename, rotate, or overwrite the existing owner credential
unless the product owner explicitly requests that mutation.

## Commands and verification

- Full local product: `npm run dev` (alias `dev:stack`). For a
  terminal-independent background stack: `npm run dev:persistent` (screen
  session; `dev:persistent:status|restart|stop`; live log in
  `var/dev-runtime/screen.log`). launchd is deliberately not used — macOS
  blocks LaunchAgents from reading `Documents/`.
- Verification pipeline: `npm run verify` (quick) or `npm run verify:full`.
  Gate order in `scripts/verify.sh`: structure -> architecture -> ruff ->
  compileall -> backend pytest -> frontend typecheck -> `npm test` -> cargo
  fmt/clippy/test for every `packages/*/Cargo.toml`. `--full` additionally
  runs `next build` and mobile typecheck/test/lint.
- Focused gates: `npm run verify:structure` and `npm run verify:architecture`
  are the executable architecture contracts; run them for structural changes.
  `npm run typecheck` alone is not a substitute for `npm run verify`.
- Single backend test:
  `PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/<file>.py -q`.
- Single web contract test: `node --test tests/<file>.test.mjs`. Root `tests/`
  is node test-runner web/architecture tests; the whole set is `npm test`.
- Browser E2E (`tests/e2e/`) is Playwright against the live dev stack
  (`npm run test:e2e:desktop`), tolerates retries, and is NOT part of
  `npm run verify`.
- Mobile (Expo in `apps/kolibri-mobile/`) is verified only in `verify:full`;
  `npm run mobile:typecheck` is the standalone check.

## Environment and setup

- The only Python environment is `backend/venv`, created with
  `backend/venv/bin/python -m pip install -r backend/requirements-dev.txt`.
  Never use a `.venv` or the parent repository `backend/venv`.
- `scripts/dev-backend.sh` loads a whitelist of keys from `.env.local`
  (`KOLIBRI_V3_*`, `NEXT_PUBLIC_*`, provider API keys). The existing platform
  owner credential is canonical — never bootstrap or rotate it.
- Generated artifacts (`generated/` from `server/`, root `openapi.json`,
  `dist/`) are generator output; do not hand-edit them.

## Repository boundary

- Only this directory (`kolibri-v3/`) is the active product. Parent-level
  `backend/`, `frontend/`, `kolibri-backend/`, `kolibri-v2/` are legacy
  contours: not fallbacks, not code sources. Do not copy code from them or run
  them for V3 work.

## Release lane

- `deploy/portable` is the only V3 production release lane.
- The portable builder must audit the complete Git commit, not only the V3
  subtree, and reject parent-level V3 Home/Primary/bare-metal release helpers.
- The retired parent V3 coordinator is allowed only as its byte-exact,
  read-only tombstone.
- The deleted `deploy/install-home.sh`, static V3 systemd units and static
  Nginx file are legacy paths and must not be restored.
- Do not use parent-level experimental bare-metal units to start or deploy V3.
- Production requires a clean committed candidate, the portable release gates,
  backup/restore and rollback rehearsal, canary evidence, and explicit owner
  GO.

## Agent skill system (обязательно)

Все agent-скиллы живут в `.agents/skills/` (16 групп 00–15 + плоские
`kolibri-*`/Expo/assistant-ui скиллы).

Для задач на `@assistant-ui/*`: канонический индекс API —
`https://www.assistant-ui.com/llms.txt`, полный дамп —
`https://www.assistant-ui.com/llms-full.txt`; если подключён MCP-сервер
`assistant-ui-docs`, используй его инструменты (`assistantUIDocs`,
`assistantUIExamples`) вместо загрузки полного дампа в контекст.

Для каждой задачи соблюдай цикл:

1. **DISCOVER** — определи затронутую поверхность (mobile/backend/ai/release)
   и entry point.
2. **SELECT SKILLS** — выполни
   `node .agents/scripts/skill-router.mjs "<формулировка задачи>" --top 5`
   и прочитай целиком `SKILL.md` выбранных скиллов (не весь каталог).
3. **PLAN** — вертикальный slice + acceptance criteria; зафиксируй запись в
   `.agents/progress-ledger.md` (состояние `IMPLEMENTING`).
4. **IMPLEMENT → INTEGRATE → VERIFY → FIX** — production-код раньше тестов;
   узкая проверка поведения; не перезапускай одну и ту же проверку без
   изменения кода или гипотезы; без mock вместо реальной интеграции.
5. **DONE** — по `definition-of-done`: поведение работает через реальный
   entry point, контракты/типы обновлены, нет плейсхолдеров, diff без
   постороннего хлама; обнови `progress-ledger` (состояние + evidence).

Состояния задачи: `DISCOVERING | IMPLEMENTING | INTEGRATING | VERIFYING |
BLOCKED | DONE`. После проверки текущей задачи продолжай следующей
production-задачей из раздела `Next` леджера. Контроллер и роутер описаны в
скиллах `development-controller` и `skill-router`.
