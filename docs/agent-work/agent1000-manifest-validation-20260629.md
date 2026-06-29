# Валидация agent1000 manifest

Дата: 2026-06-29  
Источник: `ops/agent1000_manifest.json`  
Вердикт: **FAIL**

`ops/agent1000_manifest.json` проходит синтаксическую проверку:

```bash
python3 -m json.tool ops/agent1000_manifest.json
```

Манифест корректно фиксирует `target_agents: 1000`, `remote_only: true`, 24 роли
и сумму агентов по ролям 1000. Также есть remote-only инварианты, запрещающие
model work на Mac.

Причина FAIL: как машинно применимый манифест быстрого масштабирования он
неполный. Обязательные поля `batches`, `safety_limits` и `no_mac_experiments`
отсутствуют. Вместо `batches` есть `capacity_batches`, но валидатору нужен
именно требуемый машинный ключ. Кроме того, роли и batch purpose в основном
описательные: нет `task_templates`, `task_envelopes`, схем lease payload,
исполняемых маршрутов, success/blocker условий и artifact contracts.

## Machine fix list

1. Добавить top-level `batches` или переименовать `capacity_batches` в
   `batches`; `scheduling_policy.batch_order` должен ссылаться только на
   существующие `batches[*].id`.
2. Добавить top-level `safety_limits` с машинными лимитами:
   `max_total_agents`, `max_agents_per_node_class`, `max_concurrent_leases`,
   `heartbeat_timeout_seconds`, `stale_after_seconds`,
   `max_dead_letter_rate`, `require_secret_redaction`,
   `forbid_darwin_model_work`.
3. Добавить top-level `no_mac_experiments: true`, чтобы preflight мог
   остановить Mac/Darwin эксперименты без NLP-разбора инвариантов.
4. Добавить `task_templates` для work lanes: `role_id`, `capability`,
   `ingress`, `lease_payload_schema`, `allowed_node_classes`,
   `artifact_contract`, `success_condition`, `blocker_condition`.
5. Дополнить каждую роль `task_template_ids` и машинными
   `allowed_actions`/`success_artifacts`, а не только текстовым `goal`.
6. Явно определить все pools, используемые ролями. Сейчас `pools` описывает
   только `mimo`, `codex`, `formulalm` на 375 агентов, хотя роли используют
   больше pool names.
7. Перевести `blocker_policy` из строк в объекты с `id`, `condition`, `action`,
   `severity`, `owner_role_id`.
8. Добавить JSON Schema или embedded `schema_contract` для обязательных полей и
   типов.

`ops/agent1000_manifest.json` этим отчетом не изменялся.
