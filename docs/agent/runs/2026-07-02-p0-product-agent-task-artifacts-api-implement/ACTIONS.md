# Actions

- Added reusable agent API helpers in `ops/factory_control.py`.
- Added recursive artifact reference extraction for result manifests, PR links, preview links, logs, screenshots, image paths, and result references.
- Added public task summaries for `/v1/agents/status/{task_id}` so UI/Telegram can read stable task state without depending on the full internal task object.
- Changed `/v1/agents/status/{task_id}` to report `cancelled` and `failed` distinctly instead of treating every terminal task as `completed`.
- Changed `/v1/agents/cancel/{task_id}` to be idempotent for already-cancelled tasks and to avoid rewriting completed or failed task history.
- Added focused tests in `tests/test_prompt3_fabric_api_surface.py`.
