# Kolibri Shell — approved new-design source spec

## Source of truth

This specification is derived only from these two approved images:

- Desktop: `docs/design/approved/kolibri-shell-desktop.png` (`1487 × 1058`)
- Mobile: `docs/design/approved/kolibri-shell-mobile.png` (`853 × 1844`, approximately a `393 × 850` CSS-pixel viewport at 2.17× capture scale)

The official `kolibri-bird.png` remains unchanged. It is rendered as an image asset, never redrawn, recolored, approximated, or duplicated. No other Shell screenshot is a visual source.

## Visual system

### Color tokens

Values are sampled or closely estimated from the approved images; use them as stable tokens and tune only through same-viewport visual comparison.

| Token | Value | Use |
| --- | --- | --- |
| `canvas.desktop` | `#FDFDFB` | Desktop page background |
| `canvas.mobile` | `#F8F6F4` | Mobile page background |
| `surface.primary` | `#FFFFFF` | Sheets, controls, composer |
| `surface.message` | `#F4F2EF` | User message bubble |
| `surface.soft` | `#F3F7F6` | Teal-tinted icon wells / trace fill |
| `ink.primary` | `#16191D` | Primary text |
| `ink.secondary` | `#6F7478` | Metadata, timestamps, placeholders |
| `line.subtle` | `#E3E4E2` | Dividers and control borders |
| `accent.teal` | `#078E93` | Primary actions and verified state |
| `accent.teal.dark` | `#057A80` | Gradient endpoint / pressed state |
| `accent.teal.soft` | `#DCEEEE` | Quiet accent background |
| `accent.warning` | `#FFC43D` | Waiting verifier role |
| `accent.pdf` | `#F02D2D` | PDF action only |

Primary teal controls may use a restrained `#079398 → #047A80` vertical gradient. Do not spread accent color across neutral surfaces.

### Typography

Use `Inter Variable`, then `-apple-system`, `BlinkMacSystemFont`, `"Segoe UI"`, sans-serif. Numbers use tabular figures. Desktop body is compact; mobile body is deliberately larger.

| Role | Desktop | Mobile |
| --- | --- | --- |
| Project title | `18/24`, 500 | `24/30`, 600 |
| Message | `16/23`, 400 | `17/25`, 400 |
| Metadata | `13/18`, 400 | `13/18`, 400 |
| Work-trace title | `14/20`, 600 | `17/23`, 650 |
| Artifact title | `24/30`, 600 | `26/32`, 650 |
| Table / row text | `14/20`, 400–500 | `17/23`, 400–500 |
| Total label | `17/24`, 600 | `19/26`, 650 |
| Total value | `18/24`, 650 | `30/36`, 650 |
| Button label | `14/20`, 500 | `16/22`, 500 |

### Radii, borders, and shadows

- Desktop control radius: `10–12px`; user bubble: `18px`; attached toolbar: `0 0 16px 16px`; composer: `28px`.
- Mobile message bubble: `20px`; trace: `18px`; artifact sheet: `26px`; composer: `24px`; round controls: `999px`.
- Borders: `1px solid line.subtle`; mobile trace uses `1.5px solid accent.teal`.
- Desktop composer shadow: `0 10px 30px rgba(24, 31, 33, .10)`.
- Mobile sheet shadow: `0 12px 30px rgba(24, 31, 33, .08)`.
- Mobile composer shadow: `0 -6px 24px rgba(24, 31, 33, .08)`.
- No decorative glow, glass blur, nested card shadows, or dashboard tiles.

## Desktop geometry (`1487 × 1058` reference)

### Frame and header

- Header: full width, `90px` high, white/warm-neutral, `1px` bottom divider.
- Mascot slot: approximately `56 × 56px`, `32px` from the left and `17px` from the top. The transparent bird occupies the slot without a desktop circle.
- Project selector starts at approximately `120px`; keep a `10px` gap between title and `ChevronDown`.
- Header actions: `History` control about `150 × 48px`, then a `56 × 48px` overflow control; right inset `32px`, gap `24px`.
- No permanent sidebar, rail, dashboard, or vertical category menu is visible in this state.

