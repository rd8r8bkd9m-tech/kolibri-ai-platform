"use strict";

const fs = require("node:fs");
const path = require("node:path");

const SCHEMA_PATHS = Object.freeze([
  "../common/trace.schema.json",
  "../common/error-envelope.schema.json",
  "message-part.schema.json",
  "attachment.schema.json",
  "session.schema.json",
  "project-create-request.schema.json",
  "thread-update-request.schema.json",
  "text-run-request.schema.json",
  "product-goal-initialize-command.schema.json",
  "product-goal-initialization-status.schema.json",
  "provider-enrollment-intent-command.schema.json",
  "provider-enrollment-status.schema.json",
  "run-execute-command.schema.json",
  "run-execute-command-v1.1.schema.json",
  "run-execute-command-v1.2.schema.json",
  "run-execute-command-v1.3.schema.json",
  "run-execution-status.schema.json",
  "run-execution-status-v1.1.schema.json",
  "project.schema.json",
  "thread.schema.json",
  "message.schema.json",
  "run.schema.json",
  "run-event.schema.json",
  "delivery-cursor.schema.json",
  "interrupt.schema.json",
  "agui-projection.schema.json",
]);

const DOMAIN_CONTRACTS = Object.freeze({
  "kolibri.product.session": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/product/session.schema.json",
  }),
  "kolibri.product.project_create_request": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/product/project-create-request.schema.json",
  }),
  "kolibri.product.thread_update_request": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/product/thread-update-request.schema.json",
  }),
  "kolibri.product.text_run_request": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/product/text-run-request.schema.json",
  }),
  "kolibri.product.attachment": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/product/attachment.schema.json",
  }),
  "kolibri.product.goal.initialize.command": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/product/product-goal-initialize-command.schema.json",
  }),
  "kolibri.product.goal.initialization_status": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/product/product-goal-initialization-status.schema.json",
  }),
  "kolibri.product.provider.enrollment_intent.command": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/product/provider-enrollment-intent-command.schema.json",
  }),
  "kolibri.product.provider.enrollment_status": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/product/provider-enrollment-status.schema.json",
  }),
  "kolibri.product.run.execute.command": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/product/run-execute-command.schema.json",
  }),
  "kolibri.product.run.execute.v1_1.command": Object.freeze({
    version: "1.1",
    schema:
      "https://schemas.kolibriai.ru/v1/product/run-execute-command-v1.1.schema.json",
  }),
  "kolibri.product.run.execute.v1_2.command": Object.freeze({
    version: "1.2",
    schema:
      "https://schemas.kolibriai.ru/v1/product/run-execute-command-v1.2.schema.json",
  }),
  "kolibri.product.run.execute.v1_3.command": Object.freeze({
    version: "1.3",
    schema:
      "https://schemas.kolibriai.ru/v1/product/run-execute-command-v1.3.schema.json",
  }),
  "kolibri.product.run.execution_status": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/product/run-execution-status.schema.json",
  }),
  "kolibri.product.run.execution_status.v1_1": Object.freeze({
    version: "1.1",
    schema:
      "https://schemas.kolibriai.ru/v1/product/run-execution-status-v1.1.schema.json",
  }),
  "kolibri.product.project": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/product/project.schema.json",
  }),
  "kolibri.product.thread": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/product/thread.schema.json",
  }),
  "kolibri.product.message": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/product/message.schema.json",
  }),
  "kolibri.product.run": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/product/run.schema.json",
  }),
  "kolibri.product.run.event": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/product/run-event.schema.json",
  }),
  "kolibri.product.delivery_cursor": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/product/delivery-cursor.schema.json",
  }),
  "kolibri.product.interrupt": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/product/interrupt.schema.json",
  }),
  "kolibri.product.agui.projection": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/product/agui-projection.schema.json",
  }),
});

const FORBIDDEN_PROJECTION_KEYS = new Set([
  "chain_of_thought",
  "model",
  "provider",
  "provider_response_id",
  "raw_a2a",
  "reasoning",
  "routing",
  "thinking",
]);

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

function uniqueValues(items, key, pathValue, code, violations) {
  const seen = new Set();
  for (const item of items) {
    if (seen.has(item[key])) {
      violations.push(violation(pathValue, code));
      return;
    }
    seen.add(item[key]);
  }
}

