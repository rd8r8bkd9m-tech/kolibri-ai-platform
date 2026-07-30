"use strict";

const fs = require("node:fs");
const path = require("node:path");
const {
  createCommonEnvelopeValidator,
} = require("../common/validator.cjs");

const DOMAIN_SCHEMAS = Object.freeze([
  "../goals/goal.schema.json",
  "../goals/goal-create.schema.json",
  "../goals/goal-update.schema.json",
  "../goals/goal-transition.schema.json",
  "fact.schema.json",
  "assumption.schema.json",
  "proposal.schema.json",
  "decision.schema.json",
  "open-question.schema.json",
  "project-case.schema.json",
  "project-case-transition.schema.json",
]);

const DOMAIN_CONTRACTS = Object.freeze({
  "kolibri.goal": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/goals/goal.schema.json",
  }),
  "kolibri.goal.create.command": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/goals/goal-create.schema.json",
  }),
  "kolibri.goal.update.command": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/goals/goal-update.schema.json",
  }),
  "kolibri.goal.transition.command": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/goals/goal-transition.schema.json",
  }),
  "kolibri.project_case": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/cases/project-case.schema.json",
  }),
  "kolibri.project_case.transition.command": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/cases/project-case-transition.schema.json",
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
    const id = item[key];
    if (seen.has(id)) {
      violations.push(violation(pathValue, "duplicate_register_id"));
    }
    seen.add(id);
  }
}

function validateFactSemantics(fact, index, violations) {
  const pathValue = `/facts/${index}`;
  const typeMatches =
    (fact.value_type === "text" && typeof fact.value === "string") ||
    (fact.value_type === "number" && typeof fact.value === "number") ||
    (fact.value_type === "boolean" && typeof fact.value === "boolean") ||
    (fact.value_type === "date" &&
      typeof fact.value === "string" &&
      !Number.isNaN(Date.parse(fact.value))) ||
    (fact.value_type === "quantity" && typeof fact.value === "number") ||
    fact.value_type === "reference" ||
    fact.value_type === "json";
  if (!typeMatches) {
    violations.push(violation(`${pathValue}/value`, "fact_value_type_mismatch"));
  }
  if (fact.value_type === "quantity" && fact.unit === null) {
    violations.push(violation(`${pathValue}/unit`, "quantity_unit_required"));
  }
}

function validateGoal(goal) {
  const violations = [];
  uniqueIds(
    goal.acceptance_criteria,
    "criterion_id",
    "/acceptance_criteria",
    violations,
  );
  if (Date.parse(goal.updated_at) < Date.parse(goal.created_at)) {
    violations.push(violation("/updated_at", "updated_before_created"));
  }
  return violations;
}

function prefixedViolations(prefix, violations) {
  return violations.map((item) => ({
    path: `${prefix}${item.path === "/" ? "" : item.path}`,
    code: item.code,
  }));
}

function validateGoalCreate(command) {
  const violations = prefixedViolations(
    "/goal",
    validateGoal(command.goal),
  );
  const goal = command.goal;
  if (goal.version !== 1) {
    violations.push(violation("/goal/version", "initial_version_required"));
  }
  if (goal.status !== "new") {
    violations.push(violation("/goal/status", "initial_status_required"));
  }
  for (const field of (
    ["case_id", "current_case_version", "workflow_id", "current_workflow_version"]
  )) {
    if (goal[field] !== null) {
      violations.push(violation(`/goal/${field}`, "initial_link_must_be_null"));
    }
  }
  if (
    goal.created_at !== command.requested_at ||
    goal.updated_at !== command.requested_at
  ) {
    violations.push(
      violation("/requested_at", "initial_timestamp_mismatch"),
    );
  }
  return violations;
}

function validateGoalUpdate(command) {
  const violations = prefixedViolations(
    "/goal",
    validateGoal(command.goal),
  );
  if (command.goal_id !== command.goal.goal_id) {
    violations.push(
      violation("/goal/goal_id", "goal_id_mismatch"),
    );
  }
  if (command.next_version !== command.expected_version + 1) {
    violations.push(
      violation("/next_version", "non_monotonic_version"),
    );
  }
  if (command.goal.version !== command.next_version) {
    violations.push(
      violation("/goal/version", "next_goal_version_mismatch"),
    );
  }
  if (command.goal.updated_at !== command.requested_at) {
    violations.push(
      violation("/goal/updated_at", "requested_at_mismatch"),
    );
  }
  return violations;
}

