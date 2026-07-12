# REG.RU DNS baseline for kolibriai.ru

Captured read-only in the owner's authenticated Yandex Browser session on 2026-07-12. No DNS record was created, edited or deleted.

## Current authoritative zone

| Type | Name | Value | Observed public TTL |
| --- | --- | --- | ---: |
| A | `@` | `178.207.11.90` | 21600 seconds |
| A | `www` | `178.207.11.90` | 21600 seconds |
| A | `hotel` | `217.60.62.39` | 21600 seconds |

The zone uses REG.RU name servers `ns1.reg.ru` and `ns2.reg.ru`.

## Required future diff

The canonical product routes `/app`, `/developers`, `/docs`, `/control`, `/wallboard`, `/share/*` and `/v1/*` are same-origin paths and require no DNS changes.

The plan additionally names `status.kolibriai.ru` and `*.preview.kolibriai.ru`. Neither currently resolves. They must not be added until the independent status service and isolated preview ingress have passed their own TLS/health canaries. Their final targets cannot be inferred from the current apex record.

Before the protected save action, the release controller must provide an exact record type/name/value/TTL diff, TLS certificate readiness, health evidence and a rollback diff. DNS mutation remains owner-gated.
