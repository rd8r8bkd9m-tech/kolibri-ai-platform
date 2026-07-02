# Design Refresh Plan

Positioning:
- Kolibri AI — суверенная AI-фабрика для задач, документов, смет, кода и агентов.

Design direction:
- First screen should feel like `kolibriai.ru`: chat-first, calm, centered, and immediately usable.
- Secondary capabilities stay accessible through navigation but should not compete with the main ask box.
- Runtime state should be visible without turning the portal into a Control Plane dashboard.

Applied UI changes:
- Replaced generic welcome with "Чем могу помочь?"
- Added `kolibriai.ru` domain cue.
- Replaced generic quick cards with production-like prompt actions:
  - create estimate
  - write contract
  - generate report
  - analyze data
- Added compact status pills for factory, chat, and knowledge.
- Added service banners for documents/search.
- Reduced decorative background motion/orb treatment.

Future polish:
- Add a compact top-level mobile action sheet for documents/search/factory.
- Add a deploy smoke banner only in admin/debug mode, not for normal users.
- Add production screenshots to this run after `kolibriai.ru` deployment routing is fixed.

