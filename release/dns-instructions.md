# DNS instructions for kolibriai.ru

These records are intended for REG.RU zone management after GitHub Pages is enabled.
Do not remove MX/TXT/SPF/DKIM mail records unless explicitly approved by the owner.

## Required records

| Type | Host | Value | Purpose |
| --- | --- | --- | --- |
| A | @ | 185.199.108.153 | GitHub Pages apex |
| A | @ | 185.199.109.153 | GitHub Pages apex |
| A | @ | 185.199.110.153 | GitHub Pages apex |
| A | @ | 185.199.111.153 | GitHub Pages apex |
| CNAME | www | rd8r8bkd9m-tech.github.io. | GitHub Pages www alias |
| A | api | `<production-vps-ip>` | Kolibri backend/control-plane |

## Safe operating rules

- Before changing DNS, save current zone records to `release/dns-before.txt`.
- After changing DNS, save final zone records to `release/dns-after.txt`.
- If REG.RU requires login, password, SMS, 2FA or CAPTCHA, stop and return `USER_ACTION_REQUIRED`.
- Do not store REG.RU cookies, tokens, recovery codes, passwords or screenshots containing secrets.
- Do not configure `api.kolibriai.ru` until a production VPS IP is confirmed.