function validateProjectCase(projectCase) {
  const violations = [];
  if (projectCase.intent_snapshot.goal_version !== projectCase.goal_version) {
    violations.push(
      violation("/intent_snapshot/goal_version", "goal_version_mismatch"),
    );
  }
  if (Date.parse(projectCase.updated_at) < Date.parse(projectCase.created_at)) {
    violations.push(violation("/updated_at", "updated_before_created"));
  }

  const registers = [
    ["facts", "fact_id"],
    ["assumptions", "assumption_id"],
    ["proposals", "proposal_id"],
    ["decisions", "decision_id"],
    ["open_questions", "question_id"],
    ["requirements", "item_id"],
    ["constraints", "item_id"],
  ];
  const allIds = new Set();
  for (const [register, idKey] of registers) {
    uniqueIds(
      projectCase[register],
      idKey,
      `/${register}`,
      violations,
    );
    for (const item of projectCase[register]) {
      const id = item[idKey];
      if (allIds.has(id)) {
        violations.push(violation(`/${register}`, "duplicate_case_item_id"));
      }
      allIds.add(id);
    }
  }

  projectCase.facts.forEach((fact, index) =>
    validateFactSemantics(fact, index, violations),
  );

  const proposals = new Map(
    projectCase.proposals.map((proposal) => [proposal.proposal_id, proposal]),
  );
  const selectedProposalIds = new Set();
  projectCase.decisions.forEach((decision, index) => {
    const basePath = `/decisions/${index}`;
    if (!decision.alternatives.includes(decision.selected_option)) {
      violations.push(
        violation(`${basePath}/selected_option`, "selected_option_not_offered"),
      );
    }
    if (decision.effective_case_version > projectCase.version) {
      violations.push(
        violation(
          `${basePath}/effective_case_version`,
          "decision_from_future_version",
        ),
      );
    }
    if (decision.selected_proposal_id !== null) {
      const proposal = proposals.get(decision.selected_proposal_id);
      if (!proposal) {
        violations.push(
          violation(
            `${basePath}/selected_proposal_id`,
            "selected_proposal_not_found",
          ),
        );
      } else if (
        proposal.status !== "selected" ||
        proposal.option !== decision.selected_option
      ) {
        violations.push(
          violation(
            `${basePath}/selected_proposal_id`,
            "selected_proposal_mismatch",
          ),
        );
      }
      selectedProposalIds.add(decision.selected_proposal_id);
    }
  });
  projectCase.proposals.forEach((proposal, index) => {
    if (
      proposal.status === "selected" &&
      !selectedProposalIds.has(proposal.proposal_id)
    ) {
      violations.push(
        violation(
          `/proposals/${index}/status`,
          "selected_proposal_without_decision",
        ),
      );
    }
  });

  projectCase.open_questions.forEach((question, index) => {
    if (question.status === "answered" && question.answer_ref === null) {
      violations.push(
        violation(
          `/open_questions/${index}/answer_ref`,
          "answered_question_missing_answer",
        ),
      );
    }
    if (
      question.resolved_at !== null &&
      Date.parse(question.resolved_at) < Date.parse(question.created_at)
    ) {
      violations.push(
        violation(
          `/open_questions/${index}/resolved_at`,
          "resolved_before_created",
        ),
      );
    }
  });
  return violations;
}

function validateTransition(transition, machine) {
  const violations = [];
  if (transition.next_version !== transition.expected_version + 1) {
    violations.push(violation("/next_version", "non_monotonic_version"));
  }
  const allowed = machine.allowed[transition.from_status] || [];
  if (!allowed.includes(transition.to_status)) {
    violations.push(violation("/to_status", "transition_not_allowed"));
  }
  return violations;
}

function assertMachine(machine, schemaStates) {
  if (
    !machine ||
    machine.schema_version !== "1.0" ||
    typeof machine.schema_id !== "string" ||
    !machine.schema_id.startsWith("kolibri.")
  ) {
    throw new Error("invalid state machine identity");
  }
  const states = Object.keys(machine.allowed);
  const declaredStates = [...schemaStates].sort();
  const machineStates = [...states].sort();
  if (JSON.stringify(declaredStates) !== JSON.stringify(machineStates)) {
    throw new Error(
      `state machine/schema drift: schema=${declaredStates.join(",")} ` +
        `machine=${machineStates.join(",")}`,
    );
  }
  for (const terminal of machine.terminal_states) {
    if (!states.includes(terminal) || machine.allowed[terminal].length !== 0) {
      throw new Error(`terminal state has outgoing transition: ${terminal}`);
    }
  }
  for (const [state, targets] of Object.entries(machine.allowed)) {
    if (targets.length === 0 && !machine.terminal_states.includes(state)) {
      throw new Error(`dead-end state is not terminal: ${state}`);
    }
    for (const target of targets) {
      if (!states.includes(target)) {
        throw new Error(`transition targets unknown state: ${target}`);
      }
    }
  }
}

