"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const {
  canonicalize,
  createCommonEnvelopeValidator,
} = require("../common/validator.cjs");

const DOMAIN_SCHEMAS = Object.freeze([
  "../tasks/task.schema.json",
  "../tasks/task-graph.schema.json",
  "../tasks/task-graph-apply.schema.json",
  "../tasks/task-graph-change-event.schema.json",
  "../tasks/task-transition.schema.json",
  "../tasks/lease.schema.json",
  "../tasks/attempt.schema.json",
  "../tasks/owner-state.schema.json",
  "../agents/authority-profile.schema.json",
  "../agents/agent-card.schema.json",
  "../agents/assignment.schema.json",
  "message.schema.json",
  "delivery-cursor.schema.json",
]);

const DOMAIN_CONTRACTS = Object.freeze({
  "kolibri.task": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/tasks/task.schema.json",
  }),
  "kolibri.task_graph": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/tasks/task-graph.schema.json",
  }),
  "kolibri.task_graph.apply.command": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/tasks/task-graph-apply.schema.json",
  }),
  "kolibri.task_graph.changed.event": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/tasks/task-graph-change-event.schema.json",
  }),
  "kolibri.task.transition.command": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/tasks/task-transition.schema.json",
  }),
  "kolibri.task_attempt": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/tasks/attempt.schema.json",
  }),
  "kolibri.task_owner_state": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/tasks/owner-state.schema.json",
  }),
  "kolibri.agent_card": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/agents/agent-card.schema.json",
  }),
  "kolibri.agent_assignment": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/agents/assignment.schema.json",
  }),
  "kolibri.a2a.message_appended.event": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/a2a/message.schema.json",
  }),
  "kolibri.a2a.delivery_cursor": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/a2a/delivery-cursor.schema.json",
  }),
});

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function violation(pathValue, code) {
  return { path: pathValue, code };
}

function schemaViolations(errors) {
  return (errors || []).map((error) => ({
    path:
      error.keyword === "additionalProperties"
        ? `${error.dataPath || ""}/${error.params.additionalProperty}`
        : error.keyword === "required"
          ? `${error.dataPath || ""}/${error.params.missingProperty}`
          : error.dataPath || "/",
    code: error.keyword,
  }));
}

function uniqueIds(items, key, pathValue, violations) {
  const seen = new Set();
  for (const item of items) {
    if (seen.has(item[key])) {
      violations.push(violation(pathValue, "duplicate_register_id"));
    }
    seen.add(item[key]);
  }
}

function assertMachine(machine, schemaStates) {
  if (
    !machine ||
    machine.schema_id !== "kolibri.task.transitions" ||
    machine.schema_version !== "1.0"
  ) {
    throw new Error("invalid task state machine identity");
  }
  const states = Object.keys(machine.allowed).sort();
  const declared = [...schemaStates].sort();
  if (JSON.stringify(states) !== JSON.stringify(declared)) {
    throw new Error("task state machine/schema drift");
  }
  for (const [state, targets] of Object.entries(machine.allowed)) {
    if (targets.length === 0 && !machine.terminal_states.includes(state)) {
      throw new Error(`dead-end task state is not terminal: ${state}`);
    }
    if (targets.length > 0 && machine.terminal_states.includes(state)) {
      throw new Error(`terminal task state has outgoing transition: ${state}`);
    }
    for (const target of targets) {
      if (!states.includes(target)) {
        throw new Error(`task transition targets unknown state: ${target}`);
      }
    }
  }
}

function validateTask(task) {
  const violations = [];
  if (task.parent_task_id === task.task_id) {
    violations.push(violation("/parent_task_id", "self_parent"));
  }
  if (task.dependency_task_ids.includes(task.task_id)) {
    violations.push(
      violation("/dependency_task_ids", "self_dependency"),
    );
  }
  uniqueIds(
    task.acceptance_criteria,
    "criterion_id",
    "/acceptance_criteria",
    violations,
  );
  uniqueIds(
    task.expected_outputs,
    "output_id",
    "/expected_outputs",
    violations,
  );
  if (Date.parse(task.updated_at) < Date.parse(task.created_at)) {
    violations.push(violation("/updated_at", "updated_before_created"));
  }
  return violations;
}

