---
name: kolibri-mobile-navigation
description: "Navigation and surfaces of the Kolibri Expo client: expo-router routes, drawer sidebar, bottom sheets, back transitions, and the vertical surface registry. Use when changing app routes (app/), the drawer, projects/library/remote screens, sheets, or draft/scroll preservation across navigation."
---

# Kolibri Mobile Navigation

Work inside `kolibri-v3/apps/kolibri-mobile`. Read `kolibri-v3/AGENTS.md`
first.

## Routes and shell

- expo-router routes in `app/`: `index` (chat), `projects.tsx`, `library.tsx`,
  `remote.tsx`. The drawer is wired in `app/_layout.tsx`; header lives in
  `components/shell/mobile-header.tsx`.
- Only bottom sheets (slide `Modal`, rounded top, backdrop) and the side
  drawer — no centered modals. `promptAsync` in `lib/dialogs.tsx` is a slide
  sheet; the model picker is a slide sheet too.

## Drawer (`components/thread-list/drawer-content.tsx`)

- Destinations: Проекты, Библиотека, Удаленно (+ Сметы when the capability
  gate passes via `src/verticals/registry.ts`). Footer: search, new chat,
  settings.
- No scrim; rounded leading edge. Toggle `aria-hidden` only after the drawer
  transition ends, otherwise focus is hidden from assistive tech.
- Hamburger mark: two bars, bottom shorter (`components/shell/hamburger-mark.tsx`).

## Back transitions

Preserve composer draft and scroll position across back navigation
(reanimated-driven); never reset thread state when returning from
projects/library/settings.

## Vertical surfaces

- Activate surfaces only through the compile-time registry
  (`src/verticals/registry.ts`) AND capability AND entitlement checks.
- When the server does not provide a surface, render the honest boundary
  (`components/shell/surface-boundary.tsx`) — no local fake data.
- Projects screen uses real server data
  (`ProductChatClient.listThreads()` + `/v1/projects/{id}/context`), bottom
  search, trailing sort/action rows.