### Conversation column

- Main content max width: `1120px` (`~75%` of the reference width), centered; side gutters are approximately `184px`.
- Top content padding: `30px`; bottom reserve: at least `122px` for the fixed composer.
- User message: right aligned, max width `455px`, padding `17px 18px`, radius `18px`; metadata sits `8px` above it.
- Assistant response: full content width, with `24–28px` gap below the user bubble; metadata first, then `12px` to the message.
- Message paragraphs must remain text, not card surfaces.

### Work trace

- Compact desktop trace is a single horizontal band approximately `1120 × 60px`.
- Left cluster: `32px` circular disclosure, title, then teal progress (`5/5 завершено`).
- Stages form an inline sequence separated by `1px × 24px` rules. Each stage uses a `16px` verified icon and a short label.
- Stages scroll horizontally only below the desktop breakpoint; they must not wrap into a noisy grid.
- Completed state uses real event data. Expanded state opens below the band and preserves the conversation width.

### Estimate artifact

- Artifact width: the full `1120px` content column; it is not wrapped in a decorative outer card on desktop.
- Attached action strip: centered, approximately `578 × 44px`, with actions `Редактировать`, `Источники`, `PDF`, `Открыть окном`.
- Artifact heading starts `10px` below the toolbar; subtitle sits `4px` below the heading.
- Editable table grid:

```text
28px index | minmax(420px, 1fr) description | 88px unit |
118px quantity | 124px price | 112px amount | 28px menu
```

- Column gaps: `16px`; row control height: `38px`; vertical row gap: `8px`.
- Numeric fields are right aligned and use tabular figures. Inputs use `type="text"` with `inputMode="decimal"`; no browser spinner arrows.
- Total row: `56px`, top/bottom subtle dividers, label left and value right.
- Source verdict: `16px` teal verified icon followed by one quiet line of source status.
- PDF row: `44px` high, bordered, filename left, MIME/size and download icon right.

### Composer

- Fixed above the viewport bottom by `31px`; centered; width `min(910px, calc(100vw - 48px))`; reference height approximately `88px`.
- White surface, `28px` radius, `12px` inner padding.
- Left-to-right: `52px` plus button; mode pill; flexible textarea; `48px` microphone; `52px` send button.
- Textarea grows up to six lines; after that it scrolls internally. Submit never shifts the composer horizontally.

## Mobile geometry (`~393 × 850` CSS-pixel target)

### Frame and header

- Single-column canvas; horizontal padding `16px`; zero horizontal overflow.
- Top safe-area plus `9px` visual inset.
- Shared mascot/navigation slot: `56 × 56px`, left `14px`. In the closed state it shows the one official bird inside a white circular surface with a subtle shadow.
- Centered project selector: title `Дом 100 м²` with `ChevronDown`; its optical center must remain the viewport center, independent of the mascot slot.
- Hamburger and bird occupy the same slot and crossfade/morph between navigation states; they are never simultaneous DOM-visible controls. Respect `prefers-reduced-motion`.
- History and overflow move into the navigation sheet; they do not crowd the mobile header.

### Conversation

- User bubble: max width `232px` (`~59vw`), right aligned; `14px 15px` padding; `20px` radius.
- Assistant message uses the full readable width; top gap approximately `22px`; line length is naturally constrained by `16px` gutters.
- Message font is `17px` minimum. Timestamps remain `13px` and align to the message edge.

### Work trace

- Full width inside `16px` gutters; approximately `361 × 104px`; radius `18px`; `1.5px` teal border.
- First line: bold status, `6px` teal dot, progress text, disclosure icon aligned right.
- Second line: active actor with teal `Calculator` well; divider; waiting verifier with yellow `ShieldCheck` well.
- Third line: centered `Подробнее` action.
- Collapsing the trace preserves one live summary line. Expanded details open inline and stream safe summaries, tools, sources, checks, and verdicts—not private chain-of-thought.

