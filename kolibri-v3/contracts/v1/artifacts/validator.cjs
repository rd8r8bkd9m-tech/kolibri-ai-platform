"use strict";

const fs = require("node:fs");
const path = require("node:path");
const {
  createCommonEnvelopeValidator,
} = require("../common/validator.cjs");

const SCHEMA_PATHS = Object.freeze([
  "artifact.schema.json",
  "artifact-state.schema.json",
  "artifact-state-transition.schema.json",
  "../quality/finding.schema.json",
  "../quality/evidence.schema.json",
  "../quality/review.schema.json",
  "../quality/signoff.schema.json",
  "../quality/quality-manifest.schema.json",
]);

const DOMAIN_CONTRACTS = Object.freeze({
  "kolibri.artifact": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/artifacts/artifact.schema.json",
  }),
  "kolibri.artifact_state": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/artifacts/artifact-state.schema.json",
  }),
  "kolibri.artifact.state.transition.command": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/artifacts/artifact-state-transition.schema.json",
  }),
  "kolibri.evidence": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/quality/evidence.schema.json",
  }),
  "kolibri.review": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/quality/review.schema.json",
  }),
  "kolibri.signoff": Object.freeze({
    version: "1.0",
    schema: "https://schemas.kolibriai.ru/v1/quality/signoff.schema.json",
  }),
  "kolibri.artifact_quality_manifest": Object.freeze({
    version: "1.0",
    schema:
      "https://schemas.kolibriai.ru/v1/quality/quality-manifest.schema.json",
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

function sameArtifactRef(left, right) {
  return Boolean(
    left &&
      right &&
      left.artifact_id === right.artifact_id &&
      left.artifact_version === right.artifact_version &&
      left.content_hash === right.content_hash,
  );
}

function hasExactVersionedRef(refs, refId, version) {
  return refs.some(
    (ref) => ref.ref_id === refId && ref.version === version,
  );
}

function everyRefResolved(refs, records, idKey, versionKey) {
  return refs.every((ref) =>
    records.some(
      (record) =>
        record[idKey] === ref.ref_id &&
        record[versionKey] === ref.version,
    ),
  );
}

function validateArtifact(artifact) {
  const violations = [];
  uniqueIds(artifact.inputs, "input_id", "/inputs", violations);
  uniqueIds(
    artifact.provenance,
    "provenance_id",
    "/provenance",
    violations,
  );
  if (artifact.supersedes !== null) {
    if (
      artifact.supersedes.artifact_id !== artifact.artifact_id ||
      artifact.supersedes.artifact_version >= artifact.artifact_version
    ) {
      violations.push(
        violation("/supersedes", "invalid_artifact_supersession"),
      );
    }
    if (artifact.supersedes.content_hash === artifact.content.content_hash) {
      violations.push(
        violation("/supersedes/content_hash", "supersession_hash_unchanged"),
      );
    }
  } else if (artifact.artifact_version !== 1) {
    violations.push(
      violation("/supersedes", "artifact_supersession_required"),
    );
  }
  return violations;
}

function validateArtifactState(state) {
  const violations = [];
  if (
    state.status !== "stale" &&
    state.invalidated_by.length > 0
  ) {
    violations.push(
      violation("/invalidated_by", "invalidation_only_for_stale"),
    );
  }
  return violations;
}

function assertMachine(machine, schemaStates) {
  if (
    !machine ||
    machine.schema_id !== "kolibri.artifact.transitions" ||
    machine.schema_version !== "1.0"
  ) {
    throw new Error("invalid artifact state machine identity");
  }
  const states = Object.keys(machine.allowed).sort();
  const declared = [...schemaStates].sort();
  if (JSON.stringify(states) !== JSON.stringify(declared)) {
    throw new Error("artifact state machine/schema drift");
  }
  for (const [state, targets] of Object.entries(machine.allowed)) {
    if (targets.length === 0 && !machine.terminal_states.includes(state)) {
      throw new Error(`dead-end artifact state is not terminal: ${state}`);
    }
    if (targets.length > 0 && machine.terminal_states.includes(state)) {
      throw new Error(`terminal artifact state has outgoing transition: ${state}`);
    }
    for (const target of targets) {
      if (!states.includes(target)) {
        throw new Error(`artifact transition targets unknown state: ${target}`);
      }
    }
  }
}

function validateArtifactTransition(transition, machine) {
  const violations = [];
  if (
    transition.next_state_version !== transition.expected_state_version + 1
  ) {
    violations.push(
      violation("/next_state_version", "non_monotonic_version"),
    );
  }
  const allowed = machine.allowed[transition.from_status] || [];
  if (!allowed.includes(transition.to_status)) {
    violations.push(violation("/to_status", "transition_not_allowed"));
  }
  if (
    transition.to_status === "stale" &&
    transition.invalidated_by.length === 0
  ) {
    violations.push(
      violation("/invalidated_by", "stale_invalidation_required"),
    );
  }
  if (
    transition.to_status !== "stale" &&
    transition.invalidated_by.length > 0
  ) {
    violations.push(
      violation("/invalidated_by", "invalidation_only_for_stale"),
    );
  }
  return violations;
}

function validateEvidence(evidence) {
  const violations = [];
  const effectiveFrom = evidence.source.effective_from;
  const effectiveTo = evidence.source.effective_to;
  if (
    effectiveFrom !== null &&
    effectiveTo !== null &&
    Date.parse(effectiveTo) <= Date.parse(effectiveFrom)
  ) {
    violations.push(
      violation("/source/effective_to", "invalid_effective_time_order"),
    );
  }
  const verifier = evidence.verifier;
  if (
    verifier.status === "unverified" &&
    (verifier.verified_by !== null ||
      verifier.verified_at !== null ||
      verifier.check_refs.length > 0)
  ) {
    violations.push(
      violation("/verifier", "unverified_evidence_has_verification"),
    );
  }
  if (
    verifier.status !== "unverified" &&
    (verifier.verified_by === null ||
      verifier.verified_at === null ||
      verifier.check_refs.length === 0)
  ) {
    violations.push(
      violation("/verifier", "verification_evidence_required"),
    );
  }
  if (
    evidence.status === "active" &&
    evidence.revocation !== null
  ) {
    violations.push(
      violation("/revocation", "active_evidence_cannot_be_revoked"),
    );
  }
  if (
    evidence.supersedes !== null &&
    (evidence.supersedes.evidence_id !== evidence.evidence_id ||
      evidence.supersedes.evidence_version >= evidence.evidence_version)
  ) {
    violations.push(
      violation("/supersedes", "invalid_evidence_supersession"),
    );
  }
  return violations;
}

function validateReview(review) {
  const violations = [];
  if (review.author_actor_id === review.reviewer_actor_id) {
    violations.push(
      violation("/reviewer_actor_id", "reviewer_not_independent"),
    );
  }
  uniqueIds(review.criteria, "criterion_id", "/criteria", violations);
  uniqueIds(review.findings, "finding_id", "/findings", violations);
  if (
    review.completed_at !== null &&
    Date.parse(review.completed_at) < Date.parse(review.requested_at)
  ) {
    violations.push(
      violation("/completed_at", "review_completed_before_requested"),
    );
  }
  const hasBlockingFinding = review.findings.some(
    (finding) =>
      ["high", "critical"].includes(finding.severity) &&
      finding.status === "open",
  );
  const failedCriterion = review.criteria.some(
    (criterion) =>
      criterion.result === "failed" || criterion.result === "inconclusive",
  );
  if (
    review.disposition === "approved_internal" &&
    (hasBlockingFinding || failedCriterion)
  ) {
    violations.push(
      violation("/disposition", "approval_has_blocking_quality_result"),
    );
  }
  return violations;
}

function validateSignOff(signoff) {
  const violations = [];
  if (
    signoff.status !== "revoked" &&
    signoff.revocation !== null
  ) {
    violations.push(
      violation("/revocation", "active_signoff_cannot_have_revocation"),
    );
  }
  if (
    signoff.revocation !== null &&
    Date.parse(signoff.revocation.revoked_at) <= Date.parse(signoff.granted_at)
  ) {
    violations.push(
      violation("/revocation/revoked_at", "revocation_not_after_grant"),
    );
  }
  if (
    signoff.supersedes !== null &&
    (signoff.supersedes.ref_id !== signoff.signoff_id ||
      signoff.supersedes.version >= signoff.signoff_version)
  ) {
    violations.push(
      violation("/supersedes", "invalid_signoff_supersession"),
    );
  }
  return violations;
}

function validateManifestShape(manifest) {
  const violations = [];
  if (
    manifest.eligibility !== "ineligible" &&
    manifest.blockers.length > 0
  ) {
    violations.push(
      violation("/blockers", "eligible_manifest_has_blockers"),
    );
  }
  if (
    manifest.eligibility === "eligible_release" &&
    manifest.artifact_status !== "released"
  ) {
    violations.push(
      violation("/eligibility", "release_requires_released_artifact"),
    );
  }
  return violations;
}

function createArtifactQualityValidator(Ajv) {
  const ajv = new Ajv({
    allErrors: true,
    jsonPointers: true,
    schemaId: "auto",
    unknownFormats: ["date-time"],
  });
  const base = __dirname;
  for (const relativePath of SCHEMA_PATHS) {
    ajv.addSchema(readJson(path.resolve(base, relativePath)));
  }
  const machine = readJson(
    path.resolve(base, "artifact-transitions.json"),
  );
  const stateSchema = readJson(
    path.resolve(base, "artifact-state.schema.json"),
  );
  assertMachine(
    machine,
    stateSchema.definitions.status.enum,
  );

  return function validate(value) {
    const contract = DOMAIN_CONTRACTS[value && value.schema_id];
    if (
      !contract ||
      !value ||
      value.schema_version !== contract.version
    ) {
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
        code: "invalid_artifact_quality_contract",
        violations: schemaViolations(schemaValidator.errors),
      };
    }
    let violations = [];
    if (value.schema_id === "kolibri.artifact") {
      violations = validateArtifact(value);
    } else if (value.schema_id === "kolibri.artifact_state") {
      violations = validateArtifactState(value);
    } else if (
      value.schema_id === "kolibri.artifact.state.transition.command"
    ) {
      violations = validateArtifactTransition(value, machine);
    } else if (value.schema_id === "kolibri.evidence") {
      violations = validateEvidence(value);
    } else if (value.schema_id === "kolibri.review") {
      violations = validateReview(value);
    } else if (value.schema_id === "kolibri.signoff") {
      violations = validateSignOff(value);
    } else if (
      value.schema_id === "kolibri.artifact_quality_manifest"
    ) {
      violations = validateManifestShape(value);
    }
    return {
      ok: violations.length === 0,
      code:
        violations.length === 0
          ? null
          : "invalid_artifact_quality_contract",
      violations,
    };
  };
}

function createArtifactCommandValidator(Ajv) {
  const validateEnvelope = createCommonEnvelopeValidator(Ajv);
  const validateDomain = createArtifactQualityValidator(Ajv);
  return function validate(command) {
    const envelope = validateEnvelope(command);
    if (!envelope.ok) {
      return envelope;
    }
    const violations = [];
    if (
      command.command_name !== "artifact.state.transition" ||
      command.payload_schema_id !==
        "kolibri.artifact.state.transition.command" ||
      command.payload_schema_version !== "1.0" ||
      command.target_owner !== "logical_home_control_plane"
    ) {
      violations.push(
        violation("/", "incorrect_artifact_command_envelope"),
      );
    }
    if (
      command.identity.authority.authority_role !==
        "logical_home_control_plane"
    ) {
      violations.push(
        violation(
          "/identity/authority/authority_role",
          "incorrect_authority_owner",
        ),
      );
    }
    if (
      !command.identity.authority.capabilities.includes(
        "artifact.lifecycle.transition",
      )
    ) {
      violations.push(
        violation(
          "/identity/authority/capabilities",
          "required_capability_missing",
        ),
      );
    }
    const domain = validateDomain(command.payload);
    if (!domain.ok) {
      violations.push(...domain.violations.map((item) => ({
        path: `/payload${item.path === "/" ? "" : item.path}`,
        code: item.code,
      })));
    }
    return {
      ok: violations.length === 0,
      code: violations.length === 0 ? null : "invalid_artifact_command",
      violations,
    };
  };
}

function validateQualityManifestAtOwner(
  manifest,
  artifact,
  state,
  evidences,
  reviews,
  signoffs,
  requiredSignoffTypes,
  validateDomain,
) {
  const values = [manifest, artifact, state, ...evidences, ...reviews, ...signoffs];
  for (const value of values) {
    const result = validateDomain(value);
    if (!result.ok) {
      return { ok: false, code: "rejected_invalid_contract", violations: result.violations };
    }
  }
  const violations = [];
  const artifactRef = {
    artifact_id: artifact.artifact_id,
    artifact_version: artifact.artifact_version,
    content_hash: artifact.content.content_hash,
  };
  if (!sameArtifactRef(manifest.artifact_ref, artifactRef)) {
    violations.push(
      violation("/artifact_ref", "manifest_artifact_binding_mismatch"),
    );
  }
  if (
    state.artifact_id !== artifact.artifact_id ||
    state.artifact_version !== artifact.artifact_version ||
    state.content_hash !== artifact.content.content_hash ||
    manifest.artifact_state_version !== state.state_version ||
    manifest.artifact_status !== state.status
  ) {
    violations.push(
      violation("/artifact_state_version", "artifact_state_binding_mismatch"),
    );
  }
  for (const value of [manifest, ...evidences, ...reviews, ...signoffs]) {
    if (
      value.tenant_id !== artifact.tenant_id ||
      value.goal_id !== artifact.goal_id ||
      value.case_id !== artifact.case_id
    ) {
      violations.push(
        violation("/", "artifact_subject_binding_mismatch"),
      );
      break;
    }
  }
  for (const evidence of evidences) {
    if (
      evidence.claim.target.ref_id !== artifact.artifact_id ||
      evidence.claim.target.ref_version !== artifact.artifact_version ||
      !hasExactVersionedRef(
        manifest.evidence_refs,
        evidence.evidence_id,
        evidence.evidence_version,
      ) ||
      evidence.status !== "active" ||
      evidence.verifier.status !== "passed" ||
      evidence.applicability === "not_applicable"
    ) {
      violations.push(
        violation("/evidence_refs", "evidence_binding_or_status_mismatch"),
      );
    }
  }
  if (
    !everyRefResolved(
      manifest.evidence_refs,
      evidences,
      "evidence_id",
      "evidence_version",
    )
  ) {
    violations.push(
      violation("/evidence_refs", "unresolved_evidence_ref"),
    );
  }
  for (const review of reviews) {
    if (
      !sameArtifactRef(review.artifact_ref, artifactRef) ||
      review.author_actor_id !== artifact.created_by ||
      review.reviewer_actor_id === artifact.created_by ||
      !hasExactVersionedRef(
        manifest.review_refs,
        review.review_id,
        review.review_version,
      ) ||
      review.status !== "completed" ||
      review.disposition !== "approved_internal"
    ) {
      violations.push(
        violation("/review_refs", "review_binding_or_status_mismatch"),
      );
    }
  }
  if (
    !everyRefResolved(
      manifest.review_refs,
      reviews,
      "review_id",
      "review_version",
    )
  ) {
    violations.push(
      violation("/review_refs", "unresolved_review_ref"),
    );
  }
  for (const signoff of signoffs) {
    const signoffReviewsResolved = everyRefResolved(
      signoff.review_refs,
      reviews,
      "review_id",
      "review_version",
    );
    if (
      !sameArtifactRef(signoff.artifact_ref, artifactRef) ||
      !hasExactVersionedRef(
        manifest.signoff_refs,
        signoff.signoff_id,
        signoff.signoff_version,
      ) ||
      !signoffReviewsResolved ||
      signoff.status !== "granted"
    ) {
      violations.push(
        violation("/signoff_refs", "signoff_binding_or_status_mismatch"),
      );
    }
  }
  if (
    !everyRefResolved(
      manifest.signoff_refs,
      signoffs,
      "signoff_id",
      "signoff_version",
    )
  ) {
    violations.push(
      violation("/signoff_refs", "unresolved_signoff_ref"),
    );
  }
  for (const requiredType of requiredSignoffTypes) {
    if (!signoffs.some(
      (signoff) =>
        signoff.signoff_type === requiredType && signoff.status === "granted",
    )) {
      violations.push(
        violation("/signoff_refs", `missing_signoff_type:${requiredType}`),
      );
    }
  }
  const invalidArtifactStatuses = new Set(["draft", "in_review", "stale", "revoked", "superseded"]);
  if (
    manifest.eligibility !== "ineligible" &&
    invalidArtifactStatuses.has(state.status)
  ) {
    violations.push(
      violation("/eligibility", "artifact_not_eligible"),
    );
  }
  return {
    ok: violations.length === 0,
    code: violations.length === 0 ? "accepted" : "rejected_owner_context",
    violations,
  };
}

module.exports = {
  createArtifactCommandValidator,
  createArtifactQualityValidator,
  validateQualityManifestAtOwner,
};
