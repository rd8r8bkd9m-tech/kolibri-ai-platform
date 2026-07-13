# Kolibri Mobile Shell — Design QA

Date: 2026-07-13
Surface: `https://kolibriai.ru/`
Viewport: `390 × 844` CSS pixels
Theme matrix: light, dark

## Reference contract

- Empty conversation: `/tmp/codex-remote-attachments/019f4892-14c5-7e30-934f-d2ba8f0018f6/FBF5D255-37CF-4349-BF7C-1CAD723F4EC2/1-Вставленное-изображение-1.jpg`
- Answer state: `/tmp/codex-remote-attachments/019f4892-14c5-7e30-934f-d2ba8f0018f6/2EA85C96-5240-433E-BC40-80FD1EA4C472/1-Вставленное-изображение-1.jpg`
- Working states: `/tmp/codex-remote-attachments/019f4892-14c5-7e30-934f-d2ba8f0018f6/B6CDD9D2-D024-461B-8628-085BB8ED33AB/`
- Tool sheet: `/tmp/codex-remote-attachments/019f4892-14c5-7e30-934f-d2ba8f0018f6/417576EB-7F3D-4198-AC73-FBD8E9A292F5/1-Вставленное-изображение-1.jpg`
- Voice mode: `/tmp/codex-remote-attachments/019f4892-14c5-7e30-934f-d2ba8f0018f6/35F1CB22-D923-4A19-A52A-416B8F79081A/1-Вставленное-изображение-1.jpg`
- Global mobile states and continuous background: `/tmp/codex-remote-attachments/019f4892-14c5-7e30-934f-d2ba8f0018f6/F84A778B-F9F3-428F-83B8-F5154790BE6A/`

## Implementation evidence

- `design-qa-empty-mobile-latest.png`
- `design-qa-drawer-mobile-latest.png`
- `design-qa-tools-mobile-latest.png`
- `design-qa-voice-mobile-latest.png`
- `design-qa-working-mobile-latest.png`
- `design-qa-estimate-answer-mobile-latest.png`
- `design-qa-estimate-editor-mobile-latest.png`
- `design-qa-estimate-editor-mobile-final.png`
- `design-qa-empty-unified-mobile.png`
- `design-qa-working-unified-mobile.png`
- `design-qa-theme-dark-mobile-latest.png`

Combined, same-viewport comparisons:

- `design-qa-compare-empty.png`
- `design-qa-compare-tools.png`
- `design-qa-compare-voice.png`
- `design-qa-compare-working.png`

## Verified interactions

- Hamburger opens the componentized navigation drawer.
- Drawer actions navigate to New project, Recent, Search, Files, and Settings.
- Edge-swipe gesture code opens from the left edge and closes on a left swipe.
- `+` opens one modal tool sheet with a horizontal Photo/Camera/Files carousel.
- Only live-renderable capabilities are listed below the carousel.
- Voice mode changes the global header and composer controls without duplicate mascot instances.
- Light and dark settings update the shared document theme and all tokenized surfaces.
- Conversation background now remains one uninterrupted surface behind the top bar, content and composer in empty, working, answer and voice states.
- A real estimate request streams a working state, materializes an editable estimate, and exposes a real PDF.
- The verified PDF response is `application/pdf`, starts with `%PDF-`, and has non-zero bytes.
- Latest browser log slice contains no error-level entries; only Vite HMR/debug and React DevTools info.

## Findings

- P0: none in the tested navigation, tool-sheet, voice, theme, estimate-action, or PDF flows.
- Resolved: the mobile estimate editor toolbar scrolls within its own surface; position rows are componentized cards with labelled quantity, price and total fields and no numeric spinner controls.
- P1: conversation history is not yet durable across reloads.
- Resolved: provider route, response, source-search and artifact-verification stages are backend-authored events; the UI exposes no private chain-of-thought.
- P2: the app runs from the Vite dev server on the production domain during active development; a hashed release build remains a separate release gate.

## Result

Final result: **blocked** only on product-wide conversation durability. Backend-authored safe work events are now live; provider provenance is visible without exposing private chain-of-thought.
