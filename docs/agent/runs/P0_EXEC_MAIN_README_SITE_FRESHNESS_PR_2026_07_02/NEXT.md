# Next

Exact next task:

`P0_PUBLIC_FACTORY_STATUS_TLS_AND_VHOST_REPAIR_2026_07_02`

Goal:

Repair the public `kolibriai.ru` TLS/vhost path so `curl -fsS https://kolibriai.ru/api/factory/status` returns valid JSON without `-k`.

Exact repair command for the server operator, after confirming the active nginx site and certificate owner:

```bash
sudo nginx -T | sed -n '/server_name .*kolibriai\\.ru/,/}/p'
sudo certbot --nginx -d kolibriai.ru -d www.kolibriai.ru
sudo nginx -t && sudo systemctl reload nginx
curl -fsS https://kolibriai.ru/api/factory/status
```

Rollback:

Restore the pre-repair nginx backup recorded in `docs/agent/dispatcher/FACTORY_STATUS.md` if the reload changes unrelated routes.