### Estimate summary surface

- Inline artifact becomes a near-full-width sheet: `calc(100vw - 10px)`, centered, top radius `26px`, white surface.
- A `32 × 4px` neutral drag handle is centered `11px` below the top edge.
- Inner padding: `24px 26px 16px`.
- Artifact title uses `26/32` and remains on one line at the reference width.
- Category summary has three `48px` rows separated by subtle rules. Icon wells are `36px`; label grows; amount is right aligned.
- Total row uses a strong `30/36` total value and a single source-verdict line underneath.
- Action grid: three equal buttons, minimum `96 × 64px`, gap `12px`: `Pencil`, `MessageSquareText/Link` for sources, and red `FileText` for PDF.
- `Редактировать` opens a full-screen editor; mobile never squeezes the desktop seven-column table into the summary card.

### Composer

- Sticky/fixed above `env(safe-area-inset-bottom)` with `10px` side and bottom inset; width `calc(100vw - 20px)`; minimum height `82px`; radius `24px`.
- First row is the text field with `17px` placeholder.
- Second row: `40px` plus control, centered reasoning/mode pill (`min-height: 40px`), `44px` send control aligned right.
- Composer position follows `visualViewport`; the focused editor must remain above the software keyboard.
- Microphone is omitted in the approved mobile state until its live capability is available.

## Responsive transformation

Use one semantic component tree, not separate feature implementations.

| Desktop | Mobile |
| --- | --- |
| Header history and overflow controls | Navigation sheet actions |
| Transparent mascot in header | Mascot in circular navigation control |
| Horizontal trace band | Bordered stacked trace summary |
| Editable estimate table | Readable estimate summary sheet |
| Attached artifact toolbar | Three large artifact actions |
| Single-row composer | Two-row keyboard-safe composer |
| Optional detached artifact window | Full-screen artifact/editor surface |

Recommended layout breakpoints:

- `>= 1024px`: exact desktop composition.
- `768–1023px`: same semantics with a `minmax()` artifact grid and horizontally scrollable table region.
- `< 768px`: approved mobile transformation above.

Content, response state, revisions, trace events, and artifact identity remain the same across breakpoints.

## Component and asset mapping

- `MascotPortal`: real `public/kolibri-bird.png`; one mounted visual instance, moved between approved slots.
- Navigation/action icons: use one installed icon library (Lucide is acceptable): `Menu`, `ChevronDown`, `History`, `MoreHorizontal`, `Plus`, `Mic`, `ArrowUp`, `Pencil`, `Link`, `FileText`, `Download`, `ExternalLink`, `CheckCircle2`.
- Work roles: `Calculator` and `ShieldCheck` inside real circular icon wells.
- Estimate categories: `BrickWall`/`Boxes` for foundation, `House` for shell, `Droplets` for engineering systems.
- Do not use emoji, text glyphs as icons, inline/custom SVG, CSS art, placeholder assets, or a second mascot.

## Visual acceptance contract

1. Compare the built desktop state to the desktop source at `1487 × 1058`.
2. Compare the built mobile state at `393 × 850` CSS pixels to the normalized mobile source.
3. Assert exactly one visible official mascot.
4. Assert no permanent sidebar/dashboard in the approved state.
5. Assert mobile has one vertical scroller and zero horizontal overflow.
6. Assert the composer remains visible with the mobile keyboard and desktop viewport resize.
7. Assert all visible controls have real actions and at least `44 × 44px` mobile targets.
8. Assert estimate total, source state, PDF availability, and work-trace stage come from backend data—not hardcoded success copy.
9. Assert no console, asset, MIME, session-bootstrap, ResizeObserver, or service-worker errors.
10. Preserve the approved quiet hierarchy: conversation first, live trace second, artifact third, composer always available.
