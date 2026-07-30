# Kolibri AI Mobile

Нативный клиент Kolibri Platform на Expo SDK 57, React Native 0.86,
Expo Router и `@assistant-ui/react-native`. Это не WebView и не отдельный
локальный продукт: авторизация, задачи, сообщения и AG-UI-поток принадлежат
серверу V3.

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
- compile-time registry для vertical surfaces: сервер может активировать только
  встроенный renderer при одновременном наличии capability и entitlement.

Вложения, камера, собственная диктовка, realtime voice, push и offline writes
не имитируются. Кнопка вложений отключена до появления серверного контракта.
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

Канонический каталог хранится в V3:

- `public/pets/manifest-v1.json`;
- runtime 512 px WebP в `public/pets/active`;
- thumbnails 144 px WebP в `public/pets/thumbs`.

Metro требует статические пути, поэтому релизные копии зарегистрированы явно в
`src/pets/registry.ts` и лежат в `assets/pets`. Remote URL, SVG-подмена, emoji и
runtime-загрузка непроверенного персонажа не используются.
