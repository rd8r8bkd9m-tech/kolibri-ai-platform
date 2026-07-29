# Weather widget design QA

final result: passed

## Scope

- Reference: `codex-clipboard-a13982bd-cee6-4e98-874f-19e4bc6542f1.png`
- Implementation: canonical assistant-ui `makeAssistantToolUI` for `get_weather`
- Desktop QA viewport: 1440 × 900
- Reference card crop: 846 × 636
- Implementation card: 736 × 542
- Side-by-side evidence: `.design-qa/weather-widget-comparison.png`

## Visual comparison

- Dark photographic rain background, large temperature, city heading, high/low
  values, five-column forecast, rounded card and inset forecast panel match the
  reference hierarchy and proportions.
- Russian labels are an intentional product localization.
- Current condition, feels-like temperature, humidity, wind, precipitation,
  observation time and source remain visible because they are useful real data,
  not demo decoration.
- The implementation uses a real raster asset and Lucide weather icons. It does
  not use CSS-drawn imagery, gradients or blur effects.

## Responsive and interaction checks

- Desktop: all five forecast days are visible without clipping.
- Narrow viewport: the main conditions remain readable and the forecast strip
  is horizontally scrollable instead of shrinking labels or overlapping.
- The widget is rendered from the real `get_weather` tool result.
- Loading state is announced with `role="status"` and the final card has a
  location-specific accessible region label.

## Dynamic scene checks

- `weatherCode` and `isDay` from `get_weather` select the scene. Text parsing is
  used only as a fail-safe for older persisted widget payloads.
- Rain: the real rain texture runs `kolibri-weather-rain-flow`; two browser
  measurements returned different transform matrices.
- Clear day: the clear-day photographic scene contains a rotating Lucide sun.
- Clear night: the clear-night photographic scene contains a floating Lucide
  moon; no sun layer is mounted.
- Cloud, snow and storm codes have dedicated scenes. Snowflakes fall and storm
  lighting pulses without changing the weather data.
- IntersectionObserver pauses every off-screen scene. Browser evidence
  confirmed `animation-play-state: paused` outside the viewport and `running`
  for the visible rain card.
- `prefers-reduced-motion: reduce` disables every scene animation.
- Narrow live-state screenshot:
  `.design-qa/weather-widget-dynamic-rain.png`.

## Intentional differences

- The reference contains English city/day labels; Kolibri uses Russian locale.
- The reference is a static design example; Kolibri keeps source attribution
  and live observation metadata.
