# Next

Immediate actions:

1. Deploy the updated `ops/factory_control.py` with the dead letter rerun
   endpoints to the live Control Plane.
2. Verify the new endpoints:
   - `GET /v1/tasks/dead-letter` returns the dead letter queue.
   - `POST /v1/tasks/{task_id}/rerun` re-queues the task.
3. If the original task objective is still needed, rerun through the Fabric API
   or resubmit with a longer lease duration.

Follow-up tasks:

- Increase `FACTORY_LEASE_DURATION` (env or default) if workloads regularly
  exceed the 60-second default.
- Add dead letter alerting to the Telegram gateway so the owner is notified
  when tasks enter `dead_letter` state.
- Consider adding `attempt_history` tracking to dead letter reruns so the
  full failure chain is visible in the task record.
