# Vista OS 11.1 Product Release — проверенная поставка

## Реализовано в этой итерации

- восстановление signed workspace session после reload;
- сохранение active app, active estimate и chat state;
- публичное скачивание client artifacts через scoped share token;
- отзыв клиентских ссылок;
- исправлена аутентификация Vista developer project keys;
- исправлен authenticated factory canary: user actions используют owner session, node actions — node token/HMAC;
- production Docker hardening;
- installable PWA;
- полный Tauri 2 shell scaffold;
- HTTP product smoke и backup/restore verification;
- раздельные CI gates для browser E2E, native shell, Docker и release-check.

## Локально доказано

```text
Backend/API/security: 14 passed
Frontend unit/component: 17 passed
Production Vite build: passed
HTTP product smoke: passed
Authenticated factory canary: passed
Backup/restore verification: passed
Production environment readiness: green
```

Rust/Tauri native check, Docker image build and browser Playwright E2E вынесены в обязательные GitHub Actions jobs, поскольку текущая sandbox-среда не предоставляет Docker/Rust и блокирует навигацию Chromium административной политикой.