function topologicalOrder(taskIds, prerequisites) {
  const incoming = new Map(
    taskIds.map((taskId) => [
      taskId,
      new Set(prerequisites.get(taskId) || []),
    ]),
  );
  const dependents = new Map(taskIds.map((taskId) => [taskId, new Set()]));
  for (const [taskId, requiredIds] of incoming.entries()) {
    for (const requiredId of requiredIds) {
      dependents.get(requiredId)?.add(taskId);
    }
  }
  const frontier = taskIds
    .filter((taskId) => incoming.get(taskId).size === 0)
    .sort();
  const ordered = [];
  while (frontier.length > 0) {
    const taskId = frontier.shift();
    ordered.push(taskId);
    for (const dependentId of [...dependents.get(taskId)].sort()) {
      incoming.get(dependentId).delete(taskId);
      if (
        incoming.get(dependentId).size === 0 &&
        !ordered.includes(dependentId) &&
        !frontier.includes(dependentId)
      ) {
        frontier.push(dependentId);
        frontier.sort();
      }
    }
  }
  return ordered.length === taskIds.length ? ordered : null;
}

function taskGraphProjection(tasks, scope, graphVersion) {
  const violations = [];
  const byId = new Map();
  for (const task of tasks) {
    if (byId.has(task.task_id)) {
      violations.push(violation("/tasks", "duplicate_task_id"));
    }
    byId.set(task.task_id, task);
    for (const field of ["tenant_id", "goal_id", "case_id"]) {
      if (task[field] !== scope[field]) {
        violations.push(violation(`/tasks/${task.task_id}/${field}`, "scope"));
      }
    }
    if (task.graph_version !== graphVersion) {
      violations.push(
        violation(`/tasks/${task.task_id}/graph_version`, "graph_version"),
      );
    }
    violations.push(
      ...validateTask(task).map((item) => ({
        path: `/tasks/${task.task_id}${item.path === "/" ? "" : item.path}`,
        code: item.code,
      })),
    );
  }
  const taskIds = [...byId.keys()].sort();
  const taskIdSet = new Set(taskIds);
  const parents = new Map();
  const dependencies = new Map();
  for (const [taskId, task] of byId.entries()) {
    const parentIds = task.parent_task_id === null ||
      task.parent_task_id === undefined
      ? []
      : [task.parent_task_id];
    parents.set(taskId, new Set(parentIds));
    dependencies.set(taskId, new Set(task.dependency_task_ids));
    for (const parentId of parentIds) {
      if (!taskIdSet.has(parentId)) {
        violations.push(
          violation(`/tasks/${taskId}/parent_task_id`, "parent_not_found"),
        );
      }
    }
    for (const dependencyId of task.dependency_task_ids) {
      if (!taskIdSet.has(dependencyId)) {
        violations.push(
          violation(
            `/tasks/${taskId}/dependency_task_ids`,
            "dependency_not_found",
          ),
        );
      }
    }
  }
  if (violations.length > 0) {
    return { violations };
  }
  if (topologicalOrder(taskIds, parents) === null) {
    violations.push(violation("/tasks", "parent_cycle"));
  }
  const topologicalTaskIds = topologicalOrder(taskIds, dependencies);
  if (topologicalTaskIds === null) {
    violations.push(violation("/tasks", "dependency_cycle"));
    return { violations };
  }

  const children = new Map(taskIds.map((taskId) => [taskId, []]));
  const dependents = new Map(taskIds.map((taskId) => [taskId, []]));
  for (const [taskId, parentIds] of parents.entries()) {
    for (const parentId of parentIds) {
      children.get(parentId).push(taskId);
    }
  }
  for (const [taskId, dependencyIds] of dependencies.entries()) {
    for (const dependencyId of dependencyIds) {
      dependents.get(dependencyId).push(taskId);
    }
  }
  const relations = [];
  const runnableTaskIds = [];
  for (const taskId of taskIds) {
    const task = byId.get(taskId);
    const blockedByTaskIds = [...dependencies.get(taskId)]
      .filter((dependencyId) => byId.get(dependencyId).state !== "completed")
      .sort();
    if (
      ["ready", "completed"].includes(task.state) &&
      blockedByTaskIds.length > 0
    ) {
      violations.push(
        violation(`/tasks/${taskId}/state`, "unmet_dependencies"),
      );
    }
    const runnable =
      task.state === "ready" &&
      blockedByTaskIds.length === 0 &&
      task.current_attempt_id === null &&
      task.current_assignment_id === null;
    if (runnable) {
      runnableTaskIds.push(taskId);
    }
    relations.push({
      task_id: taskId,
      parent_task_id: task.parent_task_id ?? null,
      child_task_ids: children.get(taskId).sort(),
      dependency_task_ids: [...dependencies.get(taskId)].sort(),
      dependent_task_ids: dependents.get(taskId).sort(),
      blocked_by_task_ids: blockedByTaskIds,
      runnable,
    });
  }
  return {
    violations,
    topologicalTaskIds,
    runnableTaskIds,
    relations,
  };
}