function forbiddenProjectionPath(value, currentPath = "") {
  if (!value || typeof value !== "object") return null;
  if (Array.isArray(value)) {
    for (let index = 0; index < value.length; index += 1) {
      const found = forbiddenProjectionPath(value[index], `${currentPath}/${index}`);
      if (found) return found;
    }
    return null;
  }
  for (const [key, child] of Object.entries(value)) {
    const childPath = `${currentPath}/${key}`;
    if (FORBIDDEN_PROJECTION_KEYS.has(key.toLowerCase())) return childPath;
    const found = forbiddenProjectionPath(child, childPath);
    if (found) return found;
  }
  return null;
}

function validateProject(project) {
  const violations = [];
  if (Date.parse(project.updated_at) < Date.parse(project.created_at)) {
    violations.push(violation("/updated_at", "updated_before_created"));
  }
  if (project.status === "deleted" && project.default_thread_id !== null) {
    violations.push(violation("/default_thread_id", "deleted_project_has_default_thread"));
  }
  return violations;
}

function validateThread(thread) {
  const violations = [];
  if (Date.parse(thread.updated_at) < Date.parse(thread.created_at)) {
    violations.push(violation("/updated_at", "updated_before_created"));
  }
  if (
    thread.last_message_sequence === 0 &&
    (thread.branch_count !== 1 || thread.last_run_sequence !== 0)
  ) {
    violations.push(violation("/", "empty_thread_has_activity"));
  }
  return violations;
}

function validateMessage(message) {
  const violations = [];
  if (Date.parse(message.committed_at) < Date.parse(message.created_at)) {
    violations.push(violation("/committed_at", "committed_before_created"));
  }
  if (message.parent_message_id === message.message_id) {
    violations.push(violation("/parent_message_id", "self_parent"));
  }
  if (message.role !== "system" && message.run_id === null) {
    violations.push(violation("/run_id", "conversation_message_requires_run"));
  }
  uniqueValues(message.parts, "part_id", "/parts", "duplicate_part_id", violations);
  for (let index = 0; index < message.parts.length; index += 1) {
    const part = message.parts[index];
    if (
      ["attachment_ref", "artifact_ref"].includes(part.type) &&
      part.tenant_id !== message.tenant_id
    ) {
      violations.push(violation(`/parts/${index}/tenant_id`, "artifact_tenant_mismatch"));
    }
  }
  return violations;
}

function validateTextRunRequest(request) {
  const violations = [];
  uniqueValues(request.parts, "part_id", "/parts", "duplicate_part_id", violations);
  if (
    request.parts.length !== 1 ||
    request.parts[0].type !== "text" ||
    !["plain", "markdown"].includes(request.parts[0].format)
  ) {
    violations.push(violation("/parts", "text_run_requires_one_text_part"));
  }
  return violations;
}

function validateRunExecuteCommand(command) {
  const violations = [];
  const expectedHash = `sha256:${require("node:crypto")
    .createHash("sha256")
    .update(command.prompt, "utf8")
    .digest("hex")}`;
  if (command.prompt_hash !== expectedHash) {
    violations.push(violation("/prompt_hash", "prompt_hash_mismatch"));
  }
  return violations;
}

function validateGoalInitializeCommand(command) {
  const violations = [];
  const expectedHash = `sha256:${require("node:crypto")
    .createHash("sha256")
    .update(command.prompt, "utf8")
    .digest("hex")}`;
  if (command.prompt_hash !== expectedHash) {
    violations.push(violation("/prompt_hash", "prompt_hash_mismatch"));
  }
  return violations;
}

function validateGoalInitializationStatus(status) {
  const violations = [];
  if (status.status === "initialized") {
    if (
      !Number.isInteger(status.goal_version) ||
      status.goal_version < 1 ||
      !Number.isInteger(status.case_version) ||
      status.case_version < 1 ||
      status.error !== null
    ) {
      violations.push(violation("/", "initialized_goal_status_invalid"));
    }
  } else if (
    status.goal_version !== null ||
    status.case_version !== null ||
    status.error === null
  ) {
    violations.push(violation("/", "failed_goal_status_invalid"));
  }
  return violations;
}

function validateProviderEnrollmentStatus(status) {
  const violations = [];
  if (status.status === "connected") {
    if (
      status.last_verified_at === null ||
      status.evidence_hash === null ||
      status.error !== null
    ) {
      violations.push(
        violation("/", "connected_provider_status_invalid"),
      );
    }
  } else if (status.status === "failed") {
    if (
      status.error === null ||
      status.last_verified_at !== null ||
      status.evidence_hash !== null
    ) {
      violations.push(violation("/error", "failed_provider_error_required"));
    }
  } else if (status.error !== null) {
    violations.push(
      violation("/error", "nonfailed_provider_error_forbidden"),
    );
  }
  return violations;
}

