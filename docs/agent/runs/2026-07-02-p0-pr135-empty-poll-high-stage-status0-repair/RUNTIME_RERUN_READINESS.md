# RUNTIME_RERUN_READINESS

Ready for GitHub CI after branch push.

Runtime rerun readiness conditions:

- Server-authored diff is limited to `ops/factory_control.py` and `tests/test_factory_capacity_controls.py`.
- No Agent Host files are changed.
- No frontend, Telegram, billing, FormulaLM, or model gateway files are changed.
- No runtime deploy has happened in this task.
- Local synthetic 1000 empty-poll probe reported `{"200:no_task": 1000}`.

Next runtime action after CI success:

1. Backup `/opt/kolibri-ai-platform/ops/factory_control.py`.
2. Deploy only the new `ops/factory_control.py`.
3. `python3 -m py_compile` the deployed file.
4. Restart `kolibri-factory-control.service`.
5. Verify health, fd, threads.
6. Run strict runtime canary and classify JSON manually.
7. Roll back immediately if strict gate fails.