function validateTaskGraph(graph) {
  const projection = taskGraphProjection(
    graph.tasks,
    graph,
    graph.graph_version,
  );
  const violations = [...projection.violations];
  for (const [pathValue, actual, expected] of [
    ["/topological_task_ids", graph.topological_task_ids, projection.topologicalTaskIds],
    ["/runnable_task_ids", graph.runnable_task_ids, projection.runnableTaskIds],
    ["/relations", graph.relations, projection.relations],
  ]) {
    if (
      expected !== undefined &&
      JSON.stringify(actual) !== JSON.stringify(expected)
    ) {
      violations.push(violation(pathValue, "derived_projection_mismatch"));
    }
  }
  if (Date.parse(graph.updated_at) < Date.parse(graph.created_at)) {
    violations.push(violation("/updated_at", "updated_before_created"));
  }
  return violations;
}

function validateTaskGraphApply(command) {
  const violations = [];
  if (
    command.next_graph_version !== command.expected_graph_version + 1
  ) {
    violations.push(
      violation("/next_graph_version", "non_monotonic_version"),
    );
  }
  const projection = taskGraphProjection(
    command.tasks,
    command,
    command.next_graph_version,
  );
  violations.push(...projection.violations);
  if (command.expected_graph_version === 0) {
    for (const task of command.tasks) {
      if (task.state !== "proposed") {
        violations.push(
          violation(
            `/tasks/${task.task_id}/state`,
            "new_task_state_must_be_proposed",
          ),
        );
      }
      if (
        task.current_attempt_id !== null ||
        task.current_assignment_id !== null
      ) {
        violations.push(
          violation(
            `/tasks/${task.task_id}`,
            "new_task_execution_identity_forbidden",
          ),
        );
      }
    }
  }
  return violations;
}

function validateTaskGraphEvent(event) {
  const violations = [];
  if (
    event.previous_graph_version === null
      ? event.new_graph_version !== 1
      : event.new_graph_version !== event.previous_graph_version + 1
  ) {
    violations.push(
      violation("/new_graph_version", "non_monotonic_version"),
    );
  }
  return violations;
}

function validateTaskTransition(transition, machine) {
  const violations = [];
  if (transition.next_version !== transition.expected_version + 1) {
    violations.push(violation("/next_version", "non_monotonic_version"));
  }
  const allowed = machine.allowed[transition.from_status] || [];
  if (!allowed.includes(transition.to_status)) {
    violations.push(violation("/to_status", "transition_not_allowed"));
  }
  const fencedStates = new Set([
    "leased",
    "running",
    "submitted",
    "verifying",
    "completed",
    "failed_retryable",
    "failed_terminal",
  ]);
  if (
    fencedStates.has(transition.from_status) ||
    fencedStates.has(transition.to_status)
  ) {
    for (const key of [
      "attempt_id",
      "assignment_id",
      "lease_id",
      "fencing_token",
    ]) {
      if (transition[key] === null) {
        violations.push(violation(`/${key}`, "active_fence_required"));
      }
    }
  }
  return violations;
}

function validateAttempt(attempt) {
  const violations = [];
  const lease = attempt.lease;
  if (
    Date.parse(lease.heartbeat_at) < Date.parse(lease.acquired_at) ||
    Date.parse(lease.expires_at) <= Date.parse(lease.heartbeat_at)
  ) {
    violations.push(violation("/lease", "invalid_lease_time_order"));
  }
  const failureStates = new Set([
    "failed_retryable",
    "failed_terminal",
    "expired",
  ]);
  if (failureStates.has(attempt.status) !== (attempt.error !== null)) {
    violations.push(violation("/error", "attempt_error_state_mismatch"));
  }
  return violations;
}

