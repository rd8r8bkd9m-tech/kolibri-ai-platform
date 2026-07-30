# Authenticated Moscow weather AG-UI journey — 2026-07-30

This is deterministic local release evidence for the exact prompt
`Какая погода в Москве?`. It exercises the real FastAPI HTTP contract and
durable Product/Data runtime while replacing only the external weather
provider boundary. It does not contact production or an external weather
service.

## Contract covered

- browser registration establishes the signed session cookie;
- the mutation uses the matching same-origin CSRF token;
- `POST /v1/chat/ag-ui` returns the durable AG-UI SSE projection;
- the server selects `get_weather` from the exact Russian prompt;
- tool arguments contain the requested location and forecast horizon;
- the result identifies normalized city `Москва`, an offset-aware observation
  time, a matching first forecast date and an HTTPS source;
- the user and structured assistant tool result persist in thread history;
- durable run and event rows are terminal, contiguous and time ordered;
- a second tenant receives `404` for both run replay and thread history.

## Measured trace

One local warm run produced:

| Measure | Result |
|---|---:|
| HTTP submit → accepted | 10.011 ms |
| HTTP submit → first SSE event | 16.787 ms |
| HTTP submit → `RUN_FINISHED` | 76.028 ms |
| HTTP submit → response complete | 78.689 ms |
| Durable event sequence | 1–6, contiguous |

Correlation:

- public run ID: `run_weather_journey_01`;
- local durable run ID:
  `run_2c0af26e596e483dbcc69709ee82f065`;
- observation: `2026-07-30T09:15:00+03:00`;
- fixture source:
  `https://weather-provider.example.test/observations/moscow/2026-07-30`.

The durable run ID is test-local and contains no user, tenant or credential
data.

## Commands and results

From `kolibri-v3/backend`:

```text
venv/bin/python -m pytest -q -s tests/test_weather_user_journey.py
1 passed
```

```text
/Users/kolibri/Documents/Codex/kolibri-ai-platform/backend/venv/bin/ruff \
  check tests/test_weather_user_journey.py
All checks passed!
```

```text
venv/bin/python -m pytest -q \
  tests/test_product_widgets.py \
  tests/test_product_chat_auth.py \
  tests/test_weather_user_journey.py
15 passed
```

## Remaining external gate

This closes the deterministic authenticated public-boundary regression. The
immutable release candidate must still repeat the prompt against the approved
live weather provider and capture browser-visible timing on physical Safari
and Android Chrome. That external release evidence is intentionally not
claimed here.
