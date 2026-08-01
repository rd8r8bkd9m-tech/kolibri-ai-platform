# Kolibri AI Mobile

Нативный клиент Kolibri Platform на Expo SDK 57, React Native 0.86,
Expo Router и `@assistant-ui/react-native`. Это не WebView и не отдельный
локальный продукт: авторизация, задачи, сообщения и AG-UI-поток принадлежат
серверу V3.

## Контур исполнения

Мобильный интерфейс разрабатывается и запускается только из этого каталога.
`npm run dev` из корня V3 поднимает единый UI-origin
`http://127.0.0.1:3103`: gateway маршрутизирует desktop User-Agent на внутренний
Next-процесс `3104`, а mobile User-Agent или `client=mobile` — на внутренний
Expo web/PWA-процесс `4103`. Оба клиента направляют запросы в один V3 backend на
`http://127.0.0.1:8002`. Пользователь всегда открывает один адрес, а серверные
чаты, авторизация и AG-UI контракт общие; desktop UI не используется как mobile
fallback.

При ширине viewport до 959 px desktop `/app` сохраняет тот же origin и добавляет
`client=mobile`; gateway переключает запрос на Expo без смены публичного порта.
Прямой `npm run dev:mobile` по-прежнему доступен для изолированной отладки Expo
на внутреннем `4103`, но это не второй пользовательский frontend.
Для локального запуска адрес API задаётся только через
`KOLIBRI_V3_MOBILE_API_BASE_URL` и по умолчанию жёстко равен `8002`; порты
`3103` и `4103` никогда не используются как API.

Для релизной сборки и нативного устройства клиент по умолчанию подключается к
`https://kolibriai.ru`.

## Настройка

По умолчанию клиент подключается к `https://kolibriai.ru`. Для другого
HTTPS-стенда скопируйте `.env.example` в `.env.local` и измените:

```bash
EXPO_PUBLIC_API_BASE_URL=https://example.test
```

`EXPO_PUBLIC_*` попадает в приложение. Здесь нельзя хранить API-ключи, токены,
пароли и другие секреты.

## Запуск

```bash
npm ci
npm start
```

Expo Go подходит для быстрой проверки JavaScript-среза. Релизная проверка
требует development/release build на реальном iPhone и Android-устройстве:
SecureStore, ротация сессии, background/foreground, клавиатура и AG-UI streaming
должны проверяться в нативном runtime.

## Обязательные статические и сборочные проверки

```bash
npm run typecheck
npm run lint
npx expo-doctor
npm run export:ios
npm run export:android
```

## Реализованный срез

- отдельная мобильная login/register/refresh/logout-сессия;
- refresh token только в SecureStore, access token только в памяти;
- реальная серверная история задач и операции pin/archive/delete;
- текстовый AG-UI чат через `assistant-ui`, отправка и остановка ответа;
- мультяшный pet mini-assistant на проверенных Kolibri assets: открывает
  компактный composer того же активного `assistant-ui` thread, отображает
  настоящие running/complete/incomplete состояния, поддерживает Reduce Motion,
  Android Back, safe area, accessibility и нативные haptics;
- нативные safe areas, светлая/тёмная тема, iOS Symbols и Android icons;
- универсальный shell без локальной поддельной истории;
- реальные вложения через `expo-document-picker` и V3 `/v1/attachments`:
  capability-check, bounded upload, idempotency и серверная ссылка в AG-UI;
- compile-time registry для vertical surfaces: сервер может активировать только
  встроенный renderer при одновременном наличии capability и entitlement.

Камера, собственная диктовка, realtime voice, push и offline writes пока не
подменяются фиктивными реализациями: для них нужен отдельный нативный и
серверный контракт. Кнопка вложений активируется только после server-owned
capability для уже созданной задачи.
Строительные сметы — подключаемый vertical pack `construction.estimates`, а не
сущность универсального shell. В bundle уже входит нативный real-data срез:
каталог `GET /v1/documents`, открытие `GET /v1/projects/{id}/estimate` и
компактное редактирование/версионное сохранение через
`PATCH /v1/projects/{id}/estimate`. Entry fail-closed: он доступен только при
одновременной выдаче сервером `construction.estimates.workspace` и entitlement
`construction.estimates.use`. Оба значения приходят только из server-owned
tenant/user projection в V3 identity; клиентские claims не принимаются. При
отсутствии или повреждении projection интерфейс fail-closed и показывает
disabled boundary, а не локальный mock.

## Источник pet assets

Идентичность и версия motion-asset принадлежат единому V3-каталогу
`lib/pets/catalog.ts`; desktop и mobile не копируют характеры, роли или
состояния питомцев. Web/PWA читает fallback и atlas из канонического
`public/pets`, а Expo web получает то же дерево через ссылку
`apps/kolibri-mobile/public/pets` — второго web-набора файлов нет.

Нативному Metro нужны статические `require`, поэтому проверенные release-копии
лежат в `assets/pets` и один раз сопоставляются id в `src/pets/assets.ts`.
`src/pets/assets.web.ts` заменяет только транспорт картинок на публичные URL;
контракт состояний остаётся общим в `lib/pets/motion.ts`. Remote URL,
SVG-подмена, emoji и runtime-загрузка непроверенного персонажа не используются.