function validateAssignment(assignment) {
  const violations = [];
  if (
    !assignment.authority_profile.allowed_resource_refs.includes(
      assignment.task_id,
    ) ||
    !assignment.authority_profile.allowed_resource_refs.includes(
      assignment.case_id,
    )
  ) {
    violations.push(
      violation(
        "/authority_profile/allowed_resource_refs",
        "assignment_scope_missing",
      ),
    );
  }
  if (
    Date.parse(assignment.updated_at) < Date.parse(assignment.created_at) ||
    Date.parse(assignment.deadline_at) <= Date.parse(assignment.created_at) ||
    Date.parse(assignment.authority_profile.expires_at) <
      Date.parse(assignment.deadline_at)
  ) {
    violations.push(violation("/deadline_at", "invalid_assignment_time_order"));
  }
  return violations;
}

function validateOwnerState(state) {
  const violations = [];
  if (state.current_attempt_id === state.current_assignment_id) {
    violations.push(violation("/", "owner_state_identity_collision"));
  }
  return violations;
}

function validateDeliveryCursor(cursor) {
  const violations = [];
  if (
    (cursor.last_sequence === 0 && cursor.last_message_id !== null) ||
    (cursor.last_sequence > 0 && cursor.last_message_id === null)
  ) {
    violations.push(
      violation("/last_message_id", "cursor_sequence_identity_mismatch"),
    );
  }
  return violations;
}

function canonicalA2AContent(message) {
  return {
    tenant_id: message.tenant_id,
    goal_id: message.goal_id,
    case_id: message.case_id,
    task_id: message.task_id,
    task_version: message.task_version,
    channel_id: message.channel_id,
    sequence: message.sequence,
    previous_message_id: message.previous_message_id,
    sender_actor_id: message.sender_actor_id,
    sender_assignment_id: message.sender_assignment_id,
    recipient_assignment_ids: message.recipient_assignment_ids,
    recipient_capability: message.recipient_capability,
    message_type: message.message_type,
    purpose: message.purpose,
    response_to_message_id: message.response_to_message_id,
    content: message.content,
  };
}

function a2aContentHash(message) {
  return `sha256:${crypto
    .createHash("sha256")
    .update(canonicalize(canonicalA2AContent(message)), "utf8")
    .digest("hex")}`;
}

function validateMessage(message) {
  const violations = [];
  if (message.content_hash !== a2aContentHash(message)) {
    violations.push(violation("/content_hash", "content_hash_mismatch"));
  }
  if (Date.parse(message.expires_at) <= Date.parse(message.sent_at)) {
    violations.push(violation("/expires_at", "message_expiry_not_after_send"));
  }
  return violations;
}

function createTaskA2AValidator(Ajv, a2aDir = __dirname) {
  const ajv = new Ajv({ allErrors: true, jsonPointers: true });
  const schemas = new Map();
  for (const relativePath of DOMAIN_SCHEMAS) {
    const schema = readJson(path.resolve(a2aDir, relativePath));
    schemas.set(relativePath, schema);
    ajv.addSchema(schema);
  }
  const taskMachine = readJson(
    path.resolve(a2aDir, "../tasks/task-transitions.json"),
  );
  assertMachine(
    taskMachine,
    schemas.get("../tasks/task.schema.json").definitions.status.enum,
  );

  return function validateTaskA2A(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      return { ok: false, code: "invalid_domain_contract", violations: [] };
    }
    const contract = DOMAIN_CONTRACTS[value.schema_id];
    if (!contract || value.schema_version !== contract.version) {
      return { ok: false, code: "unsupported_schema", violations: [] };
    }
    const validate = ajv.getSchema(contract.schema);
    if (!validate(value)) {
      return {
        ok: false,
        code: "invalid_domain_contract",
        violations: schemaViolations(validate.errors),
      };
    }
    let violations = [];
    if (value.schema_id === "kolibri.task") {
      violations = validateTask(value);
    } else if (value.schema_id === "kolibri.task_graph") {
      violations = validateTaskGraph(value);
    } else if (value.schema_id === "kolibri.task_graph.apply.command") {
      violations = validateTaskGraphApply(value);
    } else if (value.schema_id === "kolibri.task_graph.changed.event") {
      violations = validateTaskGraphEvent(value);
    } else if (value.schema_id === "kolibri.task.transition.command") {
      violations = validateTaskTransition(value, taskMachine);
    } else if (value.schema_id === "kolibri.task_attempt") {
      violations = validateAttempt(value);
    } else if (value.schema_id === "kolibri.task_owner_state") {
      violations = validateOwnerState(value);
    } else if (value.schema_id === "kolibri.agent_assignment") {
      violations = validateAssignment(value);
    } else if (value.schema_id === "kolibri.a2a.message_appended.event") {
      violations = validateMessage(value);
    } else if (value.schema_id === "kolibri.a2a.delivery_cursor") {
      violations = validateDeliveryCursor(value);
    }
    return violations.length
      ? { ok: false, code: "invalid_domain_contract", violations }
      : { ok: true, code: null, violations: [] };
  };
}

