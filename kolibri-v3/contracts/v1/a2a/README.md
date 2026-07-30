# Kolibri Task, Assignment and A2A contracts v1

Task: `P02-T03`.

The Logical Home Control Plane is the sole logical owner of Task, attempt,
lease/fence, AgentAssignment and A2A ordering state. `worker_id` and authority
placement are execution identities, not owners; physical server names never
grant authority.

## Lease, attempt and effect semantics

- each retry creates a new immutable `attempt_id` and increments
  `attempt_number`;
- every active attempt carries one `lease_id`, authority ID/epoch and a
  monotonically increasing `fencing_token`;
- heartbeat, submit and completion must match tenant, task, attempt,
  assignment, authority epoch and fence at the owner-local store;
- an expired/stale fence cannot commit a result;
- `effect_id` is stable for the intended logical effect, so retrying an attempt
  cannot create a second canonical effect;
- terminal task states are immutable; revision creates an allowed transition
  and a new attempt.

The existing `ops/factory_control.py` queue is a producer/consumer adapter
candidate. Its current `queued/retry_scheduled/dead_letter` transport states
must map to canonical lifecycle states; it is not a second authority model.

## Duplicate and out-of-order A2A delivery

Delivery is evaluated per `(tenant_id, channel_id)`:

1. invalid schema, tenant/channel mismatch or an expired message is rejected;
2. an already accepted `a2a_message_id` with the same content hash is
   `duplicate_noop`; a different hash is `rejected_conflict`;
3. a reused `deduplication_key` with the same message/hash is
   `duplicate_noop`; any other value is `rejected_conflict`;
4. `sequence == last_sequence + 1` and the exact previous message ID is
   `accepted`;
5. a higher sequence is `deferred_out_of_order` and creates no canonical
   effect;
6. an old, unknown sequence or wrong predecessor is rejected;
7. A2A content is always `untrusted_content` and cannot add capabilities,
   authority or tools.

The full event envelope binds the sender actor/authority, tenant/goal/case/task,
trace, aggregate version and producer owner. The owner-local consumer must also
verify active sender/recipient assignments and recipient capability.

## Producer and consumer boundary fixtures

- producer fixtures are the full task transition command and A2A event under
  `tasks/examples/valid-task-transition-command.json` and
  `a2a/examples/valid-message-event.json`;
- AgentAssignment lifecycle producers validate the payload of
  `agent_assignment.status_changed` against
  `agents/examples/valid-assignment-status-changed-event.json` before placing
  it in the common `kolibri.event` envelope;
- consumer fixtures are `tasks/examples/valid-owner-state.json`,
  `a2a/examples/valid-delivery-cursor.json` and both active assignments under
  `agents/examples/`;
- `validateTaskMutationAtOwner` rejects version, attempt, assignment,
  authority epoch, fence or expired-lease mismatches before a mutation;
- `validateA2AAtOwner` resolves active sender/recipient assignments, tenant and
  task scope, sender append capability, recipient capability, then applies the
  duplicate/out-of-order cursor decision.

These functions are the canonical reference boundary for adapters. Existing
runtime identifiers, timestamp/state vocabulary and the temporary missing
`lease_id` in the Home broker require an expand/migrate adapter in P03/P05;
they are not silently accepted as canonical v1 records.
