# Kolibri + Nomad Notes (v1)

## Why include Nomad

V1 keeps Nomad as an optional runtime for future deployment. Kubernetes не обязателен.

## Minimum profile

- control-plane и locald оставлены как systemd-first;
- Nomad может использоваться для дополнительной планировки задач после v1;
- в v1 можно считать инфраструктурным фоном для будущей миграции.

## Security defaults

- без прямого доступа root от приложений,
- ограниченный сетьевой профиль сервисов,
- обязательный контроль `healthz` и heartbeat в наблюдаемом канале.