function classifyA2ADelivery(message, cursor, now, validateDomain) {
  const messageResult = validateDomain(message);
  const cursorResult = validateDomain(cursor);
  if (!messageResult.ok || !cursorResult.ok) {
    return {
      decision: "rejected_invalid",
      code: !messageResult.ok ? messageResult.code : cursorResult.code,
    };
  }
  if (
    message.tenant_id !== cursor.tenant_id ||
    message.channel_id !== cursor.channel_id
  ) {
    return { decision: "rejected_scope", code: "cursor_scope_mismatch" };
  }
  if (Date.parse(message.expires_at) <= Date.parse(now)) {
    return { decision: "rejected_expired", code: "message_expired" };
  }
  const acceptedHash = cursor.accepted_messages[message.a2a_message_id];
  if (acceptedHash !== undefined) {
    return acceptedHash === message.content_hash
      ? { decision: "duplicate_noop", code: null }
      : { decision: "rejected_conflict", code: "message_id_hash_conflict" };
  }
  const deduplicated = cursor.deduplication_index[message.deduplication_key];
  if (deduplicated !== undefined) {
    return deduplicated.message_id === message.a2a_message_id &&
      deduplicated.content_hash === message.content_hash
      ? { decision: "duplicate_noop", code: null }
      : {
          decision: "rejected_conflict",
          code: "deduplication_key_conflict",
        };
  }
  if (message.sequence > cursor.last_sequence + 1) {
    return {
      decision: "deferred_out_of_order",
      code: "sequence_gap",
    };
  }
  if (message.sequence <= cursor.last_sequence) {
    return {
      decision: "rejected_out_of_order",
      code: "unknown_old_sequence",
    };
  }
  if (message.previous_message_id !== cursor.last_message_id) {
    return {
      decision: "rejected_out_of_order",
      code: "previous_message_mismatch",
    };
  }
  return { decision: "accepted", code: null };
}

function createA2AEventValidator(
  Ajv,
  a2aDir = __dirname,
  commonDir = path.resolve(a2aDir, "../common"),
) {
  const validateEnvelope = createCommonEnvelopeValidator(Ajv, commonDir);
  const validateDomain = createTaskA2AValidator(Ajv, a2aDir);

  return function validateA2AEvent(envelope) {
    const envelopeResult = validateEnvelope(envelope);
    if (!envelopeResult.ok) {
      return envelopeResult;
    }
    const violations = [];
    const expected = {
      event_name: "a2a.message_appended",
      payload_schema_id: "kolibri.a2a.message_appended.event",
      payload_schema_version: "1.0",
      producer_owner: "logical_home_control_plane",
    };
    for (const [key, value] of Object.entries(expected)) {
      if (envelope[key] !== value) {
        violations.push(violation(`/${key}`, "incorrect_a2a_envelope"));
      }
    }
    if (
      envelope.identity.authority.authority_role !==
        "logical_home_control_plane"
    ) {
      violations.push(
        violation(
          "/identity/authority/authority_role",
          "incorrect_authority_role",
        ),
      );
    }
    if (
      !envelope.identity.authority.capabilities.includes("a2a.message.append")
    ) {
      violations.push(
        violation(
          "/identity/authority/capabilities",
          "required_capability_missing",
        ),
      );
    }
    const payload = envelope.payload;
    const bindings = [
      ["tenant_id", envelope.identity.tenant_id],
      ["goal_id", envelope.identity.subject_refs.goal_id],
      ["case_id", envelope.identity.subject_refs.case_id],
      ["task_id", envelope.identity.subject_refs.task_id],
      ["sender_actor_id", envelope.identity.actor.actor_id],
    ];
    for (const [key, expectedValue] of bindings) {
      if (payload[key] !== expectedValue) {
        violations.push(
          violation(`/payload/${key}`, "identity_binding_mismatch"),
        );
      }
    }
    if (
      envelope.aggregate.aggregate_type !== "task" ||
      envelope.aggregate.aggregate_id !== payload.task_id ||
      envelope.aggregate.aggregate_version !== payload.task_version
    ) {
      violations.push(
        violation("/aggregate", "task_aggregate_binding_mismatch"),
      );
    }
    if (envelope.deduplication_key !== payload.deduplication_key) {
      violations.push(
        violation("/deduplication_key", "deduplication_binding_mismatch"),
      );
    }
    const domainResult = validateDomain(payload);
    if (!domainResult.ok) {
      violations.push(
        ...domainResult.violations.map((item) => ({
          path: `/payload${item.path === "/" ? "" : item.path}`,
          code: item.code,
        })),
      );
      if (domainResult.code === "unsupported_schema") {
        violations.push(
          violation("/payload/schema_version", "unsupported_payload_schema"),
        );
      }
    }
    return violations.length
      ? { ok: false, code: "invalid_a2a_event", violations }
      : { ok: true, code: null, violations: [] };
  };
}

