# Owner Summary

Владислав, коротко:

- Gateway для управляющего чата добавлен как тонкий слой поверх Control Plane.
- Он умеет health/start/tick/fleet/queue/submit/status/artifacts/approval.
- Опасные действия не исполняются, а превращаются в approval request.
- Live proof `СТАРТ ФАБРИКИ -> task -> artifact` пока заблокирован: Control Plane `10.99.0.2:9101` не ответил, локальный `9101` не слушает.
- FormulaLM параллельно ведется: воспроизводимый 10-вопросный тест уже есть, текущий baseline `0.066391`.
- FormulaLM дальше ведем ближе к железу: latency/CPU/RAM замеры, меньше лишних слоев, оптимизация под реальные узлы.
