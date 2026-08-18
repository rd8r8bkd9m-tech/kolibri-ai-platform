---
name: kolibri-vertical-registry
description: "Add or change a Kolibri vertical surface (construction-estimates today): compile-time allowlist in apps/kolibri-mobile/src/verticals/registry.ts, capability/entitlement/rendererKey gating, and honest surface-boundary rendering. Use when wiring a new vertical, fixing surface visibility, or changing entitlement gates."
license: MIT
---

# Kolibri Vertical Registry

Работаем внутри `kolibri-v3/`. Сначала прочитать `kolibri-v3/AGENTS.md` и
`apps/kolibri-mobile/README.md`.

## Когда использовать

- Подключение новой вертикальной поверхности (не только сметы).
- Вертикаль видна/скрыта неправильно, entitlement-гейт ошибочен.
- Изменение границы поверхности (surface-boundary) или allowlist.

## Workflow

1. Завести контракты/клиент в `src/verticals/<vertical>/` (см. «Как добавить вертикаль» ниже).
2. Зарегистрировать в `registration.ts` и добавить в `VERTICAL_NAVIGATION_ALLOWLIST`.
3. Написать `access.ts` (fail-closed) и рендер через `surface-boundary.tsx`.
4. Добавить контрактные тесты; прогнать `npm run mobile:typecheck` и тесты.
5. Смоук в Playwright: без entitlement — причина, с entitlement — реальные данные.

## Модель

Вертикаль — серверно-управляемая поверхность мобильного приложения. Клиент
содержит **compile-time allowlist** рендеров; рантайм-манифест может только
включить уже существующую запись, но не скачать UI или произвольные действия.

Тройной гейт (все три условия обязательны):

1. `capability` — `user.capabilities` содержит id (например `construction.estimates.workspace`);
2. `entitlement` — `user.entitlements` содержит id (например `construction.estimates.use`);
3. `rendererKey` — клиент собрал рендер с этим ключом (например `construction.estimate.renderer.v1`).

## Файлы

| Файл | Роль |
|---|---|
| `apps/kolibri-mobile/src/verticals/contracts.ts` | Типы `CapabilitySnapshot`, `VerticalNavigationRegistration` |
| `apps/kolibri-mobile/src/verticals/registry.ts` | `VERTICAL_NAVIGATION_ALLOWLIST` + `availableVerticalNavigation()` |
| `apps/kolibri-mobile/src/verticals/<vertical>/registration.ts` | Регистрация: `id`, `label`, `capability`, `entitlement`, `rendererKey`, `allowedActions` |
| `apps/kolibri-mobile/src/verticals/<vertical>/access.ts` | Функция доступа: `{enabled:true}` или `{enabled:false, reason}` — fail-closed с объяснением |
| `components/shell/surface-boundary.tsx` | Граница поверхности — честный fallback, без фейковых данных |

## Как добавить вертикаль

1. Завести контракты/клиент в `src/verticals/<vertical>/`.
2. Зарегистрировать в `registration.ts` (новый `verticalId` и `rendererKey`).
3. Добавить в `VERTICAL_NAVIGATION_ALLOWLIST` в `registry.ts`.
4. Написать `access.ts` с fail-closed логикой и человекочитаемой причиной.
5. Рендерить через `surface-boundary.tsx`: при `enabled:false` — причина, не заглушка-декорация.
6. Добавить контрактные тесты в `apps/kolibri-mobile/tests/` (см. `native-vertical-contracts.test.mjs`).

## Rules

- Клиент не принимает client claims — сервер решает (capability/entitlement из сессии).
- Не показывать «придуманный успех»: нет доступа — честная причина, нет данных — loading/empty/error.
- Идентификаторы — kebab-case строки, уникальные в рамках продукта.

## Verification

- `npm run mobile:typecheck`; контрактные тесты вертикали
  (`node --test tests/native-vertical-contracts.test.mjs` из `apps/kolibri-mobile`).
- Смоук в Playwright: у пользователя без entitlement вертикаль скрыта или показывает причину; с entitlement — открывается на реальных данных.

## Related skills

- `kolibri-estimates-engine` — текущая вертикаль construction-estimates
- `kolibri-auth-session` — откуда берутся capabilities/entitlements пользователя
- `kolibri-billing` — entitlement-гейты