function createTaskCommandValidator(
  Ajv,
  a2aDir = __dirname,
  commonDir = path.resolve(a2aDir, "../common"),
) {
  const validateEnvelope = createCommonEnvelopeValidator(Ajv, commonDir);
  const validateDomain = createTaskA2AValidator(Ajv, a2aDir);

  return function validateTaskCommand(envelope) {
    const envelopeResult = validateEnvelope(envelope);
    if (!envelopeResult.ok) {
      return envelopeResult;
    }
    const violations = [];
    const expected = {
      command_name: "task.transition",
      payload_schema_id: "kolibri.task.transition.command",
      payload_schema_version: "1.0",
      target_owner: "logical_home_control_plane",
    };
    for (const [key, value] of Object.entries(expected)) {
      if (envelope[key] !== value) {
        violations.push(violation(`/${key}`, "incorrect_task_envelope"));
      }
    }
    if (
      envelope.identity.authority.authority_role !==
        "logical_home_control_plane"
    ) {
      violations.push(
        violation(
          "/identity/authority/authority_role",
          "incorrect_authority_role",
        ),
      );
    }
    if (
      !envelope.identity.authority.capabilities.includes("task.transition")
    ) {
      violations.push(
        violation(
          "/identity/authority/capabilities",
          "required_capability_missing",
        ),
      );
    }
    if (envelope.payload.task_id !== envelope.identity.subject_refs.task_id) {
      violations.push(
        violation("/payload/task_id", "identity_binding_mismatch"),
      );
    }
    if (
      envelope.idempotency.scope !== "task" ||
      envelope.idempotency.scope_id !== envelope.payload.task_id
    ) {
      violations.push(
        violation("/idempotency", "task_idempotency_scope_mismatch"),
      );
    }
    const domainResult = validateDomain(envelope.payload);
    if (!domainResult.ok) {
      violations.push(
        ...domainResult.violations.map((item) => ({
          path: `/payload${item.path === "/" ? "" : item.path}`,
          code: item.code,
        })),
      );
      if (domainResult.code === "unsupported_schema") {
        violations.push(
          violation("/payload/schema_version", "unsupported_payload_schema"),
        );
      }
    }
    return violations.length
      ? { ok: false, code: "invalid_task_command", violations }
      : { ok: true, code: null, violations: [] };
  };
}

