# Telegram Report Format

Rules:

- Do not send raw JSON to owner Telegram.
- Do not show Python traceback.
- Do not show `None` as if it were a value.
- Say "не проверено" when data was not collected.
- Say actual `0` only when Control Plane returned zero.
- Include attempted Control Plane endpoints when unavailable.
- Include repair task when unavailable.

Failure report must include:

- Status: не удалось проверить очередь.
- Reason: Control Plane недоступен.
- Meaning: values were not checked; they are not zero.
- Next repair task.

Success report must include:

- Control Plane used.
- Redis status.
- Queue count.
- Expired leases.
- Stuck heartbeat.
- Action.