function validateRunExecutionStatus(executionStatus) {
  const violations = [];
  const resultPresent =
    executionStatus.result_text !== null ||
    executionStatus.result_hash !== null ||
    executionStatus.evidence !== null;

  if (executionStatus.status === "succeeded") {
    if (
      typeof executionStatus.result_text !== "string" ||
      !executionStatus.result_text.trim()
    ) {
      violations.push(violation("/result_text", "succeeded_result_text_required"));
    }
    if (typeof executionStatus.result_hash !== "string") {
      violations.push(violation("/result_hash", "succeeded_result_hash_required"));
    }
    if (executionStatus.verification_status === "verified") {
      if (!executionStatus.evidence) {
        violations.push(violation("/evidence", "verified_evidence_required"));
      }
    } else if (executionStatus.verification_status === "unverified") {
      if (executionStatus.evidence !== null) {
        violations.push(violation("/evidence", "unverified_evidence_forbidden"));
      }
    } else {
      violations.push(
        violation(
          "/verification_status",
          "succeeded_verification_status_required",
        ),
      );
    }
    if (executionStatus.error !== null) {
      violations.push(violation("/error", "succeeded_error_forbidden"));
    }
  } else if (executionStatus.status === "failed") {
    if (executionStatus.verification_status !== "not_applicable") {
      violations.push(
        violation("/verification_status", "failed_verification_not_applicable"),
      );
    }
    if (resultPresent) {
      violations.push(violation("/result_text", "failed_result_forbidden"));
    }
    if (executionStatus.error === null) {
      violations.push(violation("/error", "failed_error_required"));
    }
  } else {
    if (executionStatus.verification_status !== "not_applicable") {
      violations.push(
        violation(
          "/verification_status",
          "nonterminal_verification_not_applicable",
        ),
      );
    }
    if (resultPresent || executionStatus.error !== null) {
      violations.push(violation("/", "nonterminal_payload_forbidden"));
    }
  }

  if (
    typeof executionStatus.result_text === "string" &&
    typeof executionStatus.result_hash === "string"
  ) {
    const expectedHash = `sha256:${require("node:crypto")
      .createHash("sha256")
      .update(executionStatus.result_text, "utf8")
      .digest("hex")}`;
    if (executionStatus.result_hash !== expectedHash) {
      violations.push(violation("/result_hash", "result_hash_mismatch"));
    }
  }
  if (
    executionStatus.evidence &&
    typeof executionStatus.result_hash === "string" &&
    executionStatus.evidence.content_hash !== executionStatus.result_hash
  ) {
    violations.push(violation("/evidence/content_hash", "evidence_result_hash_mismatch"));
  }
  if (
    executionStatus.error &&
    executionStatus.error.in_response_to !== executionStatus.execution_id
  ) {
    violations.push(violation("/error/in_response_to", "error_execution_mismatch"));
  }
  return violations;
}

function validateRun(run) {
  const violations = [];
  const isFinished = run.lifecycle === "finished";
  if (isFinished !== (run.outcome !== null) || isFinished !== (run.finished_at !== null)) {
    violations.push(violation("/outcome", "run_terminal_state_mismatch"));
  }
  if (
    run.finished_at !== null &&
    Date.parse(run.finished_at) < Date.parse(run.created_at)
  ) {
    violations.push(violation("/finished_at", "finished_before_created"));
  }
  if (Date.parse(run.updated_at) < Date.parse(run.created_at)) {
    violations.push(violation("/updated_at", "updated_before_created"));
  }
  if (run.retry_of_run_id !== null && run.resume_of_run_id !== null) {
    violations.push(violation("/", "run_cannot_retry_and_resume"));
  }
  if (run.retry_of_run_id === run.run_id || run.resume_of_run_id === run.run_id) {
    violations.push(violation("/", "run_cannot_reference_itself"));
  }
  if ((run.last_event_sequence === 0) !== (run.last_event_id === null)) {
    violations.push(violation("/last_event_id", "run_event_watermark_mismatch"));
  }
  if (run.outcome === "interrupt" && run.active_interrupt_ids.length === 0) {
    violations.push(violation("/active_interrupt_ids", "interrupt_outcome_requires_interrupt"));
  }
  uniqueValues(
    run.active_interrupt_ids.map((interruptId) => ({ interruptId })),
    "interruptId",
    "/active_interrupt_ids",
    "duplicate_interrupt_id",
    violations,
  );
  return violations;
}

