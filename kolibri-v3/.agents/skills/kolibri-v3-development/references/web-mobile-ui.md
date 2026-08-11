# Web & mobile UI pitfalls

## Tailwind variable utilities are not emitted

`bg-(--composer-bg)`, `rounded-(--composer-radius)`, `p-(--composer-padding)`
produce no CSS in this project, so elements styled only by them render with
transparent background and zero radius (the composer "never changed" and later
"looked broken"). Fix pattern:

- Declare the variables on the thread root (`THREAD_ROOT_CSS_VARS` in
  `components/assistant-ui/thread/thread-layout-config.ts`).
- Apply them with an explicit top-level rule in `app/globals.css`:

```css
[data-slot="aui_composer-shell"] {
  background: var(--composer-bg, var(--secondary));
  border-radius: var(--composer-radius, 1.5rem);
  padding: var(--composer-padding, 8px);
}
```

- Never put such rules only inside `@media (max-width: 959px)` — desktop misses
  them. Mobile-specific rules may live in the media query (higher specificity
  wins there).
- `var(--mobile-composer)` is undefined in the desktop scope: referencing it
  makes the property invalid (falls back to transparent). Use `--secondary`.

## react-native-web `pointerEvents: "box-none"`

RN-web 0.21.x emits CSS `pointer-events: box-none`, which is invalid; the
browser drops it and the element becomes `auto`. A full-screen
`StyleSheet.absoluteFill` wrapper (e.g., the pet mini assistant) then swallows
every wheel/touch event aimed at the chat list below — the classic "mobile
scroll does not work" root cause.

Fix: on web use `pointerEvents: "none"` on the wrapper; interactive children
(the pet button, its panel) keep the default `auto` and remain clickable:

```tsx
style={[
  StyleSheet.absoluteFill,
  Platform.OS === "web"
    ? { pointerEvents: "none" }
    : { pointerEvents: "box-none" },
]}
```

## RN-web FlatList auto-scroll

`VirtualizedList#scrollToEnd` derives the offset from per-cell frame metrics
that lag the DOM on web, and the FlatList resets `scrollTop` to 0 on re-render,
so new messages stay off-screen. Fix in
`apps/kolibri-mobile/components/assistant-ui/thread.tsx`:

```tsx
const scrollToBottom = () => {
  const node = listRef.current?.getScrollableNode?.();
  if (node) node.scrollTop = node.scrollHeight; // web
  else listRef.current?.scrollToEnd({ animated: false });
};
// onContentSizeChange → double requestAnimationFrame(scrollToBottom)
```

Track "at bottom" via `onScroll` and only auto-scroll when true (or accept
always-scroll for the send flow). Wheel/touch scrolling is native once no
overlay blocks it.

## GPT-style composer

- Send button renders only when the composer is non-empty
  (`AuiIf condition={(s) => !s.composer.isEmpty}`); stop button while running.
- Input auto-grows (`maxHeight`), Enter submits, Shift+Enter newline
  (assistant-ui defaults), mobile adds `unstable_insertNewlineOnTouchEnter`.
- Slash commands and @-mentions use assistant-ui
  `ComposerPrimitive.Unstable_TriggerPopover` (textarea mode; no Lexical needed)
  with `unstable_useSlashCommandAdapter` / `unstable_useMentionAdapter`.
  Commands transform the input via `aui.composer.setText(...)`; mentions insert
  structured directives (`:context[Проект]{name=project}`). Wrap `Root` in
  `Unstable_TriggerPopoverRoot`; the shell needs `relative` so the absolute
  popover anchors above the composer.
- Render directive chips in user messages with a small `DirectiveText`
  component (regex `/:([\w-]+)\[([^\]]+)\](?:\{name=([^}]+)\})?/g`); the
  default `Text` part renders plain text otherwise.

## Drawer / off-screen content

The react-navigation drawer keeps its content mounted when closed (translated
off-screen). Those elements are still in the DOM and accessibility tree:
`elementFromPoint` and Playwright locators can resolve them while clicks fail
("element is outside of the viewport"). Always filter by on-screen rect and
verify hit-testing before concluding a control is broken. After logout the
drawer stays mounted; ensure the auth screen is not covered by an open drawer.