function validateTaskMutationAtOwner(
  envelope,
  ownerState,
  now,
  validateCommand,
  validateDomain,
) {
  const commandResult = validateCommand(envelope);
  const stateResult = validateDomain(ownerState);
  if (!commandResult.ok || !stateResult.ok) {
    return {
      ok: false,
      code: !commandResult.ok ? commandResult.code : stateResult.code,
      violations: !commandResult.ok
        ? commandResult.violations
        : stateResult.violations,
    };
  }
  const payload = envelope.payload;
  const violations = [];
  const bindings = [
    ["/identity/tenant_id", envelope.identity.tenant_id, ownerState.tenant_id],
    ["/payload/task_id", payload.task_id, ownerState.task_id],
    ["/payload/expected_version", payload.expected_version, ownerState.task_version],
    ["/payload/from_status", payload.from_status, ownerState.current_status],
    ["/payload/attempt_id", payload.attempt_id, ownerState.current_attempt_id],
    ["/payload/assignment_id", payload.assignment_id, ownerState.current_assignment_id],
    ["/payload/lease_id", payload.lease_id, ownerState.lease_id],
    ["/payload/fencing_token", payload.fencing_token, ownerState.fencing_token],
    [
      "/identity/authority/authority_id",
      envelope.identity.authority.authority_id,
      ownerState.authority_id,
    ],
    [
      "/identity/authority/authority_epoch",
      envelope.identity.authority.authority_epoch,
      ownerState.authority_epoch,
    ],
  ];
  for (const [pathValue, actual, expected] of bindings) {
    if (actual !== expected) {
      violations.push(violation(pathValue, "owner_state_binding_mismatch"));
    }
  }
  if (Date.parse(ownerState.lease_expires_at) <= Date.parse(now)) {
    violations.push(violation("/lease_expires_at", "lease_expired"));
  }
  return violations.length
    ? { ok: false, code: "rejected_stale_fence", violations }
    : { ok: true, code: null, violations: [] };
}

function validateA2AAtOwner(
  envelope,
  cursor,
  assignments,
  now,
  validateEvent,
  validateDomain,
) {
  const eventResult = validateEvent(envelope);
  if (!eventResult.ok) {
    return eventResult;
  }
  const payload = envelope.payload;
  const assignmentById = new Map();
  const violations = [];
  for (const assignment of assignments) {
    const result = validateDomain(assignment);
    if (!result.ok) {
      violations.push(
        ...result.violations.map((item) => ({
          path: `/assignments${item.path}`,
          code: item.code,
        })),
      );
      continue;
    }
    assignmentById.set(assignment.assignment_id, assignment);
  }
  const sender = assignmentById.get(payload.sender_assignment_id);
  if (
    !sender ||
    sender.status !== "active" ||
    sender.assignee_actor_id !== payload.sender_actor_id ||
    sender.tenant_id !== payload.tenant_id ||
    sender.goal_id !== payload.goal_id ||
    sender.case_id !== payload.case_id ||
    sender.task_id !== payload.task_id ||
    sender.task_version !== payload.task_version ||
    sender.authority_profile.authority_id !==
      envelope.identity.authority.authority_id ||
    sender.authority_profile.authority_epoch !==
      envelope.identity.authority.authority_epoch ||
    Date.parse(sender.authority_profile.expires_at) <= Date.parse(now) ||
    !sender.authority_profile.capabilities.includes("a2a.message.append")
  ) {
    violations.push(
      violation("/payload/sender_assignment_id", "sender_assignment_invalid"),
    );
  }
  for (const assignmentId of payload.recipient_assignment_ids) {
    const recipient = assignmentById.get(assignmentId);
    if (
      !recipient ||
      recipient.status !== "active" ||
      recipient.tenant_id !== payload.tenant_id ||
      recipient.goal_id !== payload.goal_id ||
      recipient.case_id !== payload.case_id ||
      recipient.task_id !== payload.task_id ||
      recipient.task_version !== payload.task_version ||
      recipient.authority_profile.authority_id !==
        envelope.identity.authority.authority_id ||
      recipient.authority_profile.authority_epoch !==
        envelope.identity.authority.authority_epoch ||
      Date.parse(recipient.authority_profile.expires_at) <= Date.parse(now) ||
      (payload.recipient_capability !== null &&
        !recipient.authority_profile.capabilities.includes(
          payload.recipient_capability,
        ))
    ) {
      violations.push(
        violation(
          "/payload/recipient_assignment_ids",
          "recipient_assignment_invalid",
        ),
      );
    }
  }
  const delivery = classifyA2ADelivery(payload, cursor, now, validateDomain);
  if (delivery.decision !== "accepted" && delivery.decision !== "duplicate_noop") {
    violations.push(
      violation("/payload/sequence", `delivery_${delivery.decision}`),
    );
  }
  return violations.length
    ? { ok: false, code: "rejected_owner_context", violations }
    : { ok: true, code: delivery.decision, violations: [] };
}

module.exports = {
  DOMAIN_CONTRACTS,
  DOMAIN_SCHEMAS,
  a2aContentHash,
  canonicalA2AContent,
  classifyA2ADelivery,
  validateA2AAtOwner,
  validateTaskMutationAtOwner,
  createA2AEventValidator,
  createTaskCommandValidator,
  createTaskA2AValidator,
};