function createGoalCaseValidator(Ajv, casesDir = __dirname) {
  const ajv = new Ajv({ allErrors: true, jsonPointers: true });
  const schemasByPath = new Map();
  for (const relativePath of DOMAIN_SCHEMAS) {
    const schema = readJson(path.resolve(casesDir, relativePath));
    schemasByPath.set(relativePath, schema);
    ajv.addSchema(schema);
  }
  const goalMachine = readJson(
    path.resolve(casesDir, "../goals/goal-transitions.json"),
  );
  const caseMachine = readJson(
    path.resolve(casesDir, "project-case-transitions.json"),
  );
  assertMachine(
    goalMachine,
    schemasByPath.get("../goals/goal.schema.json").definitions.status.enum,
  );
  assertMachine(
    caseMachine,
    schemasByPath.get("project-case.schema.json").definitions.status.enum,
  );

  return function validateGoalCase(value) {
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
    if (value.schema_id === "kolibri.goal") {
      violations = validateGoal(value);
    } else if (value.schema_id === "kolibri.goal.create.command") {
      violations = validateGoalCreate(value);
    } else if (value.schema_id === "kolibri.goal.update.command") {
      violations = validateGoalUpdate(value);
    } else if (value.schema_id === "kolibri.project_case") {
      violations = validateProjectCase(value);
    } else if (value.schema_id === "kolibri.goal.transition.command") {
      violations = validateTransition(value, goalMachine);
    } else {
      violations = validateTransition(value, caseMachine);
    }
    return violations.length
      ? { ok: false, code: "invalid_domain_contract", violations }
      : { ok: true, code: null, violations: [] };
  };
}

function createGoalCaseCommandValidator(
  Ajv,
  casesDir = __dirname,
  commonDir = path.resolve(casesDir, "../common"),
) {
  const validateEnvelope = createCommonEnvelopeValidator(Ajv, commonDir);
  const validateDomain = createGoalCaseValidator(Ajv, casesDir);
  const commandContracts = Object.freeze({
    "goal.create": Object.freeze({
      schemaId: "kolibri.goal.create.command",
      subjectPath: ["goal", "goal_id"],
      goalPath: ["goal"],
    }),
    "goal.update": Object.freeze({
      schemaId: "kolibri.goal.update.command",
      subjectPath: ["goal_id"],
      goalPath: ["goal"],
    }),
    "goal.transition": Object.freeze({
      schemaId: "kolibri.goal.transition.command",
      subjectPath: ["goal_id"],
      goalPath: null,
    }),
    "project_case.transition": Object.freeze({
      schemaId: "kolibri.project_case.transition.command",
      subjectPath: ["case_id"],
      goalPath: null,
    }),
  });

  return function validateGoalCaseCommand(envelope) {
    const envelopeResult = validateEnvelope(envelope);
    if (!envelopeResult.ok) {
      return envelopeResult;
    }

    const commandContract = commandContracts[envelope.command_name];
    if (!commandContract) {
      return {
        ok: false,
        code: "unsupported_domain_command",
        violations: [
          violation("/command_name", "unsupported_domain_command"),
        ],
      };
    }

    const violations = [];
    if (envelope.target_owner !== "logical_home_control_plane") {
      violations.push(
        violation("/target_owner", "incorrect_command_owner"),
      );
    }
    if (envelope.identity.authority.authority_role !==
        "logical_home_control_plane") {
      violations.push(
        violation(
          "/identity/authority/authority_role",
          "incorrect_authority_role",
        ),
      );
    }
    if (
      !envelope.identity.authority.capabilities.includes(envelope.command_name)
    ) {
      violations.push(
        violation(
          "/identity/authority/capabilities",
          "required_capability_missing",
        ),
      );
    }
    if (envelope.payload_schema_id !== commandContract.schemaId) {
      violations.push(
        violation("/payload_schema_id", "incorrect_payload_schema"),
      );
    }
    if (envelope.payload_schema_version !== "1.0") {
      violations.push(
        violation("/payload_schema_version", "unsupported_payload_schema"),
      );
    }

    const subjectKey = envelope.command_name.startsWith("goal.")
      ? "goal_id"
      : "case_id";
    const payloadSubject = commandContract.subjectPath.reduce(
      (current, field) => current?.[field],
      envelope.payload,
    );
    const identitySubject = envelope.identity.subject_refs[subjectKey];
    if (payloadSubject !== identitySubject) {
      violations.push(
        violation(
          `/payload/${commandContract.subjectPath.join("/")}`,
          "subject_reference_mismatch",
        ),
      );
    }
    if (
      subjectKey === "goal_id" &&
      (
        envelope.idempotency.scope !== "goal" ||
        envelope.idempotency.scope_id !== identitySubject
      )
    ) {
      violations.push(
        violation(
          "/idempotency/scope",
          "goal_idempotency_scope_required",
        ),
      );
    }
    if (commandContract.goalPath) {
      const goal = commandContract.goalPath.reduce(
        (current, field) => current?.[field],
        envelope.payload,
      );
      if (goal?.tenant_id !== envelope.identity.tenant_id) {
        violations.push(
          violation("/payload/goal/tenant_id", "tenant_identity_mismatch"),
        );
      }
      if (goal?.user_id !== envelope.identity.user_id) {
        violations.push(
          violation("/payload/goal/user_id", "user_identity_mismatch"),
        );
      }
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
      ? {
          ok: false,
          code: "invalid_domain_command",
          violations,
        }
      : { ok: true, code: null, violations: [] };
  };
}

module.exports = {
  DOMAIN_CONTRACTS,
  DOMAIN_SCHEMAS,
  createGoalCaseCommandValidator,
  createGoalCaseValidator,
};
