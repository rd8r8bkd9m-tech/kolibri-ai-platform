# Kolibri Support

## Public product links

- Portal: <https://kolibriai.ru/>
- Application: <https://kolibriai.ru/app>
- Developers: <https://kolibriai.ru/developers>
- API documentation: <https://kolibriai.ru/docs>

## Where to ask

- Reproducible product bug: [Bug report](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/issues/new?template=bug_report.yml)
- Product proposal: [Feature request](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/issues/new?template=feature_request.yml)
- Security vulnerability: private process in [SECURITY.md](SECURITY.md)

GitHub Issues is not an emergency operations channel and does not provide an
SLA. Production incidents visible to users should include the affected URL and
release identity, but never credentials or internal topology.

## Diagnostic checklist

Before reporting a bug, record:

- exact URL and UTC time;
- `release_id` from response headers or health response;
- desktop/mobile OS, browser and viewport;
- concise reproduction steps;
- expected and actual result;
- sanitized console/network error;
- whether retry and reload change the result;
- artifact ID and SHA-256 when the issue concerns a generated file.

For a capability issue, include its entry from `/v1/capabilities`, especially
`status`, `reason.code`, `as_of`/probe time and renderer/route evidence. Do not
report `21 connected nodes` as `21 executing nodes`: connected, fresh,
schedulable, active and verified are different states.

## Never attach

- API/provider/owner/Telegram keys;
- `Authorization` headers or cookies;
- `.env` files;
- raw user documents or personal data;
- private prompts, chain-of-thought or internal topology;
- full database or runtime-artifact directories.

Redact sensitive data while preserving the status code, endpoint, request ID,
release ID and timestamp needed for diagnosis.
