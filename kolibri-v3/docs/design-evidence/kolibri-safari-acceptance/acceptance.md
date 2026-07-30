# Kolibri local Safari acceptance

Capture date: 2026-07-30 (Europe/Moscow)

This acceptance is intentionally separate from the native ChatGPT reference
research in `../mobile-chatgpt/`.

## Target

- Browser: Safari.
- URL: `http://127.0.0.1:3103/app`.
- Visible app state: compact Kolibri chat shell.
- Account/security boundary: no login, account, privacy, security, credential,
  subscription or permission setting was opened or changed.

## Result

- The local route returned HTTP 200 and rendered the compact shell in Safari.
- A warm `Cmd+R` reload reached the visible disabled composer and `Войти`
  action in 1818 ms.
- Timing boundary: measured from the reload command until the Safari
  accessibility tree exposed both `Сообщение для Kolibri` and `Войти`.
  Poll interval was 300 ms and the measurement includes Computer Use overhead.
- The Safari local session was unauthenticated. The composer exposed
  `Войдите в личный кабинет, чтобы написать Kolibri` and disabled message and
  attachment controls.
- Because the composer was disabled, the requested question
  `Какая погода в Москве?` was not submitted. Therefore `RUN_STARTED`, first
  visible answer and finish timings are not available from this sample.

## Evidence

- `01-unauthenticated-local-app-safari.jpg`: first visible authenticated-gate
  state, 726 × 719 px.
- `02-warm-reload-unauthenticated.jpg`: warm reload endpoint, 726 × 719 px.

## Required follow-up

Repeat the exact question in an already authenticated local Safari session and
record four timestamps from one run:

1. submit;
2. `RUN_STARTED` or the first running/stop state;
3. first visible assistant content;
4. terminal finish state.

Do not enter or change account/security settings solely to obtain the sample.
