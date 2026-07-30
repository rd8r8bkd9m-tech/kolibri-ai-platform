"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

const SCHEMA_FILES = Object.freeze([
  "identity.schema.json",
  "trace.schema.json",
  "idempotency.schema.json",
  "command-envelope.schema.json",
  "event-envelope.schema.json",
  "error-envelope.schema.json",
]);

const ENVELOPES = Object.freeze({
  "kolibri.command": Object.freeze({
    version: "1.0",
    file: "command-envelope.schema.json",
  }),
  "kolibri.event": Object.freeze({
    version: "1.0",
    file: "event-envelope.schema.json",
  }),
  "kolibri.error": Object.freeze({
    version: "1.0",
    file: "error-envelope.schema.json",
  }),
});

function loadCommonSchemas(Ajv, contractDir = __dirname) {
  const ajv = new Ajv({ allErrors: true, jsonPointers: true });
  for (const name of SCHEMA_FILES) {
    ajv.addSchema(
      JSON.parse(fs.readFileSync(path.join(contractDir, name), "utf8")),
    );
  }
  return ajv;
}

function validationFailure(code, violations = []) {
  return Object.freeze({ ok: false, code, violations });
}

function assertValidUnicode(value) {
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) {
        throw new TypeError("canonical JSON rejects lone high surrogate");
      }
      index += 1;
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      throw new TypeError("canonical JSON rejects lone low surrogate");
    }
  }
}

function canonicalize(value) {
  if (value === null || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (typeof value === "string") {
    assertValidUnicode(value);
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new TypeError("canonical JSON does not support non-finite numbers");
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalize).join(",")}]`;
  }
  if (typeof value === "object") {
    const keys = Object.keys(value);
    keys.forEach(assertValidUnicode);
    return `{${keys
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalize(value[key])}`)
      .join(",")}}`;
  }
  throw new TypeError(`unsupported canonical JSON type: ${typeof value}`);
}

function canonicalEffect(command) {
  return {
    schema_id: command.schema_id,
    schema_version: command.schema_version,
    command_name: command.command_name,
    payload_schema_id: command.payload_schema_id,
    payload_schema_version: command.payload_schema_version,
    target_owner: command.target_owner,
    tenant_id: command.identity.tenant_id,
    user_id: command.identity.user_id,
    actor: command.identity.actor,
    subject_refs: command.identity.subject_refs,
    idempotency_scope: command.idempotency.scope,
    idempotency_scope_id: command.idempotency.scope_id,
    payload: command.payload,
  };
}

function canonicalRequestHash(command) {
  const digest = crypto
    .createHash("sha256")
    .update(canonicalize(canonicalEffect(command)), "utf8")
    .digest("hex");
  return `sha256:${digest}`;
}

function constantTimeEqual(left, right) {
  const leftBytes = Buffer.from(left, "utf8");
  const rightBytes = Buffer.from(right, "utf8");
  return (
    leftBytes.length === rightBytes.length &&
    crypto.timingSafeEqual(leftBytes, rightBytes)
  );
}

function semanticViolations(envelope) {
  const violations = [];

  if (envelope.schema_id === "kolibri.command") {
    if (
      envelope.payload_schema_id !==
      `kolibri.${envelope.command_name}.command`
    ) {
      violations.push({
        path: "/payload_schema_id",
        code: "payload_schema_name_mismatch",
      });
    }
    try {
      if (
        !constantTimeEqual(
          envelope.idempotency.canonical_request_hash,
          canonicalRequestHash(envelope),
        )
      ) {
        violations.push({
          path: "/idempotency/canonical_request_hash",
          code: "canonical_request_hash_mismatch",
        });
      }
    } catch (error) {
      violations.push({
        path: "/idempotency/canonical_request_hash",
        code: "canonicalization_failed",
      });
    }
    if (Date.parse(envelope.deadline_at) <= Date.parse(envelope.issued_at)) {
      violations.push({
        path: "/deadline_at",
        code: "deadline_not_after_issuance",
      });
    }

    const subjectKeyByScope = {
      tenant: "tenant_id",
      goal: "goal_id",
      case: "case_id",
      task: "task_id",
    };
    const subjectKey = subjectKeyByScope[envelope.idempotency.scope];
    const expectedScopeId =
      subjectKey === "tenant_id"
        ? envelope.identity.tenant_id
        : envelope.identity.subject_refs[subjectKey];
    if (subjectKey && envelope.idempotency.scope_id !== expectedScopeId) {
      violations.push({
        path: "/idempotency/scope_id",
        code: "idempotency_scope_mismatch",
      });
    }
  }

  if (envelope.schema_id === "kolibri.event") {
    if (
      envelope.payload_schema_id !==
      `kolibri.${envelope.event_name}.event`
    ) {
      violations.push({
        path: "/payload_schema_id",
        code: "payload_schema_name_mismatch",
      });
    }
    if (Date.parse(envelope.recorded_at) < Date.parse(envelope.occurred_at)) {
      violations.push({
        path: "/recorded_at",
        code: "recorded_before_occurred",
      });
    }
    if (
      envelope.source_command_id !== null &&
      envelope.trace.causation_id !== envelope.source_command_id
    ) {
      violations.push({
        path: "/trace/causation_id",
        code: "source_command_causation_mismatch",
      });
    }
  }

  return violations;
}

function createCommonEnvelopeValidator(Ajv, contractDir = __dirname) {
  const ajv = loadCommonSchemas(Ajv, contractDir);

  return function validateCommonEnvelope(envelope) {
    if (!envelope || typeof envelope !== "object" || Array.isArray(envelope)) {
      return validationFailure("invalid_envelope");
    }

    const contract = ENVELOPES[envelope.schema_id];
    if (!contract || envelope.schema_version !== contract.version) {
      return validationFailure("unsupported_schema");
    }

    const schemaId =
      `https://schemas.kolibriai.ru/v1/common/${contract.file}`;
    const validate = ajv.getSchema(schemaId);
    if (!validate) {
      throw new Error(`schema not registered: ${schemaId}`);
    }
    if (!validate(envelope)) {
      return validationFailure(
        "invalid_envelope",
        (validate.errors || []).map((error) => ({
          path:
            error.keyword === "additionalProperties"
              ? `${error.dataPath || ""}/${error.params.additionalProperty}`
              : error.keyword === "required"
                ? `${error.dataPath || ""}/${error.params.missingProperty}`
                : error.dataPath || "/",
          code: error.keyword,
        })),
      );
    }

    const violations = semanticViolations(envelope);
    return violations.length
      ? validationFailure("invalid_envelope", violations)
      : Object.freeze({ ok: true, code: null, violations: [] });
  };
}

module.exports = {
  ENVELOPES,
  SCHEMA_FILES,
  canonicalEffect,
  canonicalRequestHash,
  canonicalize,
  createCommonEnvelopeValidator,
  loadCommonSchemas,
};