function validateRunEvent(event) {
  const violations = [];
  if (Date.parse(event.recorded_at) < Date.parse(event.occurred_at)) {
    violations.push(violation("/recorded_at", "recorded_before_occurred"));
  }
  if (event.source_event_id === event.event_id) {
    violations.push(violation("/source_event_id", "self_causation"));
  }
  if (event.payload_schema_id !== `kolibri.product.event.${event.event_type}`) {
    violations.push(violation("/payload_schema_id", "event_payload_schema_mismatch"));
  }
  const forbiddenPath = forbiddenProjectionPath(event.payload, "/payload");
  if (forbiddenPath) {
    violations.push(violation(forbiddenPath, "unsafe_internal_payload"));
  }
  return violations;
}

function validateCursor(cursor) {
  const violations = [];
  if ((cursor.last_sequence === 0) !== (cursor.last_event_id === null)) {
    violations.push(violation("/last_event_id", "cursor_watermark_mismatch"));
  }
  return violations;
}

function validateInterrupt(interrupt) {
  const violations = [];
  if (Date.parse(interrupt.updated_at) < Date.parse(interrupt.created_at)) {
    violations.push(violation("/updated_at", "updated_before_created"));
  }
  if (Date.parse(interrupt.expires_at) <= Date.parse(interrupt.created_at)) {
    violations.push(violation("/expires_at", "interrupt_expiry_not_after_creation"));
  }
  if (
    (interrupt.state === "answered") !== (interrupt.answer_message_id !== null)
  ) {
    violations.push(violation("/answer_message_id", "interrupt_answer_state_mismatch"));
  }
  return violations;
}

function validateAguiProjection(projection) {
  const violations = [];
  const custom = projection.event_type === "CUSTOM";
  if (
    custom !== (projection.custom_schema_id !== null) ||
    custom !== (projection.custom_schema_version !== null)
  ) {
    violations.push(violation("/custom_schema_id", "custom_schema_binding_mismatch"));
  }
  const forbiddenPath = forbiddenProjectionPath(projection.payload, "/payload");
  if (forbiddenPath) {
    violations.push(violation(forbiddenPath, "unsafe_internal_projection"));
  }
  return violations;
}

function createProductChatValidator(Ajv) {
  const ajv = new Ajv({
    allErrors: true,
    jsonPointers: true,
    schemaId: "auto",
    unknownFormats: ["date-time"],
  });
  for (const relativePath of SCHEMA_PATHS) {
    ajv.addSchema(readJson(path.resolve(__dirname, relativePath)));
  }

  return function validate(value) {
    const contract = DOMAIN_CONTRACTS[value && value.schema_id];
    if (!contract || !value || value.schema_version !== contract.version) {
      return {
        ok: false,
        code: "unsupported_schema",
        violations: [violation("/schema_version", "unsupported_schema")],
      };
    }
    const schemaValidator = ajv.getSchema(contract.schema);
    if (!schemaValidator(value)) {
      return {
        ok: false,
        code: "invalid_product_chat_contract",
        violations: schemaViolations(schemaValidator.errors),
      };
    }

    let violations = [];
    if (value.schema_id === "kolibri.product.text_run_request") {
      violations = validateTextRunRequest(value);
    } else if (
      value.schema_id === "kolibri.product.goal.initialize.command"
    ) {
      violations = validateGoalInitializeCommand(value);
    } else if (
      value.schema_id === "kolibri.product.goal.initialization_status"
    ) {
      violations = validateGoalInitializationStatus(value);
    } else if (
      value.schema_id === "kolibri.product.provider.enrollment_status"
    ) {
      violations = validateProviderEnrollmentStatus(value);
    } else if (
      value.schema_id === "kolibri.product.run.execute.command"
      || value.schema_id === "kolibri.product.run.execute.v1_1.command"
      || value.schema_id === "kolibri.product.run.execute.v1_2.command"
    ) {
      violations = validateRunExecuteCommand(value);
    } else if (
      value.schema_id === "kolibri.product.run.execution_status"
      || value.schema_id === "kolibri.product.run.execution_status.v1_1"
    ) {
      violations = validateRunExecutionStatus(value);
    } else if (value.schema_id === "kolibri.product.project") {
      violations = validateProject(value);
    } else if (value.schema_id === "kolibri.product.thread") {
      violations = validateThread(value);
    } else if (value.schema_id === "kolibri.product.message") {
      violations = validateMessage(value);
    } else if (value.schema_id === "kolibri.product.run") {
      violations = validateRun(value);
    } else if (value.schema_id === "kolibri.product.run.event") {
      violations = validateRunEvent(value);
    } else if (value.schema_id === "kolibri.product.delivery_cursor") {
      violations = validateCursor(value);
    } else if (value.schema_id === "kolibri.product.interrupt") {
      violations = validateInterrupt(value);
    } else if (value.schema_id === "kolibri.product.agui.projection") {
      violations = validateAguiProjection(value);
    }
    return {
      ok: violations.length === 0,
      code: violations.length === 0 ? null : "invalid_product_chat_contract",
      violations,
    };
  };
}

