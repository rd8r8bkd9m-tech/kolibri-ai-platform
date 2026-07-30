# ChatGPT mobile state matrix

Capture date: 2026-07-30 (Europe/Moscow)

Capture source: native ChatGPT on an iPhone viewed through Apple iPhone
Mirroring (`com.apple.ScreenContinuity`). Every durable frame in this directory
is the uncropped Computer Use capture at 318 × 701 px. The phone was already
authenticated. No account, privacy, security, subscription, or permission
setting was changed.

Status meanings:

- `confirmed`: inspected live and saved as durable evidence in this directory.
- `reference-only`: present in the user-supplied reference set, but not yet
  recaptured in the current live ChatGPT build.
- `manual capture needed`: the iPhone mirror did not expose ChatGPT controls in
  the macOS accessibility tree, and coordinate clicks became unavailable after
  the mirror handed input focus to the phone.

| Surface / state | Status | Durable evidence | Current-build observations |
| --- | --- | --- | --- |
| Empty chat, light | confirmed | `01-empty-chat-light.jpg` | Static centered `Chat` title; circular hamburger and new-chat controls; three starter actions; fixed two-row composer. |
| Composer focused, light | confirmed | `02-composer-focused-light.jpg` | Input caret is visible; hardware keyboard input keeps the software keyboard hidden; controls do not jump. |
| Weather prompt composed | confirmed | `03-weather-question-composed.jpg` | Multiline input expands upward while the action row remains fixed. |
| Weather streaming / stop | confirmed | `04-weather-streaming-stop.jpg` | Send control becomes a blue stop square; header switches from the empty-chat control to edit + overflow. |
| Active chat + weather result | confirmed | `05-weather-result-light.jpg` | Compact weather card, assistant prose, centered scroll-to-bottom control and fixed composer coexist without horizontal overflow. |
| Image prompt composed | confirmed | `06-image-question-composed.jpg` | Four-line prompt expands the composer to 139 px high; plus/model/mic/send stay on the bottom row. |
| Image request sent / stop | confirmed | `07-image-streaming-stop.jpg` | User bubble is right aligned; the blue stop square remains available during generation. |
| Image generation initial skeleton | confirmed | `08-image-generation-skeleton.jpg` | `Думаю` label and a 230 × 307 rounded placeholder appear before the generated asset. |
| Image generation preview stage | confirmed | `09-image-generation-preview-strip.jpg` | Placeholder widens; `Предпросмотр` pill and four thumbnail slots appear before completion. |
| Generated image result | confirmed | `10-image-result-light.jpg` | 278 × 278 image card, `Редактировать` pill, in-card share and secondary action row. |
| Empty chat, dark | reference-only | user reference `19FD648A-…/1-Вставленное-изображение-1.jpg` | Do not change the persistent theme solely for research. |
| Sidebar open | confirmed | `11-sidebar-open-light.jpg` | Current build keeps about one quarter of the previous chat visible at right; existing destinations and footer controls remain unchanged. |
| Sidebar close transition | manual capture needed | user reference `44FF0CAB-…/2-Вставленное-изображение-2.jpg` | Fully open endpoint is confirmed; close timing and intermediate animation frames are not. |
| Conversation long press | manual capture needed | none | Need press duration, haptic/scale/highlight response and menu placement. |
| Projects | confirmed | `12-projects-light.jpg` | Current tabs, four project rows, pin state, add action and fixed bottom search are visible. |
| Library | confirmed | `13-library-light.jpg` | Current category tabs, two-column mixed folder/image/document grid, overflow action and fixed bottom search are visible. |
| Remote | confirmed | `14-remote-light.jpg` | Current connection chips, project/chat sections, row actions, loading indicator, search and primary chat action are visible. |
| Remote sort menu | confirmed | `15-remote-sort-menu-light.jpg` | Current menu groups sorting and management in one rounded trailing sheet. No selection was changed. |
| Remote connection settings | confirmed | `16-remote-settings-connections-light.jpg` | Current connection and editor preference groups were inspected read-only; no switch or connection was changed. |
| Account / settings (read-only) | manual capture needed | user reference `C028C7BC-…/1-Вставленное-изображение-1.jpg` | Do not enter privacy, security, credentials, billing or subscription flows. |
| Model / effort menu | manual capture needed | user reference `44FF0CAB-…/5-Вставленное-изображение-5.jpg` | Need current selected model, menu geometry, radio/check state and close transition. |
| Plus / tools / attachment menu | manual capture needed | user reference `44FF0CAB-…/6-Вставленное-изображение-6.jpg` | Inspect menu only; do not grant camera/photo/files permissions or upload a file. |
| Software keyboard open / close | manual capture needed | user references `44FF0CAB-…/5-6`, `AF924D2B-…/1`, `79345E22-…/2` | The mirrored session used the Mac hardware keyboard, so the iOS keyboard stayed hidden. |
| Remote active chat → chat list back transition | confirmed | `18-active-chat-back-light.jpg`, `19-back-transition-intermediate-light.jpg`, `20-chat-list-light.jpg` | Top-left circular back control returns from an active remote chat to its chat list. One intermediate translated frame and the settled endpoint were captured. |
| Other back transitions | manual capture needed | user references `44FF0CAB-…/6`, `AF924D2B-…/1` | Still need project/library ↔ chat, account settings ↔ sidebar and Kolibri estimate editor ↔ main chat. |

## Short manual capture sequence

Coordinates below are relative to the current 318 × 701 mirror capture. Fetch a
fresh screenshot after every action; after navigation, use the visible label
rather than reusing a stale coordinate.

1. Empty/active chat hamburger: center `(39, 100)`. Leave the sidebar open.
2. In the open sidebar, capture first. Then long-press a visible conversation
   row near its text center for approximately 600 ms and leave the action menu
   open.
3. Reopen the sidebar and select, one at a time, the existing labels
   `Проекты`, `Библиотека`, and `Удаленно`; leave each destination untouched
   after it opens.
4. Reopen the sidebar and open the existing account/settings control at the
   bottom. Leave the settings root visible; do not open security, privacy,
   billing, subscription or credentials.
5. Return to chat. Composer controls in the current capture are: plus
   `(37, 647)`, model/effort `(159, 647)`, microphone `(243, 647)`, live voice
   `(281, 647)`. Open plus and model menus one at a time and leave each open.
6. Tap the input around `(131, 614)` to show the software keyboard if iOS
   permits it; dismiss it with the system keyboard-dismiss action and leave the
   chat visible.
7. For back-transition evidence, open an existing project/library item, then
   stop on the first screen that exposes the top-left back control.

## Automation limitation observed after authorization

Coordinate clicks became available after targeting
`/System/Applications/iPhone Mirroring.app`, invoking the window's exposed
`Raise` action, and fetching a fresh state. This enabled captures `11`–`16`.
The API does not expose pointer-down duration. A one-pixel `drag` was attempted
as the only available hold-like primitive, but it failed before changing the
phone with:

`Computer Use server error -10005: noWindowsAvailable`

Right-click was not treated as evidence of an iOS long press. The long-press
row therefore remains unconfirmed. When `noWindowsAvailable` recurs, a fresh
state and `Raise` may restore ordinary coordinate clicks; it does not add a
duration-capable gesture primitive.
