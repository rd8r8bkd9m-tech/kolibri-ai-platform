# Local runtime and latency baseline — 2026-07-30

Observed at 12:05–12:07 MSK on the current local V3 development runtime.
This is diagnostic evidence, not a production SLO result.

## Runtime persistence

- V3 Uvicorn (`127.0.0.1:8002`) had been alive for about 14 hours.
- Its Codex app-server child had been alive for about 14 hours.
- The attached MiMo server (`127.0.0.1:50505`) had been alive for about
  14 hours.
- The provider Agent Host was also long-lived.
- `GET /v1/health` returned `200`.

This confirms that the current local execution architecture does not require a
new server process for every chat turn. Per-turn clients or sessions may still
perform provider work, but the server runtimes themselves are persistent.

## Historical time to first text

The local database was queried only in aggregate, without user content or
identity fields. For succeeded runs created in the preceding 24 hours, time to
first text was calculated from `chat_runs.created_at` to the first
`TEXT_MESSAGE_CONTENT` event:

| Selected profile | Samples | Mean | Minimum | Maximum |
|---|---:|---:|---:|---:|
| `codex-cli` | 55 | 5.52 s | 0.02 s | 22.38 s |
| `mimo-code` | 21 | 24.86 s | 0.02 s | 139.46 s |
| `auto` | 13 | 2.01 s | 0.02 s | 6.72 s |

The population mixes interactive and automated local runs, so these values
identify a direction rather than a release threshold. MiMo is the current
latency outlier and requires a fresh controlled sample plus trace attribution.

## Web shell

- First `/app` request after development compilation: 11.91 s total.
- Immediately repeated warm `/app` request: 1.51 s total.
- Warm `/api/v3/session`: 0.21 s total.

The 11.91 s result is a development compilation cost and must not be used as a
production response-time claim.

## Next evidence

1. Run one fresh warm Safari turn with the exact prompt
   `Какая погода в Москве?`.
2. Record submit-to-accepted, submit-to-first-visible-text and total duration.
3. Correlate the run ID with backend and provider events.
4. Repeat for each enabled runtime profile.
5. Run the same measurement from the immutable production build and define the
   R1 alert/SLO boundary from those controlled samples.