function validateProductChatAtOwner(records, context) {
  const violations = [];
  const {
    project,
    thread,
    messages = [],
    runs = [],
    events = [],
    cursors = [],
    interrupts = [],
    projections = [],
  } = records;

  const scopedRecords = [
    project,
    thread,
    ...messages,
    ...runs,
    ...events,
    ...cursors,
    ...interrupts,
    ...projections,
  ].filter(Boolean);
  for (const record of scopedRecords) {
    if (record.tenant_id !== context.tenant_id) {
      violations.push(violation("/", "owner_tenant_mismatch"));
      break;
    }
  }
  if (!project || !thread || thread.project_id !== project.project_id) {
    violations.push(violation("/thread/project_id", "thread_project_mismatch"));
  }

  uniqueValues(messages, "message_id", "/messages", "duplicate_message_id", violations);
  uniqueValues(messages, "sequence", "/messages", "duplicate_message_sequence", violations);
  const messageById = new Map(messages.map((message) => [message.message_id, message]));
  for (const message of messages) {
    if (message.thread_id !== thread.thread_id || message.project_id !== project.project_id) {
      violations.push(violation("/messages", "message_scope_mismatch"));
    }
    if (message.parent_message_id !== null) {
      const parent = messageById.get(message.parent_message_id);
      if (!parent || parent.sequence >= message.sequence) {
        violations.push(violation("/messages", "message_parent_not_prior"));
      }
    }
  }

  uniqueValues(runs, "run_id", "/runs", "duplicate_run_id", violations);
  uniqueValues(runs, "run_sequence", "/runs", "duplicate_run_sequence", violations);
  const runById = new Map(runs.map((run) => [run.run_id, run]));
  for (const run of runs) {
    const input = messageById.get(run.input_message_id);
    if (
      run.thread_id !== thread.thread_id ||
      run.project_id !== project.project_id ||
      !input ||
      input.role !== "user"
    ) {
      violations.push(violation("/runs", "run_input_or_scope_mismatch"));
    }
  }

  uniqueValues(events, "event_id", "/events", "duplicate_event_id", violations);
  for (const run of runs) {
    const runEvents = events
      .filter((event) => event.run_id === run.run_id)
      .sort((left, right) => left.sequence - right.sequence);
    for (let index = 0; index < runEvents.length; index += 1) {
      if (runEvents[index].sequence !== index + 1) {
        violations.push(violation("/events", "non_contiguous_event_sequence"));
        break;
      }
    }
    const last = runEvents.at(-1);
    if (
      last &&
      (last.sequence !== run.last_event_sequence || last.event_id !== run.last_event_id)
    ) {
      violations.push(violation("/runs", "run_event_watermark_not_bound"));
    }
  }

  const eventById = new Map(events.map((event) => [event.event_id, event]));
  for (const cursor of cursors) {
    const event = cursor.last_event_id ? eventById.get(cursor.last_event_id) : null;
    if (
      !runById.has(cursor.run_id) ||
      (cursor.last_sequence > 0 &&
        (!event ||
          event.run_id !== cursor.run_id ||
          event.sequence !== cursor.last_sequence))
    ) {
      violations.push(violation("/cursors", "cursor_event_not_bound"));
    }
  }

  const interruptById = new Map(
    interrupts.map((interrupt) => [interrupt.interrupt_id, interrupt]),
  );
  for (const run of runs) {
    for (const interruptId of run.active_interrupt_ids) {
      const interrupt = interruptById.get(interruptId);
      if (!interrupt || interrupt.run_id !== run.run_id || interrupt.state !== "pending") {
        violations.push(violation("/runs", "active_interrupt_not_bound"));
      }
    }
  }
  for (const projection of projections) {
    const event = eventById.get(projection.source_event_id);
    if (
      !event ||
      event.run_id !== projection.run_id ||
      event.sequence !== projection.source_sequence
    ) {
      violations.push(violation("/projections", "projection_source_not_bound"));
    }
  }

  return {
    ok: violations.length === 0,
    code: violations.length === 0 ? "accepted" : "rejected_owner_context",
    violations,
  };
}

module.exports = {
  DOMAIN_CONTRACTS,
  createProductChatValidator,
  validateProductChatAtOwner,
};
