---
name: kolibri-mobile-chat
description: "Chat surface of the Kolibri Expo client driven by @assistant-ui/react-native + AG-UI: composer primitives, streaming states, attachments, dictation/voice, and result cards. Use when changing components/assistant-ui/composer/, message rendering, cards, attachments, or send/stop/streaming behavior."
---

# Kolibri Mobile Chat

Work inside `kolibri-v3/apps/kolibri-mobile`. Read `kolibri-v3/AGENTS.md`
first.

## Runtime-driven UI only

Read state from `useAuiState` (`thread.isRunning`, `composer.isEmpty`,
`thread.capabilities.dictation`, `thread.capabilities.voice`). Never fake
streaming or results locally — server data and AG-UI events only.

## Composer (`components/assistant-ui/composer/`)

The composer is split into small modules: `index.tsx` (shell + layout),
`controls.tsx` (send/stop/mic/voice), `attachments.tsx`, `glass.ts` (Liquid
Glass + Reduce Transparency), `enter-to-send.ts`, `styles.ts` (shared
StyleSheet). Edit the module that owns the change; keep the shell thin.

Single-row capsule («в один этаж»): `AttachmentButton` (+) → `Input` (flex) →
`ModelSelector variant="label"` → `MicButton` → `AuiIf`-swapped rightmost
circle: `VoiceButton` when empty, `SendButton` when text exists, `StopButton`
when running. Send/stop share the same 30px blue circle (`colors.send`); stop
renders an 11px square with `radius: 2`.
- Enter-to-send on web: the keydown can arrive before the last onChange
  propagates — read the value from the DOM target, sync via
  `aui.composer.setText`, then `aui.composer.send()`.
- The module sets `__KOLIBRI_MOBILE_ENTER_SEND__` as a QA marker; a stale
  Metro bundle may lack it — wait for the marker before interacting.
- Web-only pitfalls: `AccessibilityInfo.isReduceTransparencyEnabled` throws on
  web (use matchMedia); `pointerEvents` belongs in style, not as a prop.

## Attachments

Gate on `activeProjectId && activeThreadId`; call
`attachmentClient.capability()` then `expo-document-picker`, upload via
`attachmentClient.upload()` (API base from `mobile-session`, same-origin
through the gateway), then `aui.composer.addAttachment(...)` with the returned
`contentPath`.

## Dictation and voice

- Dictation: prefer `aui.composer.startDictation()` when the capability is
  on; on web fall back to Web Speech (`SpeechRecognition` /
  `webkitSpeechRecognition`, `ru-RU`, interim results into
  `aui.composer.setText`).
- Voice: `useVoiceControls` / `useVoiceState`, gated by
  `capabilities.voice`; filled blue circle, disconnects on press while
  connected.

## Result cards

- `src/product-chat/cards.ts` maps AG-UI `data.by_name` to card types;
  renderers live in `components/assistant-ui/cards/` and are wired in
  `components/assistant-ui/message.tsx`.
- Weather: temperature pill + condition/location + forecast rows.
- Image generation: skeleton ("Думаю…", 230x307) → preview strip (4 slots) →
  final 278x278 with Edit/share.
- Unknown data types must render a Fallback card, never crash.

## Model selector

`ModelSelector` (variants `label`/`pill`) loads the server catalog via
`MobileModelClient` and persists the choice with `saveSettings()`; only the
platform owner sees it. `variant="label"` is an inline composer element that
opens a bottom-sheet `Modal` (slide) — no centered dialogs.
