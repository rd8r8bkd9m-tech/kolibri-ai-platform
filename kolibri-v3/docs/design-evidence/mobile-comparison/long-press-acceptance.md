# Mobile thread long-press acceptance

Date: 2026-07-30

Surface: Kolibri V3 mobile web, Chromium touch context, CSS viewport
390 × 844.

## Verified sequence

1. Open the mobile navigation drawer.
2. Emit `touchStart` at the center of an existing conversation row.
3. At 250 ms, verify `data-long-pressing="true"`.
4. At 650 ms, verify `data-thread-action-menu-open="true"`.
5. Emit `touchEnd`.
6. Verify the drawer remains visible and one menu remains open.
7. Verify the menu exposes `Закрепить`, `Архивировать` and
   `Удалить диалог`.

Evidence:
`thread-long-press-menu-390x844.png`.

## Negative checks

- Moving the touch point 22 px before the threshold cancels the gesture. The
  drawer remains open and no menu appears.
- A short tap opens the selected conversation, closes the drawer and does not
  open the action menu.
- Mouse input does not enter the touch long-press state.
- Draft conversations do not consume long-press input.

## Implementation note

The action menu is controlled. While the browser is delivering the synthetic
click that follows a successful touch hold, a transient close request from the
menu primitive is ignored. The click is then prevented before assistant-ui can
switch threads, and normal menu dismissal resumes immediately afterward. A
bounded 1.5 s fallback clears the suppression marker if a browser omits the
synthetic click.

This evidence verifies the Kolibri browser implementation. It does not claim
that the current ChatGPT iPhone long-press reference was captured; the
available iPhone Mirroring control API still lacks a duration-capable touch
primitive.
