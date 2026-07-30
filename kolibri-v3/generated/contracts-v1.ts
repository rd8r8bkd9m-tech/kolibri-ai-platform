/* Generated from contracts/v1. Do not edit by hand. */

export const CONTRACT_GENERATOR_VERSION = "1.0" as const

export type KolibriA2aDeliveryCursor = { readonly "schema_id": "kolibri.a2a.delivery_cursor"; readonly "schema_version": "1.0"; readonly "tenant_id": string; readonly "channel_id": string; readonly "last_sequence": number; readonly "last_message_id": string | null; readonly "accepted_messages": Readonly<Record<string, string>>; readonly "deduplication_index": Readonly<Record<string, { readonly "message_id": string; readonly "content_hash": string; }>>; }

export type KolibriA2aMessageAppendedEvent = { readonly "schema_id": "kolibri.a2a.message_appended.event"; readonly "schema_version": "1.0"; readonly "a2a_message_id": string; readonly "tenant_id": string; readonly "goal_id": string; readonly "case_id": string; readonly "task_id": string; readonly "task_version": number; readonly "channel_id": string; readonly "sequence": number; readonly "previous_message_id": string | null; readonly "sender_actor_id": string; readonly "sender_assignment_id": string; readonly "recipient_assignment_ids": ReadonlyArray<string>; readonly "recipient_capability": string | null; readonly "message_type": "request" | "clarification" | "proposal" | "challenge" | "handoff" | "review" | "revision_request" | "approval" | "rejection" | "escalation"; readonly "purpose": string; readonly "response_to_message_id": string | null; readonly "content": { readonly "trust": "untrusted_content"; readonly "text": string; readonly "structured_data": Readonly<Record<string, unknown>>; readonly "reference_ids": ReadonlyArray<string>; }; readonly "content_hash": string; readonly "deduplication_key": string; readonly "sent_at": string; readonly "expires_at": string; }

export type KolibriAgentAssignment = { readonly "schema_id": "kolibri.agent_assignment"; readonly "schema_version": "1.0"; readonly "assignment_id": string; readonly "tenant_id": string; readonly "goal_id": string; readonly "case_id": string; readonly "task_id": string; readonly "task_version": number; readonly "attempt_id": string; readonly "assignee_actor_id": string; readonly "agent_card_id": string; readonly "agent_card_version": number; readonly "temporary_role": string; readonly "purpose": string; readonly "authority_profile": { readonly "authority_id": string; readonly "authority_role": "logical_home_control_plane"; readonly "authority_epoch": number; readonly "authorization_decision_id": string; readonly "capabilities": ReadonlyArray<string>; readonly "allowed_tool_ids": ReadonlyArray<string>; readonly "allowed_resource_refs": ReadonlyArray<string>; readonly "expires_at": string; }; readonly "context_slice": { readonly "case_version": number; readonly "fact_ids": ReadonlyArray<string>; readonly "assumption_ids": ReadonlyArray<string>; readonly "decision_ids": ReadonlyArray<string>; readonly "artifact_refs": ReadonlyArray<string>; readonly "classification": "public" | "internal" | "confidential" | "restricted"; readonly "max_bytes": number; }; readonly "budget": { readonly "compute_units_limit": number; readonly "tool_calls_limit": number; readonly "external_spend_limit_minor": number; readonly "currency": string; }; readonly "lease_id": string; readonly "deadline_at": string; readonly "required_output_ids": ReadonlyArray<string>; readonly "required_evidence_types": ReadonlyArray<string>; readonly "status": "pending" | "active" | "suspended" | "completed" | "revoked" | "expired" | "superseded"; readonly "version": number; readonly "created_at": string; readonly "updated_at": string; }

export type KolibriAgentAssignmentStatusChangedEvent = { readonly "schema_id": "kolibri.agent_assignment.status_changed.event"; readonly "schema_version": "1.0"; readonly "assignment_id": string; readonly "previous_status": "pending" | "active" | "suspended" | "completed" | "revoked" | "expired" | "superseded"; readonly "new_status": "pending" | "active" | "suspended" | "completed" | "revoked" | "expired" | "superseded"; readonly "previous_version": number; readonly "new_version": number; readonly "reason": string; }

export type KolibriAgentCard = { readonly "schema_id": "kolibri.agent_card"; readonly "schema_version": "1.0"; readonly "agent_card_id": string; readonly "tenant_scope": string | "platform"; readonly "display_name": string; readonly "agent_kind": "model" | "worker" | "human" | "hybrid" | "service"; readonly "capabilities": ReadonlyArray<string>; readonly "skills": ReadonlyArray<string>; readonly "model_profiles": ReadonlyArray<string>; readonly "tool_ids": ReadonlyArray<string>; readonly "jurisdictions": ReadonlyArray<string>; readonly "domain_tags": ReadonlyArray<string>; readonly "limits": { readonly "max_concurrent_assignments": number; readonly "max_context_bytes": number; readonly "max_external_spend_minor": number; readonly "currency": string; readonly "latency_slo_ms": number; }; readonly "availability": "available" | "busy" | "degraded" | "offline" | "revoked"; readonly "policy_constraints": ReadonlyArray<string>; readonly "version": number; readonly "updated_at": string; }

export type KolibriArtifact = { readonly "schema_id": "kolibri.artifact"; readonly "schema_version": "1.0"; readonly "artifact_id": string; readonly "artifact_version": number; readonly "tenant_id": string; readonly "goal_id": string; readonly "case_id": string; readonly "task_id": string | null; readonly "artifact_type": string; readonly "domain_output": { readonly "aggregate_type": string; readonly "aggregate_id": string; readonly "aggregate_version": number; }; readonly "content": { readonly "storage_ref": string; readonly "media_type": string; readonly "size_bytes": number; readonly "content_hash": string; readonly "filename": string; }; readonly "contract": { readonly "schema_id": string; readonly "schema_version": string; readonly "renderer_id": string | null; readonly "renderer_version": string | null; }; readonly "generator": { readonly "generator_id": string; readonly "generator_version": string; readonly "execution_ref": string; }; readonly "inputs": ReadonlyArray<{ readonly "input_id": string; readonly "input_kind": "fact" | "assumption" | "decision" | "domain_aggregate" | "artifact" | "source_document" | "tool_result"; readonly "ref_id": string; readonly "ref_version": number; readonly "content_hash": string; readonly "role": string; }>; readonly "provenance": ReadonlyArray<{ readonly "provenance_id": string; readonly "kind": "user_input" | "source_document" | "calculation" | "tool_execution" | "model_generation" | "human_edit"; readonly "source_ref": string; readonly "recorded_at": string; readonly "effective_at": string | null; readonly "actor_or_tool_ref": string; }>; readonly "supersedes": { readonly "artifact_id": string; readonly "artifact_version": number; readonly "content_hash": string; } | null; readonly "created_by": string; readonly "created_at": string; }

export type KolibriArtifactStateTransitionCommand = { readonly "schema_id": "kolibri.artifact.state.transition.command"; readonly "schema_version": "1.0"; readonly "artifact_id": string; readonly "artifact_version": number; readonly "content_hash": string; readonly "expected_state_version": number; readonly "next_state_version": number; readonly "from_status": "draft" | "in_review" | "approved_internal" | "released" | "stale" | "revoked" | "superseded"; readonly "to_status": "draft" | "in_review" | "approved_internal" | "released" | "stale" | "revoked" | "superseded"; readonly "reason": string; readonly "invalidated_by": ReadonlyArray<{ readonly "ref_id": string; readonly "ref_version": number; readonly "content_hash": string; }>; readonly "requested_at": string; }

export type KolibriArtifactQualityManifest = { readonly "schema_id": "kolibri.artifact_quality_manifest"; readonly "schema_version": "1.0"; readonly "manifest_id": string; readonly "manifest_version": number; readonly "tenant_id": string; readonly "goal_id": string; readonly "case_id": string; readonly "artifact_ref": { readonly "artifact_id": string; readonly "artifact_version": number; readonly "content_hash": string; }; readonly "artifact_state_version": number; readonly "artifact_status": "draft" | "in_review" | "approved_internal" | "released" | "stale" | "revoked" | "superseded"; readonly "evidence_refs": ReadonlyArray<{ readonly "ref_id": string; readonly "version": number; }>; readonly "review_refs": ReadonlyArray<{ readonly "ref_id": string; readonly "version": number; }>; readonly "signoff_refs": ReadonlyArray<{ readonly "ref_id": string; readonly "version": number; }>; readonly "eligibility": "eligible_internal" | "eligible_release" | "ineligible"; readonly "blockers": ReadonlyArray<"artifact_not_approved" | "artifact_stale" | "artifact_revoked" | "evidence_missing_or_invalid" | "review_incomplete" | "blocking_finding" | "signoff_missing" | "signoff_stale_or_revoked" | "policy_denied">; readonly "generated_at": string; readonly "generated_by": string; }

export type KolibriArtifactState = { readonly "schema_id": "kolibri.artifact_state"; readonly "schema_version": "1.0"; readonly "artifact_id": string; readonly "artifact_version": number; readonly "content_hash": string; readonly "tenant_id": string; readonly "status": "draft" | "in_review" | "approved_internal" | "released" | "stale" | "revoked" | "superseded"; readonly "state_version": number; readonly "changed_at": string; readonly "reason": string | null; readonly "invalidated_by": ReadonlyArray<{ readonly "ref_id": string; readonly "ref_version": number; readonly "content_hash": string; }>; }

export type KolibriCommand = { readonly "schema_id": "kolibri.command"; readonly "schema_version": "1.0"; readonly "message_id": string; readonly "command_name": string; readonly "payload_schema_id": string; readonly "payload_schema_version": string; readonly "issued_at": string; readonly "deadline_at": string; readonly "target_owner": "logical_home_control_plane" | "product_data_authority" | "provider_execution_authority"; readonly "identity": { readonly "tenant_id": string; readonly "user_id": string | null; readonly "actor": { readonly "actor_id": string; readonly "actor_type": "user" | "service" | "agent" | "system"; }; readonly "authority": { readonly "authority_id": string; readonly "authority_role": "logical_home_control_plane" | "product_data_authority" | "provider_execution_authority"; readonly "authority_epoch": number; readonly "authority_placement_id": string; readonly "authorization_decision_id": string; readonly "capabilities": ReadonlyArray<string>; }; readonly "subject_refs": { readonly "goal_id": string | null; readonly "case_id": string | null; readonly "task_id": string | null; }; }; readonly "trace": { readonly "trace_id": string; readonly "span_id": string; readonly "parent_span_id": string | null; readonly "correlation_id": string; readonly "causation_id": string | null; }; readonly "idempotency": { readonly "key": string; readonly "scope": "tenant" | "goal" | "case" | "task" | "aggregate"; readonly "scope_id": string; readonly "canonical_request_hash": string; }; readonly "payload": Readonly<Record<string, unknown>>; }

export type KolibriDocumentData = { readonly "schema_id": "kolibri.document_data"; readonly "schema_version": "1.0"; readonly "document_data_id": string; readonly "document_type": "commercial_offer" | "contract" | "completion_act" | "invoice"; readonly "title": string; readonly "client_name": string; readonly "contractor_name": string; readonly "estimate_id": string; readonly "currency": string; readonly "total": string; readonly "locale": string; readonly "jurisdiction": string; readonly "sections": ReadonlyArray<{ readonly "title": string; readonly "text": string; readonly "kind"?: "text" | "table" | "disclaimer" | "heading"; readonly "rows"?: ReadonlyArray<Readonly<Record<string, unknown>>>; }>; readonly "totals": { readonly "grand_total": string; readonly "labor": string; readonly "materials": string; readonly "overhead": string; }; readonly "attachments": ReadonlyArray<string>; readonly "provenance": { readonly "created_at": string; readonly "updated_at": string; readonly "estimate_fingerprint": string; readonly "source_version"?: string; }; }

export type KolibriDocumentRenderRequest = { readonly "schema_id": "kolibri.document_render_request"; readonly "schema_version": "1.0"; readonly "request_id": string; readonly "template_id": string; readonly "template_version": string; readonly "template_locale": string; readonly "template_jurisdiction": string; readonly "requested_outputs": ReadonlyArray<"pdf" | "docx" | "xlsx">; readonly "document_data": { readonly "document_data_id": string; readonly "document_type": "commercial_offer" | "contract" | "completion_act" | "invoice"; readonly "title": string; readonly "client_name": string; readonly "contractor_name": string; readonly "estimate_id": string; readonly "currency": string; readonly "total": string; readonly "locale": string; readonly "jurisdiction": string; readonly "sections": ReadonlyArray<{ readonly "title": string; readonly "text": string; readonly "kind"?: "text" | "table" | "disclaimer" | "heading"; readonly "rows"?: ReadonlyArray<Readonly<Record<string, unknown>>>; }>; readonly "totals": { readonly "grand_total": string; readonly "labor": string; readonly "materials": string; readonly "overhead": string; }; readonly "attachments": ReadonlyArray<string>; readonly "provenance": { readonly "created_at": string; readonly "updated_at": string; readonly "estimate_fingerprint": string; }; }; readonly "idempotency_key"?: string; readonly "tenant_id"?: string; readonly "project_id"?: string; }

export type KolibriDocumentRenderResult = { readonly "schema_id": "kolibri.document_render_result"; readonly "schema_version": "1.0"; readonly "request_id": string; readonly "document_id": string; readonly "template_id": string; readonly "template_version": string; readonly "status": "rendered" | "failed" | "deferred"; readonly "generated_at": string; readonly "rendered_locale"?: string; readonly "rendered_jurisdiction"?: string; readonly "assets": ReadonlyArray<{ readonly "format": "pdf" | "docx" | "xlsx"; readonly "content_type": string; readonly "path": string; readonly "size_bytes": number; readonly "sha256": string; }>; readonly "warnings"?: ReadonlyArray<string>; readonly "error"?: string; }

export type KolibriDocumentTemplate = { readonly "schema_id": "kolibri.document_template"; readonly "schema_version": "1.0"; readonly "template_id": string; readonly "template_version": string; readonly "document_type": "commercial_offer" | "contract" | "completion_act" | "invoice"; readonly "locale": string; readonly "jurisdictions": ReadonlyArray<string>; readonly "output_formats": ReadonlyArray<"pdf" | "docx" | "xlsx">; readonly "data_contract": { readonly "schema_id": "kolibri.document_data"; readonly "schema_version": "1.0"; }; readonly "layout_fingerprint": string; readonly "required_fields": ReadonlyArray<string>; readonly "prohibited_fields": ReadonlyArray<string>; readonly "reproducible": boolean; readonly "created_at": string; readonly "updated_at": string; readonly "notes"?: string; }

export type KolibriDocumentTemplateRegistry = { readonly "schema_id": "kolibri.document_template_registry"; readonly "schema_version": "1.0"; readonly "registry_id": string; readonly "generated_at": string; readonly "templates": ReadonlyArray<{ readonly "template_id": string; readonly "template_version": string; readonly "document_type": "commercial_offer" | "contract" | "completion_act" | "invoice"; readonly "locale": string; readonly "jurisdictions": ReadonlyArray<string>; readonly "output_formats": ReadonlyArray<"pdf" | "docx" | "xlsx">; readonly "layout_fingerprint": string; readonly "render_enabled": boolean; }>; }

export type KolibriError = { readonly "schema_id": "kolibri.error"; readonly "schema_version": "1.0"; readonly "error_id": string; readonly "in_response_to": string | null; readonly "occurred_at": string; readonly "http_status": number; readonly "code": string; readonly "category": "validation" | "authentication" | "authorization" | "conflict" | "not_found" | "capacity" | "dependency" | "timeout" | "internal"; readonly "retryable": boolean; readonly "retry_after_ms": number | null; readonly "safe_message": string; readonly "trace": { readonly "trace_id": string; readonly "span_id": string; readonly "parent_span_id": string | null; readonly "correlation_id": string; readonly "causation_id": string | null; }; readonly "violations": ReadonlyArray<{ readonly "path": string; readonly "code": string; readonly "message": string; }>; readonly "details": Readonly<Record<string, unknown>>; }

export type KolibriEvent = { readonly "schema_id": "kolibri.event"; readonly "schema_version": "1.0"; readonly "message_id": string; readonly "event_name": string; readonly "payload_schema_id": string; readonly "payload_schema_version": string; readonly "occurred_at": string; readonly "recorded_at": string; readonly "producer_owner": "logical_home_control_plane" | "product_data_authority" | "provider_execution_authority"; readonly "identity": { readonly "tenant_id": string; readonly "user_id": string | null; readonly "actor": { readonly "actor_id": string; readonly "actor_type": "user" | "service" | "agent" | "system"; }; readonly "authority": { readonly "authority_id": string; readonly "authority_role": "logical_home_control_plane" | "product_data_authority" | "provider_execution_authority"; readonly "authority_epoch": number; readonly "authority_placement_id": string; readonly "authorization_decision_id": string; readonly "capabilities": ReadonlyArray<string>; }; readonly "subject_refs": { readonly "goal_id": string | null; readonly "case_id": string | null; readonly "task_id": string | null; }; }; readonly "trace": { readonly "trace_id": string; readonly "span_id": string; readonly "parent_span_id": string | null; readonly "correlation_id": string; readonly "causation_id": string | null; }; readonly "aggregate": { readonly "aggregate_type": string; readonly "aggregate_id": string; readonly "aggregate_version": number; }; readonly "source_command_id": string | null; readonly "deduplication_key": string; readonly "payload": Readonly<Record<string, unknown>>; }

export type KolibriEvidence = { readonly "schema_id": "kolibri.evidence"; readonly "schema_version": "1.0"; readonly "evidence_id": string; readonly "evidence_version": number; readonly "tenant_id": string; readonly "goal_id": string; readonly "case_id": string; readonly "task_id": string | null; readonly "claim": { readonly "claim_id": string; readonly "statement": string; readonly "target": { readonly "ref_id": string; readonly "ref_version": number; readonly "locator": string; }; }; readonly "source": { readonly "source_type": "user_input" | "document" | "normative_source" | "market_quote" | "measurement" | "calculation" | "tool_result" | "artifact" | "test_result"; readonly "locator": string; readonly "publisher_or_author": string; readonly "retrieved_at": string; readonly "effective_from": string | null; readonly "effective_to": string | null; readonly "jurisdiction": string | null; readonly "region": string | null; readonly "content_hash": string; }; readonly "method": { readonly "method_type": "direct" | "calculation" | "retrieval" | "inspection" | "test" | "human_attestation"; readonly "method_ref": string; readonly "method_version": string; }; readonly "confidence": number; readonly "applicability": "applicable" | "partially_applicable" | "not_applicable" | "unknown"; readonly "verifier": { readonly "status": "unverified" | "passed" | "failed" | "inconclusive"; readonly "verified_by": string | null; readonly "verified_at": string | null; readonly "check_refs": ReadonlyArray<string>; }; readonly "status": "active" | "superseded" | "withdrawn" | "stale" | "revoked"; readonly "supersedes": { readonly "evidence_id": string; readonly "evidence_version": number; } | null; readonly "revocation": { readonly "reason": string; readonly "revoked_by": string; readonly "revoked_at": string; } | null; readonly "created_by": string; readonly "created_at": string; }

export type KolibriGoal = { readonly "schema_id": "kolibri.goal"; readonly "schema_version": "1.0"; readonly "goal_id": string; readonly "tenant_id": string; readonly "user_id": string | null; readonly "intent": { readonly "source_message_id": string; readonly "original_request": string; readonly "normalized_objective": string; readonly "locale": string; }; readonly "acceptance_criteria": ReadonlyArray<{ readonly "criterion_id": string; readonly "statement": string; readonly "verification_method": string; readonly "required": boolean; readonly "status": "pending" | "satisfied" | "waived" | "failed"; }>; readonly "budget_policy": { readonly "currency": string; readonly "compute_units_limit": number; readonly "tool_calls_limit": number; readonly "external_spend_limit_minor": number; readonly "human_services_limit_minor": number; readonly "approval_required_above_minor": number; }; readonly "deadline_policy": { readonly "due_at": string | null; readonly "timezone": string; readonly "late_action": "continue_and_flag" | "escalate" | "pause"; }; readonly "status": "new" | "intake" | "planning" | "executing" | "reviewing" | "awaiting_user" | "awaiting_approval" | "awaiting_payment" | "awaiting_external" | "revising" | "approved_internal" | "released" | "executing_physical" | "completed" | "failed_recoverable" | "cancelled" | "superseded"; readonly "blocking_question_ids": ReadonlyArray<string>; readonly "case_id": string | null; readonly "current_case_version": number | null; readonly "workflow_id": string | null; readonly "current_workflow_version": number | null; readonly "version": number; readonly "supersedes_goal_id": string | null; readonly "created_at": string; readonly "updated_at": string; }

export type KolibriGoalChangedEvent = { readonly "schema_id": "kolibri.goal.changed.event"; readonly "schema_version": "1.0"; readonly "goal_id": string; readonly "command_name": "goal.create" | "goal.update" | "goal.transition"; readonly "change_type": "created" | "updated" | "transitioned" | "cancelled" | "completed"; readonly "previous_version": number | null; readonly "new_version": number; readonly "previous_status": "new" | "intake" | "planning" | "executing" | "reviewing" | "awaiting_user" | "awaiting_approval" | "awaiting_payment" | "awaiting_external" | "revising" | "approved_internal" | "released" | "executing_physical" | "completed" | "failed_recoverable" | "cancelled" | "superseded" | null; readonly "new_status": "new" | "intake" | "planning" | "executing" | "reviewing" | "awaiting_user" | "awaiting_approval" | "awaiting_payment" | "awaiting_external" | "revising" | "approved_internal" | "released" | "executing_physical" | "completed" | "failed_recoverable" | "cancelled" | "superseded"; readonly "reason_provided": boolean; }

export type KolibriGoalCreateCommand = { readonly "schema_id": "kolibri.goal.create.command"; readonly "schema_version": "1.0"; readonly "goal": KolibriGoal; readonly "requested_at": string; }

export type KolibriGoalTransitionCommand = { readonly "schema_id": "kolibri.goal.transition.command"; readonly "schema_version": "1.0"; readonly "goal_id": string; readonly "expected_version": number; readonly "next_version": number; readonly "from_status": "new" | "intake" | "planning" | "executing" | "reviewing" | "awaiting_user" | "awaiting_approval" | "awaiting_payment" | "awaiting_external" | "revising" | "approved_internal" | "released" | "executing_physical" | "completed" | "failed_recoverable" | "cancelled" | "superseded"; readonly "to_status": "new" | "intake" | "planning" | "executing" | "reviewing" | "awaiting_user" | "awaiting_approval" | "awaiting_payment" | "awaiting_external" | "revising" | "approved_internal" | "released" | "executing_physical" | "completed" | "failed_recoverable" | "cancelled" | "superseded"; readonly "reason": string; readonly "requested_at": string; }

export type KolibriGoalUpdateCommand = { readonly "schema_id": "kolibri.goal.update.command"; readonly "schema_version": "1.0"; readonly "goal_id": string; readonly "expected_version": number; readonly "next_version": number; readonly "goal": KolibriGoal; readonly "reason": string; readonly "requested_at": string; }

export type KolibriProductAguiProjection = { readonly "schema_id": "kolibri.product.agui.projection"; readonly "schema_version": "1.0"; readonly "tenant_id": string; readonly "thread_id": string; readonly "run_id": string; readonly "source_event_id": string; readonly "source_sequence": number; readonly "protocol": "ag-ui"; readonly "protocol_version": "0.0.57"; readonly "adapter_package": "@assistant-ui/react-ag-ui"; readonly "adapter_version": "0.0.45"; readonly "event_type": "RUN_STARTED" | "RUN_FINISHED" | "RUN_CANCELLED" | "RUN_ERROR" | "TEXT_MESSAGE_START" | "TEXT_MESSAGE_CONTENT" | "TEXT_MESSAGE_END" | "TEXT_MESSAGE_CHUNK" | "TOOL_CALL_START" | "TOOL_CALL_ARGS" | "TOOL_CALL_END" | "TOOL_CALL_CHUNK" | "TOOL_CALL_RESULT" | "STATE_SNAPSHOT" | "STATE_DELTA" | "MESSAGES_SNAPSHOT" | "CUSTOM"; readonly "custom_schema_id": string | null; readonly "custom_schema_version": string | null; readonly "payload": Readonly<Record<string, unknown>>; readonly "projected_at": string; }

export type KolibriProductAttachment = { readonly "schema_id": "kolibri.product.attachment"; readonly "schema_version": "1.0"; readonly "tenant_id": string; readonly "user_id": string; readonly "project_id": string; readonly "attachment_id": string; readonly "artifact_id": string; readonly "artifact_version": number; readonly "content_hash": string; readonly "filename": string; readonly "mime_type": string; readonly "size_bytes": number; readonly "content_path": string; readonly "status": "available"; readonly "created_by": string; readonly "created_at": string; }

export type KolibriProductDeliveryCursor = { readonly "schema_id": "kolibri.product.delivery_cursor"; readonly "schema_version": "1.0"; readonly "tenant_id": string; readonly "user_id": string; readonly "project_id": string; readonly "thread_id": string; readonly "run_id": string; readonly "last_sequence": number; readonly "last_event_id": string | null; readonly "ledger_version": number; readonly "issued_at": string; }

export type KolibriProductDeveloperDispatch = { readonly "schema_id": "kolibri.product.developer_dispatch"; readonly "schema_version": "1.0"; readonly "source_command_ref": string; readonly "run_id": string; readonly "project_id": string; readonly "thread_id": string; readonly "input_message_id": string; readonly "runtime_profile": string; readonly "runtime_capability": string; readonly "model": string | null; readonly "reasoning_effort": string | null; readonly "service_tier": string | null; readonly "workspace_ref": string; readonly "access_mode": "auto" | "full"; readonly "sandbox": "workspace-write" | "danger-full-access"; readonly "approval_policy": "on-request" | "never"; readonly "reviewer": string | null; }

export type KolibriProductDeveloperDispatchV11 = { readonly "schema_id": "kolibri.product.developer_dispatch.v1_1"; readonly "schema_version": "1.1"; readonly "source_command_ref": string; readonly "run_id": string; readonly "project_id": string; readonly "thread_id": string; readonly "input_message_id": string; readonly "runtime_profile": string; readonly "runtime_capability": string; readonly "model": string | null; readonly "reasoning_effort": string | null; readonly "service_tier": string | null; readonly "workspace_ref": string; readonly "access_mode": "full"; readonly "sandbox": "danger-full-access"; readonly "approval_policy": "never"; readonly "reviewer": null; readonly "trusted_agent_profile_id": string; readonly "trusted_agent_profile_epoch": number; readonly "trusted_agent_workspace_binding_id": string; readonly "trusted_agent_workspace_binding_epoch": number; }

export type KolibriProductDeveloperLeaseSource = { readonly "schema_id": "kolibri.product.developer_lease_source"; readonly "schema_version": "1.0"; readonly "source_command_ref": string; readonly "canonical_request_hash": string; readonly "source_command_hash": string; readonly "tenant_id": string; readonly "task_id": string; readonly "task_version": number; readonly "attempt_id": string; readonly "assignment_id": string; readonly "effect_id": string; readonly "lease_id": string; readonly "fencing_token": number; readonly "runtime_profile": string; readonly "access_policy": { readonly "policy_id": string; readonly "tool_ids": ReadonlyArray<string>; readonly "compute_units_limit": number; readonly "tool_calls_limit": number; }; }

export type KolibriProductDeveloperLeaseSourceV11 = { readonly "schema_id": "kolibri.product.developer_lease_source.v1_1"; readonly "schema_version": "1.1"; readonly "source_command_ref": string; readonly "canonical_request_hash": string; readonly "source_command_hash": string; readonly "tenant_id": string; readonly "task_id": string; readonly "task_version": number; readonly "attempt_id": string; readonly "assignment_id": string; readonly "effect_id": string; readonly "lease_id": string; readonly "fencing_token": number; readonly "runtime_profile": string; readonly "access_policy": { readonly "policy_id": string; readonly "tool_ids": ReadonlyArray<string>; readonly "compute_units_limit": number; readonly "tool_calls_limit": number; }; readonly "trusted_agent_profile_id": string; readonly "trusted_agent_profile_epoch": number; readonly "trusted_agent_workspace_binding_id": string; readonly "trusted_agent_workspace_binding_epoch": number; }

export type KolibriProductDeveloperSourceCommand = { readonly "schema_id": "kolibri.product.developer_source_command"; readonly "schema_version": "1.0"; readonly "source_command_ref": string; readonly "tenant_id": string; readonly "goal_id": string; readonly "case_id": string; readonly "run_id": string; readonly "task_id": string; readonly "graph_id": string; readonly "request_hash": string; readonly "command_hash": string; readonly "requested_runtime_profile": string; readonly "runtime_profile": string; readonly "runtime_capability": string; readonly "access_policy": { readonly "policy_id": string; readonly "tool_ids": ReadonlyArray<string>; readonly "compute_units_limit": number; readonly "tool_calls_limit": number; }; readonly "state": "reserved" | "ready"; readonly "source_command": KolibriCommand; }

export type KolibriProductGoalInitializationStatus = { readonly "schema_id": "kolibri.product.goal.initialization_status"; readonly "schema_version": "1.0"; readonly "run_id": string; readonly "goal_id": string; readonly "case_id": string; readonly "status": "initialized" | "failed"; readonly "goal_version": number | null; readonly "case_version": number | null; readonly "error": KolibriError | null; }

export type KolibriProductGoalInitializeCommand = { readonly "schema_id": "kolibri.product.goal.initialize.command"; readonly "schema_version": "1.0"; readonly "tenant_id": string; readonly "project_id": string; readonly "thread_id": string; readonly "run_id": string; readonly "input_message_id": string; readonly "goal_id": string; readonly "prompt": string; readonly "prompt_hash": string; }

export type KolibriProductInterrupt = { readonly "schema_id": "kolibri.product.interrupt"; readonly "schema_version": "1.0"; readonly "tenant_id": string; readonly "project_id": string; readonly "thread_id": string; readonly "run_id": string; readonly "interrupt_id": string; readonly "interrupt_version": number; readonly "state": "pending" | "answered" | "expired" | "cancelled"; readonly "kind": "clarification" | "approval" | "missing_source" | "conflict"; readonly "prompt": string; readonly "response_schema_id": string; readonly "response_schema_version": string; readonly "required_authority": "user" | "project_manager" | "estimator" | "finance" | "owner"; readonly "answer_message_id": string | null; readonly "created_at": string; readonly "updated_at": string; readonly "expires_at": string; }

export type KolibriProductMessage = { readonly "schema_id": "kolibri.product.message"; readonly "schema_version": "1.0"; readonly "tenant_id": string; readonly "project_id": string; readonly "thread_id": string; readonly "message_id": string; readonly "sequence": number; readonly "parent_message_id": string | null; readonly "branch_id": string; readonly "run_id": string | null; readonly "role": "user" | "assistant" | "system"; readonly "author_actor_id": string; readonly "status": "committed" | "superseded" | "redacted"; readonly "parts": ReadonlyArray<{ readonly "part_id": string; readonly "type": "text"; readonly "format": "plain" | "markdown"; readonly "text": string; } | { readonly "part_id": string; readonly "type": "attachment_ref"; readonly "tenant_id": string; readonly "artifact_id": string; readonly "artifact_version": number; readonly "content_hash": string; readonly "filename": string; readonly "mime_type": string; readonly "size_bytes": number; } | { readonly "part_id": string; readonly "type": "tool_call_ref"; readonly "tool_call_id": string; readonly "tool_name": string; readonly "input_schema_id": string; readonly "input_schema_version": string; readonly "input_hash": string; } | { readonly "part_id": string; readonly "type": "tool_result_ref"; readonly "tool_call_id": string; readonly "result_schema_id": string; readonly "result_schema_version": string; readonly "result_hash": string; } | { readonly "part_id": string; readonly "type": "artifact_ref"; readonly "tenant_id": string; readonly "artifact_id": string; readonly "artifact_version": number; readonly "content_hash": string; readonly "artifact_kind": string; } | { readonly "part_id": string; readonly "type": "citation_ref"; readonly "source_id": string; readonly "source_version": number; readonly "content_hash": string; readonly "label": string; readonly "locator": string; } | { readonly "part_id": string; readonly "type": "interrupt_ref"; readonly "interrupt_id": string; readonly "interrupt_version": number; }>; readonly "version": number; readonly "created_at": string; readonly "committed_at": string; }

export type KolibriProductProject = { readonly "schema_id": "kolibri.product.project"; readonly "schema_version": "1.0"; readonly "tenant_id": string; readonly "project_id": string; readonly "case_id": string; readonly "goal_id": string | null; readonly "name": string; readonly "status": "active" | "archived" | "deleted"; readonly "default_thread_id": string | null; readonly "version": number; readonly "created_by": string; readonly "created_at": string; readonly "updated_at": string; }

export type KolibriProductProjectCreateRequest = { readonly "schema_id": "kolibri.product.project_create_request"; readonly "schema_version": "1.0"; readonly "name": string; }

export type KolibriProductProviderEnrollmentIntentCommand = { readonly "schema_id": "kolibri.product.provider.enrollment_intent.command"; readonly "schema_version": "1.0"; readonly "tenant_id": string; readonly "intent_id": string; readonly "provider_id": "mimo-code" | "codex-cli"; readonly "requested_by_user_id": string; readonly "owner_authorization_decision_id": string; readonly "purpose": "owner_provider_enrollment"; readonly "requested_at": string; }

export type KolibriProductProviderEnrollmentStatus = { readonly "schema_id": "kolibri.product.provider.enrollment_status"; readonly "schema_version": "1.0"; readonly "tenant_id": string; readonly "intent_id": string; readonly "provider_id": "mimo-code" | "codex-cli"; readonly "status": "connected" | "failed"; readonly "observed_at": string; readonly "auth_flow_supported": boolean; readonly "last_verified_at": string | null; readonly "evidence_hash": string | null; readonly "error": KolibriError | null; }

export type KolibriProductRun = { readonly "schema_id": "kolibri.product.run"; readonly "schema_version": "1.0"; readonly "tenant_id": string; readonly "project_id": string; readonly "thread_id": string; readonly "run_id": string; readonly "run_sequence": number; readonly "input_message_id": string; readonly "retry_of_run_id": string | null; readonly "resume_of_run_id": string | null; readonly "case_id": string; readonly "goal_id": string | null; readonly "home_task_id": string | null; readonly "lifecycle": "accepted" | "running" | "cancellation_requested" | "finished"; readonly "outcome": "success" | "interrupt" | "failure" | "cancelled" | null; readonly "last_event_sequence": number; readonly "last_event_id": string | null; readonly "active_interrupt_ids": ReadonlyArray<string>; readonly "version": number; readonly "created_by": string; readonly "created_at": string; readonly "updated_at": string; readonly "finished_at": string | null; }

export type KolibriProductRunEvent = { readonly "schema_id": "kolibri.product.run.event"; readonly "schema_version": "1.0"; readonly "tenant_id": string; readonly "project_id": string; readonly "thread_id": string; readonly "run_id": string; readonly "event_id": string; readonly "sequence": number; readonly "event_type": "run_started" | "safe_progress" | "message_part_delta" | "message_part_committed" | "tool_started" | "tool_finished" | "artifact_referenced" | "interrupt_created" | "invalidation" | "heartbeat" | "run_finished" | "run_error"; readonly "payload_schema_id": string; readonly "payload_schema_version": string; readonly "payload": Readonly<Record<string, unknown>>; readonly "trace": { readonly "trace_id": string; readonly "span_id": string; readonly "parent_span_id": string | null; readonly "correlation_id": string; readonly "causation_id": string | null; }; readonly "source_task_id": string | null; readonly "source_event_id": string | null; readonly "occurred_at": string; readonly "recorded_at": string; }

export type KolibriProductRunExecuteCommand = { readonly "schema_id": "kolibri.product.run.execute.command"; readonly "schema_version": "1.0"; readonly "tenant_id": string; readonly "project_id": string; readonly "thread_id": string; readonly "run_id": string; readonly "input_message_id": string; readonly "case_id": string; readonly "goal_id": string; readonly "prompt": string; readonly "prompt_hash": string; readonly "preferred_agent_profile": "auto" | "mimo-code" | "codex-cli"; }

export type KolibriProductRunExecuteV11Command = ({ readonly "schema_id": "kolibri.product.run.execute.v1_1.command"; readonly "schema_version": "1.1"; readonly "tenant_id": string; readonly "project_id": string; readonly "thread_id": string; readonly "run_id": string; readonly "input_message_id": string; readonly "case_id": string; readonly "goal_id": string; readonly "prompt": string; readonly "prompt_hash": string; readonly "preferred_agent_profile": string; readonly "preferred_model": string | null; readonly "preferred_reasoning_effort": string | null; }) & ({ readonly "preferred_model": string; readonly "preferred_reasoning_effort": string; } | { readonly "preferred_model": null; readonly "preferred_reasoning_effort": null; })

export type KolibriProductRunExecuteV12Command = { readonly "schema_id": "kolibri.product.run.execute.v1_2.command"; readonly "schema_version": "1.2"; readonly "tenant_id": string; readonly "project_id": string; readonly "thread_id": string; readonly "run_id": string; readonly "input_message_id": string; readonly "case_id": string; readonly "goal_id": string; readonly "prompt": string; readonly "prompt_hash": string; readonly "execution_mode": "developer"; readonly "runtime_profile": string; readonly "model": string | null; readonly "reasoning_effort": string | null; readonly "service_tier": string | null; readonly "workspace_ref": string; readonly "access_mode": "auto" | "full"; readonly "sandbox": "workspace-write" | "danger-full-access"; readonly "approval_policy": "on-request" | "never"; readonly "reviewer": string | null; readonly "requester_role": "owner"; }

export type KolibriProductRunExecuteV13Command = { readonly "schema_id": "kolibri.product.run.execute.v1_3.command"; readonly "schema_version": "1.3"; readonly "tenant_id": string; readonly "project_id": string; readonly "thread_id": string; readonly "run_id": string; readonly "input_message_id": string; readonly "case_id": string; readonly "goal_id": string; readonly "prompt": string; readonly "prompt_hash": string; readonly "execution_mode": "developer"; readonly "runtime_profile": string; readonly "model": string | null; readonly "reasoning_effort": string | null; readonly "service_tier": string | null; readonly "workspace_ref": string; readonly "access_mode": "full"; readonly "sandbox": "danger-full-access"; readonly "approval_policy": "never"; readonly "reviewer": null; readonly "requester_role": "owner"; readonly "trusted_agent_profile_id": string; readonly "trusted_agent_profile_epoch": number; readonly "trusted_agent_workspace_binding_id": string; readonly "trusted_agent_workspace_binding_epoch": number; }

export type KolibriProductRunExecutionStatus = { readonly "schema_id": "kolibri.product.run.execution_status"; readonly "schema_version": "1.0"; readonly "run_id": string; readonly "status": "accepted" | "running" | "succeeded" | "failed"; readonly "profile": "mimo-code" | "codex-cli"; readonly "execution_id": string; readonly "verification_status": "not_applicable" | "unverified" | "verified"; readonly "result_text": string | null; readonly "result_hash": string | null; readonly "evidence": { readonly "evidence_id": string; readonly "evidence_version": number; readonly "content_hash": string; } | null; readonly "error": KolibriError | null; }

export type KolibriProductRunExecutionStatusV11 = { readonly "schema_id": "kolibri.product.run.execution_status.v1_1"; readonly "schema_version": "1.1"; readonly "run_id": string; readonly "status": "accepted" | "running" | "succeeded" | "failed"; readonly "runtime_profile": string; readonly "execution_id": string; readonly "verification_status": "not_applicable" | "unverified" | "verified"; readonly "result_text": string | null; readonly "result_hash": string | null; readonly "evidence": { readonly "evidence_id": string; readonly "evidence_version": number; readonly "content_hash": string; } | null; readonly "error": KolibriError | null; }

export type KolibriProductSession = { readonly "schema_id": "kolibri.product.session"; readonly "schema_version": "1.0"; readonly "tenant_id": string; readonly "user_id": string; readonly "session_kind": "anonymous" | "authenticated"; readonly "expires_at": string | null; readonly "product_api_version": "v1"; readonly "capabilities": ReadonlyArray<string>; }

export type KolibriProductTextRunRequest = { readonly "schema_id": "kolibri.product.text_run_request"; readonly "schema_version": "1.0"; readonly "expected_thread_version": number; readonly "parent_message_id": string | null; readonly "parts": ReadonlyArray<{ readonly "part_id": string; readonly "type": "text"; readonly "format": "plain" | "markdown"; readonly "text": string; } | { readonly "part_id": string; readonly "type": "attachment_ref"; readonly "tenant_id": string; readonly "artifact_id": string; readonly "artifact_version": number; readonly "content_hash": string; readonly "filename": string; readonly "mime_type": string; readonly "size_bytes": number; } | { readonly "part_id": string; readonly "type": "tool_call_ref"; readonly "tool_call_id": string; readonly "tool_name": string; readonly "input_schema_id": string; readonly "input_schema_version": string; readonly "input_hash": string; } | { readonly "part_id": string; readonly "type": "tool_result_ref"; readonly "tool_call_id": string; readonly "result_schema_id": string; readonly "result_schema_version": string; readonly "result_hash": string; } | { readonly "part_id": string; readonly "type": "artifact_ref"; readonly "tenant_id": string; readonly "artifact_id": string; readonly "artifact_version": number; readonly "content_hash": string; readonly "artifact_kind": string; } | { readonly "part_id": string; readonly "type": "citation_ref"; readonly "source_id": string; readonly "source_version": number; readonly "content_hash": string; readonly "label": string; readonly "locator": string; } | { readonly "part_id": string; readonly "type": "interrupt_ref"; readonly "interrupt_id": string; readonly "interrupt_version": number; }>; readonly "preferred_agent_profile": "auto" | "mimo-code" | "codex-cli"; }

export type KolibriProductThread = { readonly "schema_id": "kolibri.product.thread"; readonly "schema_version": "1.0"; readonly "tenant_id": string; readonly "project_id": string; readonly "thread_id": string; readonly "title": string; readonly "status": "active" | "archived" | "deleted"; readonly "branch_count": number; readonly "last_message_sequence": number; readonly "last_run_sequence": number; readonly "version": number; readonly "created_by": string; readonly "created_at": string; readonly "updated_at": string; }

export type KolibriProductThreadUpdateRequest = { readonly "schema_id": "kolibri.product.thread_update_request"; readonly "schema_version": "1.0"; readonly "expected_thread_version": number; readonly "title": string; }

export type KolibriProjectCase = { readonly "schema_id": "kolibri.project_case"; readonly "schema_version": "1.0"; readonly "case_id": string; readonly "goal_id": string; readonly "goal_version": number; readonly "tenant_id": string; readonly "status": "draft" | "intake" | "working" | "blocked" | "review" | "approved_internal" | "released" | "superseded" | "closed"; readonly "version": number; readonly "event_sequence": number; readonly "intent_snapshot": { readonly "goal_version": number; readonly "normalized_objective": string; }; readonly "acceptance_criterion_ids": ReadonlyArray<string>; readonly "facts": ReadonlyArray<{ readonly "fact_id": string; readonly "key": string; readonly "value": unknown; readonly "value_type": "text" | "number" | "boolean" | "date" | "quantity" | "reference" | "json"; readonly "unit": string | null; readonly "source": { readonly "source_type": "user_message" | "uploaded_document" | "measurement" | "domain_artifact" | "external_registry" | "human_confirmation"; readonly "reference_id": string; readonly "locator": string; readonly "observed_at": string; }; readonly "confidence": number; readonly "status": "active" | "refuted" | "superseded"; readonly "recorded_at": string; readonly "superseded_by": string | null; }>; readonly "assumptions": ReadonlyArray<{ readonly "assumption_id": string; readonly "statement": string; readonly "rationale": string; readonly "confidence": number; readonly "impact": { readonly "severity": "low" | "medium" | "high" | "critical"; readonly "summary": string; }; readonly "allowed_until_stage": "concept" | "estimate_draft" | "internal_review" | "release"; readonly "owner_actor_id": string; readonly "status": "proposed" | "active" | "confirmed" | "rejected" | "superseded"; readonly "invalidation_targets": ReadonlyArray<string>; readonly "created_at": string; readonly "superseded_by": string | null; }>; readonly "proposals": ReadonlyArray<{ readonly "proposal_id": string; readonly "question": string; readonly "option": string; readonly "rationale": string; readonly "evidence_refs": ReadonlyArray<string>; readonly "status": "open" | "selected" | "rejected" | "superseded"; readonly "created_by_actor_id": string; readonly "created_at": string; }>; readonly "decisions": ReadonlyArray<{ readonly "decision_id": string; readonly "question": string; readonly "alternatives": ReadonlyArray<string>; readonly "selected_option": string; readonly "selected_proposal_id": string | null; readonly "evidence_refs": ReadonlyArray<string>; readonly "authority_decision_id": string; readonly "made_by_actor_id": string; readonly "effective_case_version": number; readonly "consequences": ReadonlyArray<string>; readonly "decided_at": string; readonly "supersedes_decision_id": string | null; }>; readonly "open_questions": ReadonlyArray<{ readonly "question_id": string; readonly "question": string; readonly "reason": string; readonly "blocking": boolean; readonly "answer_type": "text" | "number" | "boolean" | "single_choice" | "multiple_choice" | "document"; readonly "options": ReadonlyArray<string>; readonly "status": "open" | "answered" | "waived"; readonly "owner_actor_id": string; readonly "answer_ref": string | null; readonly "created_at": string; readonly "resolved_at": string | null; }>; readonly "requirements": ReadonlyArray<{ readonly "item_id": string; readonly "statement": string; readonly "source_ref": string; readonly "status": "active" | "satisfied" | "violated" | "superseded"; }>; readonly "constraints": ReadonlyArray<{ readonly "item_id": string; readonly "statement": string; readonly "source_ref": string; readonly "status": "active" | "satisfied" | "violated" | "superseded"; }>; readonly "domain_refs": ReadonlyArray<{ readonly "ref_type": string; readonly "ref_id": string; readonly "version": number; }>; readonly "created_at": string; readonly "updated_at": string; }

export type KolibriProjectCaseTransitionCommand = { readonly "schema_id": "kolibri.project_case.transition.command"; readonly "schema_version": "1.0"; readonly "case_id": string; readonly "expected_version": number; readonly "next_version": number; readonly "from_status": "draft" | "intake" | "working" | "blocked" | "review" | "approved_internal" | "released" | "superseded" | "closed"; readonly "to_status": "draft" | "intake" | "working" | "blocked" | "review" | "approved_internal" | "released" | "superseded" | "closed"; readonly "reason": string; readonly "requested_at": string; }

export type KolibriProjectWorkflow = { readonly "schema_id": "kolibri.project_workflow"; readonly "schema_version": "1.0"; readonly "workflow_id": string; readonly "tenant_id": string; readonly "goal_id": string; readonly "case_id": string; readonly "workflow_type": "project" | "child" | "child.retry" | "child.review"; readonly "parent_workflow_id"?: string | null; readonly "status": "running" | "waiting_signal" | "waiting_query" | "waiting_timer" | "cancelling" | "completed" | "failed" | "cancelled" | "superseded"; readonly "version": number; readonly "graph_id": string; readonly "graph_version": number; readonly "activity_count": number; readonly "signal_count": number; readonly "query_count": number; readonly "timer_count": number; readonly "activities": ReadonlyArray<{ readonly "activity_id": string; readonly "task_id": string; readonly "activity_type": string; readonly "status": "queued" | "assigned" | "running" | "waiting_signal" | "waiting_timer" | "succeeded" | "failed" | "cancelled" | "superseded"; readonly "execution_attempt": number; readonly "execution_attempt_id"?: string | null; readonly "assigned_node"?: string | null; readonly "started_at": string; readonly "updated_at": string; }>; readonly "pending_signals": ReadonlyArray<{ readonly "signal_id": string; readonly "signal_type": "user_change" | "approval" | "payment" | "policy_change" | "cancellation"; readonly "status": "queued" | "applied" | "ignored" | "rejected" | "failed"; readonly "received_at": string; }>; readonly "open_queries": ReadonlyArray<{ readonly "query_id": string; readonly "query_type": "task_projection" | "artifact_state" | "owner_state" | "telemetry"; readonly "status": "queued" | "in_progress" | "served" | "failed"; readonly "requested_at": string; }>; readonly "timers": ReadonlyArray<{ readonly "timer_id": string; readonly "timer_type": "lease_expiry" | "retry_backoff" | "deadline_policy"; readonly "scheduled_at": string; readonly "status": "waiting" | "fired" | "cancelled"; readonly "fired_at"?: string | null; }>; readonly "created_at": string; readonly "updated_at": string; }

export type KolibriProviderExecutionCatalog = { readonly "schema_id": "kolibri.provider_execution.catalog"; readonly "schema_version": "1.0"; readonly "agent_cards": ReadonlyArray<KolibriAgentCard>; }

export type KolibriProviderExecutionRequest = { readonly "schema_id": "kolibri.provider_execution.request"; readonly "schema_version": "1.0"; readonly "effect_key": string; readonly "task": KolibriTask; readonly "attempt": KolibriTaskAttempt; readonly "agent_assignment": KolibriAgentAssignment; readonly "requester_assignment": KolibriAgentAssignment; readonly "a2a_request": KolibriA2aMessageAppendedEvent; readonly "developer_dispatch": KolibriProductDeveloperDispatch | KolibriProductDeveloperDispatchV11; readonly "source_command": KolibriCommand; readonly "lease_source": KolibriProductDeveloperLeaseSource | KolibriProductDeveloperLeaseSourceV11; }

export type KolibriProviderExecutionResult = { readonly "schema_id": "kolibri.provider_execution.result"; readonly "schema_version": "1.0"; readonly "effect_key": string; readonly "request_hash": string; readonly "task_id": string; readonly "attempt_id": string; readonly "assignment_id": string; readonly "lease_id": string; readonly "fencing_token": number; readonly "runtime_profile": string; readonly "status": "completed" | "failed"; readonly "replayed": boolean; readonly "output": ({ readonly "response": string | null; readonly "session_id": string | null; readonly "tool_call": { readonly "name": string; readonly "arguments": Readonly<Record<string, unknown>>; } | null; }) & ({ readonly "response"?: string; readonly "tool_call"?: null; } | { readonly "response"?: null; readonly "tool_call"?: Readonly<Record<string, unknown>>; }) | null; readonly "activity": ReadonlyArray<{ readonly "phase": string; readonly "payload": Readonly<Record<string, unknown>>; }>; readonly "error": { readonly "code": string; readonly "category": "configuration" | "authentication" | "unavailable" | "invalid_output" | "execution"; readonly "retryable": boolean; readonly "safe_message": string; } | null; }

export type KolibriReview = { readonly "schema_id": "kolibri.review"; readonly "schema_version": "1.0"; readonly "review_id": string; readonly "review_version": number; readonly "tenant_id": string; readonly "goal_id": string; readonly "case_id": string; readonly "task_id": string; readonly "artifact_ref": { readonly "artifact_id": string; readonly "artifact_version": number; readonly "content_hash": string; }; readonly "author_actor_id": string; readonly "reviewer_actor_id": string; readonly "reviewer_assignment_id": string; readonly "scope": ReadonlyArray<"technical" | "commercial" | "legal" | "quality" | "security" | "release">; readonly "criteria": ReadonlyArray<{ readonly "criterion_id": string; readonly "result": "passed" | "failed" | "not_applicable" | "inconclusive"; readonly "evidence_refs": ReadonlyArray<{ readonly "ref_id": string; readonly "version": number; }>; }>; readonly "evidence_refs": ReadonlyArray<{ readonly "ref_id": string; readonly "version": number; }>; readonly "findings": ReadonlyArray<{ readonly "finding_id": string; readonly "severity": "info" | "low" | "medium" | "high" | "critical"; readonly "category": string; readonly "statement": string; readonly "artifact_locator": string; readonly "evidence_refs": ReadonlyArray<{ readonly "ref_id": string; readonly "version": number; }>; readonly "required_action": string; readonly "owner_ref": string; readonly "status": "open" | "accepted_risk" | "resolved" | "superseded"; readonly "resolution": { readonly "disposition": "fixed" | "not_reproducible" | "accepted_risk" | "superseded"; readonly "resolved_by": string; readonly "resolved_at": string; readonly "evidence_refs": ReadonlyArray<{ readonly "ref_id": string; readonly "version": number; }>; } | null; }>; readonly "disposition": "pending" | "changes_requested" | "rejected" | "accepted_with_conditions" | "approved_internal"; readonly "status": "open" | "completed" | "superseded" | "stale" | "revoked"; readonly "requested_at": string; readonly "completed_at": string | null; readonly "supersedes": { readonly "ref_id": string; readonly "version": number; } | null; }

export type KolibriSignoff = { readonly "schema_id": "kolibri.signoff"; readonly "schema_version": "1.0"; readonly "signoff_id": string; readonly "signoff_version": number; readonly "tenant_id": string; readonly "goal_id": string; readonly "case_id": string; readonly "artifact_ref": { readonly "artifact_id": string; readonly "artifact_version": number; readonly "content_hash": string; }; readonly "signoff_type": "internal_approval" | "corporate_release_authorization" | "qualified_human_signoff" | "client_acceptance"; readonly "signer": { readonly "actor_id": string; readonly "actor_type": "human" | "agent" | "service"; readonly "credential_ref": string | null; }; readonly "authority_basis_ref": string; readonly "policy_decision": { readonly "decision_id": string; readonly "policy_version": string; readonly "effect": "allow"; }; readonly "review_refs": ReadonlyArray<{ readonly "ref_id": string; readonly "version": number; }>; readonly "signature_ref": string | null; readonly "status": "granted" | "revoked" | "stale" | "superseded"; readonly "granted_at": string; readonly "revocation": { readonly "reason": string; readonly "revoked_by": string; readonly "revoked_at": string; } | null; readonly "supersedes": { readonly "ref_id": string; readonly "version": number; } | null; }

export type KolibriTask = { readonly "schema_id": "kolibri.task"; readonly "schema_version": "1.0"; readonly "task_id": string; readonly "tenant_id": string; readonly "goal_id": string; readonly "case_id": string; readonly "title": string; readonly "objective": string; readonly "kind": string; readonly "parent_task_id"?: string | null; readonly "dependency_task_ids": ReadonlyArray<string>; readonly "required_capabilities": ReadonlyArray<string>; readonly "acceptance_criteria": ReadonlyArray<{ readonly "criterion_id": string; readonly "statement": string; readonly "verification_method": string; readonly "required": boolean; }>; readonly "expected_outputs": ReadonlyArray<{ readonly "output_id": string; readonly "artifact_type": string; readonly "schema_id": string; readonly "evidence_required": boolean; }>; readonly "budget": { readonly "compute_units_limit": number; readonly "tool_calls_limit": number; readonly "external_spend_limit_minor": number; readonly "currency": string; }; readonly "deadline_at": string | null; readonly "risk_class": "low" | "medium" | "high" | "critical"; readonly "state": "proposed" | "accepted" | "ready" | "leased" | "running" | "submitted" | "verifying" | "blocked" | "revision_requested" | "failed_retryable" | "completed" | "failed_terminal" | "cancelled" | "superseded"; readonly "graph_version": number; readonly "version": number; readonly "current_attempt_id": string | null; readonly "current_assignment_id": string | null; readonly "created_at": string; readonly "updated_at": string; }

export type KolibriTaskTransitionCommand = { readonly "schema_id": "kolibri.task.transition.command"; readonly "schema_version": "1.0"; readonly "task_id": string; readonly "expected_version": number; readonly "next_version": number; readonly "from_status": "proposed" | "accepted" | "ready" | "leased" | "running" | "submitted" | "verifying" | "blocked" | "revision_requested" | "failed_retryable" | "completed" | "failed_terminal" | "cancelled" | "superseded"; readonly "to_status": "proposed" | "accepted" | "ready" | "leased" | "running" | "submitted" | "verifying" | "blocked" | "revision_requested" | "failed_retryable" | "completed" | "failed_terminal" | "cancelled" | "superseded"; readonly "attempt_id": string | null; readonly "assignment_id": string | null; readonly "lease_id": string | null; readonly "fencing_token": number | null; readonly "reason": string; readonly "requested_at": string; }

export type KolibriTaskAttempt = { readonly "schema_id": "kolibri.task_attempt"; readonly "schema_version": "1.0"; readonly "attempt_id": string; readonly "tenant_id": string; readonly "goal_id": string; readonly "case_id": string; readonly "task_id": string; readonly "attempt_number": number; readonly "assignment_id": string; readonly "status": "created" | "leased" | "running" | "submitted" | "verifying" | "completed" | "failed_retryable" | "failed_terminal" | "expired" | "cancelled"; readonly "lease": { readonly "lease_id": string; readonly "authority_id": string; readonly "authority_epoch": number; readonly "fencing_token": number; readonly "worker_id": string; readonly "agent_card_id": string; readonly "acquired_at": string; readonly "heartbeat_at": string; readonly "expires_at": string; }; readonly "effect_id": string; readonly "result_artifact_refs": ReadonlyArray<string>; readonly "result_hash": string | null; readonly "error": { readonly "error_type": string; readonly "message": string; readonly "retryable": boolean; } | null; readonly "created_at": string; readonly "updated_at": string; }

export type KolibriTaskGraph = { readonly "schema_id": "kolibri.task_graph"; readonly "schema_version": "1.0"; readonly "graph_id": string; readonly "tenant_id": string; readonly "goal_id": string; readonly "case_id": string; readonly "graph_version": number; readonly "tasks": ReadonlyArray<KolibriTask>; readonly "relations": ReadonlyArray<{ readonly "task_id": string; readonly "parent_task_id": string | null; readonly "child_task_ids": ReadonlyArray<string>; readonly "dependency_task_ids": ReadonlyArray<string>; readonly "dependent_task_ids": ReadonlyArray<string>; readonly "blocked_by_task_ids": ReadonlyArray<string>; readonly "runnable": boolean; }>; readonly "topological_task_ids": ReadonlyArray<string>; readonly "runnable_task_ids": ReadonlyArray<string>; readonly "created_at": string; readonly "updated_at": string; }

export type KolibriTaskGraphApplyCommand = { readonly "schema_id": "kolibri.task_graph.apply.command"; readonly "schema_version": "1.0"; readonly "graph_id": string; readonly "tenant_id": string; readonly "goal_id": string; readonly "case_id": string; readonly "expected_graph_version": number; readonly "next_graph_version": number; readonly "tasks": ReadonlyArray<KolibriTask>; readonly "reason": string; readonly "requested_at": string; }

export type KolibriTaskGraphChangedEvent = { readonly "schema_id": "kolibri.task_graph.changed.event"; readonly "schema_version": "1.0"; readonly "graph_id": string; readonly "tenant_id": string; readonly "goal_id": string; readonly "case_id": string; readonly "previous_graph_version": number | null; readonly "new_graph_version": number; readonly "task_count": number; readonly "runnable_task_ids": ReadonlyArray<string>; }

export type KolibriTaskOwnerState = { readonly "schema_id": "kolibri.task_owner_state"; readonly "schema_version": "1.0"; readonly "tenant_id": string; readonly "task_id": string; readonly "task_version": number; readonly "current_status": "proposed" | "accepted" | "ready" | "leased" | "running" | "submitted" | "verifying" | "blocked" | "revision_requested" | "failed_retryable" | "completed" | "failed_terminal" | "cancelled" | "superseded"; readonly "current_attempt_id": string; readonly "current_assignment_id": string; readonly "lease_id": string; readonly "authority_id": string; readonly "authority_epoch": number; readonly "fencing_token": number; readonly "lease_expires_at": string; readonly "committed_effects": Readonly<Record<string, { readonly "attempt_id": string; readonly "result_hash": string; }>>; }

export type KolibriWorkflowQuery = { readonly "schema_id": "kolibri.workflow.query"; readonly "schema_version": "1.0"; readonly "workflow_id": string; readonly "query_id": string; readonly "query_type": "task_projection" | "artifact_state" | "owner_state" | "telemetry"; readonly "query_scope"?: string | null; readonly "requested_at": string; readonly "response_contract_id"?: string; }

export type KolibriWorkflowSignal = { readonly "schema_id": "kolibri.workflow.signal"; readonly "schema_version": "1.0"; readonly "workflow_id": string; readonly "signal_id": string; readonly "signal_type": "user_change" | "approval" | "payment" | "policy_change" | "cancellation"; readonly "source": string; readonly "payload_hash": string; readonly "requested_at": string; }

export type KolibriWorkflowTimer = { readonly "schema_id": "kolibri.workflow.timer"; readonly "schema_version": "1.0"; readonly "workflow_id": string; readonly "timer_id": string; readonly "timer_type": "lease_expiry" | "retry_backoff" | "deadline_policy" | "poll_interval"; readonly "scheduled_at": string; readonly "status": "waiting" | "fired" | "cancelled" | "rescheduled"; readonly "fired_at"?: string | null; }

export type KolibriWorkflowVersionTransitionCommand = { readonly "schema_id": "kolibri.workflow.version.transition.command"; readonly "schema_version": "1.0"; readonly "workflow_id": string; readonly "expected_version": number; readonly "next_version": number; readonly "reason": string; readonly "requested_at": string; }

export type KolibriContractV1 = KolibriA2aDeliveryCursor | KolibriA2aMessageAppendedEvent | KolibriAgentAssignment | KolibriAgentAssignmentStatusChangedEvent | KolibriAgentCard | KolibriArtifact | KolibriArtifactStateTransitionCommand | KolibriArtifactQualityManifest | KolibriArtifactState | KolibriCommand | KolibriDocumentData | KolibriDocumentRenderRequest | KolibriDocumentRenderResult | KolibriDocumentTemplate | KolibriDocumentTemplateRegistry | KolibriError | KolibriEvent | KolibriEvidence | KolibriGoal | KolibriGoalChangedEvent | KolibriGoalCreateCommand | KolibriGoalTransitionCommand | KolibriGoalUpdateCommand | KolibriProductAguiProjection | KolibriProductAttachment | KolibriProductDeliveryCursor | KolibriProductDeveloperDispatch | KolibriProductDeveloperDispatchV11 | KolibriProductDeveloperLeaseSource | KolibriProductDeveloperLeaseSourceV11 | KolibriProductDeveloperSourceCommand | KolibriProductGoalInitializationStatus | KolibriProductGoalInitializeCommand | KolibriProductInterrupt | KolibriProductMessage | KolibriProductProject | KolibriProductProjectCreateRequest | KolibriProductProviderEnrollmentIntentCommand | KolibriProductProviderEnrollmentStatus | KolibriProductRun | KolibriProductRunEvent | KolibriProductRunExecuteCommand | KolibriProductRunExecuteV11Command | KolibriProductRunExecuteV12Command | KolibriProductRunExecuteV13Command | KolibriProductRunExecutionStatus | KolibriProductRunExecutionStatusV11 | KolibriProductSession | KolibriProductTextRunRequest | KolibriProductThread | KolibriProductThreadUpdateRequest | KolibriProjectCase | KolibriProjectCaseTransitionCommand | KolibriProjectWorkflow | KolibriProviderExecutionCatalog | KolibriProviderExecutionRequest | KolibriProviderExecutionResult | KolibriReview | KolibriSignoff | KolibriTask | KolibriTaskTransitionCommand | KolibriTaskAttempt | KolibriTaskGraph | KolibriTaskGraphApplyCommand | KolibriTaskGraphChangedEvent | KolibriTaskOwnerState | KolibriWorkflowQuery | KolibriWorkflowSignal | KolibriWorkflowTimer | KolibriWorkflowVersionTransitionCommand
export type KolibriContractSchemaId = KolibriContractV1['schema_id']

export const CONTRACT_SPECS = {
  "kolibri.a2a.delivery_cursor": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "channel_id",
      "last_sequence",
      "last_message_id",
      "accepted_messages",
      "deduplication_index"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "channel_id",
      "last_sequence",
      "last_message_id",
      "accepted_messages",
      "deduplication_index"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/a2a/delivery-cursor.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/a2a/delivery-cursor.schema.json",
    "source_sha256": "9f82329aad20d1c972f52a3cfbc9e4c488a7c224153e15d40f46f2ee543710e2"
  },
  "kolibri.a2a.message_appended.event": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "a2a_message_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "task_version",
      "channel_id",
      "sequence",
      "previous_message_id",
      "sender_actor_id",
      "sender_assignment_id",
      "recipient_assignment_ids",
      "recipient_capability",
      "message_type",
      "purpose",
      "response_to_message_id",
      "content",
      "content_hash",
      "deduplication_key",
      "sent_at",
      "expires_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "a2a_message_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "task_version",
      "channel_id",
      "sequence",
      "previous_message_id",
      "sender_actor_id",
      "sender_assignment_id",
      "recipient_assignment_ids",
      "recipient_capability",
      "message_type",
      "purpose",
      "response_to_message_id",
      "content",
      "content_hash",
      "deduplication_key",
      "sent_at",
      "expires_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/a2a/message.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/a2a/message.schema.json",
    "source_sha256": "86a853b28a71cf71cfbbcf012bba2832503ab82271665e3916021ed44fc134ff"
  },
  "kolibri.agent_assignment": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "assignment_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "task_version",
      "attempt_id",
      "assignee_actor_id",
      "agent_card_id",
      "agent_card_version",
      "temporary_role",
      "purpose",
      "authority_profile",
      "context_slice",
      "budget",
      "lease_id",
      "deadline_at",
      "required_output_ids",
      "required_evidence_types",
      "status",
      "version",
      "created_at",
      "updated_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "assignment_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "task_version",
      "attempt_id",
      "assignee_actor_id",
      "agent_card_id",
      "agent_card_version",
      "temporary_role",
      "purpose",
      "authority_profile",
      "context_slice",
      "budget",
      "lease_id",
      "deadline_at",
      "required_output_ids",
      "required_evidence_types",
      "status",
      "version",
      "created_at",
      "updated_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/agents/assignment.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/agents/assignment.schema.json",
    "source_sha256": "af4b6aeffa433d2881c952c35cbc26307426cd78414e7720894cc3a41bd6f684"
  },
  "kolibri.agent_assignment.status_changed.event": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "assignment_id",
      "previous_status",
      "new_status",
      "previous_version",
      "new_version",
      "reason"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "assignment_id",
      "previous_status",
      "new_status",
      "previous_version",
      "new_version",
      "reason"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/agents/assignment-status-changed-event.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/agents/assignment-status-changed-event.schema.json",
    "source_sha256": "6fe9bc9915aa111e288e98c94b3e63fe219b74eca5a02b623c2e7883e7c8f70c"
  },
  "kolibri.agent_card": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "agent_card_id",
      "tenant_scope",
      "display_name",
      "agent_kind",
      "capabilities",
      "skills",
      "model_profiles",
      "tool_ids",
      "jurisdictions",
      "domain_tags",
      "limits",
      "availability",
      "policy_constraints",
      "version",
      "updated_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "agent_card_id",
      "tenant_scope",
      "display_name",
      "agent_kind",
      "capabilities",
      "skills",
      "model_profiles",
      "tool_ids",
      "jurisdictions",
      "domain_tags",
      "limits",
      "availability",
      "policy_constraints",
      "version",
      "updated_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/agents/agent-card.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/agents/agent-card.schema.json",
    "source_sha256": "92f6c83b6064d5879799cda459acc4d9b535c8b6c976dbbcfb918232ab3849a7"
  },
  "kolibri.artifact": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "artifact_id",
      "artifact_version",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "artifact_type",
      "domain_output",
      "content",
      "contract",
      "generator",
      "inputs",
      "provenance",
      "supersedes",
      "created_by",
      "created_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "artifact_id",
      "artifact_version",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "artifact_type",
      "domain_output",
      "content",
      "contract",
      "generator",
      "inputs",
      "provenance",
      "supersedes",
      "created_by",
      "created_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/artifacts/artifact.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/artifacts/artifact.schema.json",
    "source_sha256": "d4b6511a96997f3b03209e082d11dacf0e22139262f582bff389478984beb6c0"
  },
  "kolibri.artifact.state.transition.command": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "artifact_id",
      "artifact_version",
      "content_hash",
      "expected_state_version",
      "next_state_version",
      "from_status",
      "to_status",
      "reason",
      "invalidated_by",
      "requested_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "artifact_id",
      "artifact_version",
      "content_hash",
      "expected_state_version",
      "next_state_version",
      "from_status",
      "to_status",
      "reason",
      "invalidated_by",
      "requested_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/artifacts/artifact-state-transition.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/artifacts/artifact-state-transition.schema.json",
    "source_sha256": "6e6ecf3c1e7c6e8f40f14e645135e6282a0b0329d5cd2c0ad3109f3eb7e64d60"
  },
  "kolibri.artifact_quality_manifest": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "manifest_id",
      "manifest_version",
      "tenant_id",
      "goal_id",
      "case_id",
      "artifact_ref",
      "artifact_state_version",
      "artifact_status",
      "evidence_refs",
      "review_refs",
      "signoff_refs",
      "eligibility",
      "blockers",
      "generated_at",
      "generated_by"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "manifest_id",
      "manifest_version",
      "tenant_id",
      "goal_id",
      "case_id",
      "artifact_ref",
      "artifact_state_version",
      "artifact_status",
      "evidence_refs",
      "review_refs",
      "signoff_refs",
      "eligibility",
      "blockers",
      "generated_at",
      "generated_by"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/quality/quality-manifest.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/quality/quality-manifest.schema.json",
    "source_sha256": "dd0c90c4141768893b41e717350156d1094abd710c9f193418159bf9577196da"
  },
  "kolibri.artifact_state": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "artifact_id",
      "artifact_version",
      "content_hash",
      "tenant_id",
      "status",
      "state_version",
      "changed_at",
      "reason",
      "invalidated_by"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "artifact_id",
      "artifact_version",
      "content_hash",
      "tenant_id",
      "status",
      "state_version",
      "changed_at",
      "reason",
      "invalidated_by"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/artifacts/artifact-state.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/artifacts/artifact-state.schema.json",
    "source_sha256": "2c21b1a2b91d4b69b1404d6b724f0588ce1781329d3927f1ed9a49c96d359f9d"
  },
  "kolibri.command": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "message_id",
      "command_name",
      "payload_schema_id",
      "payload_schema_version",
      "issued_at",
      "deadline_at",
      "target_owner",
      "identity",
      "trace",
      "idempotency",
      "payload"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "message_id",
      "command_name",
      "payload_schema_id",
      "payload_schema_version",
      "issued_at",
      "deadline_at",
      "target_owner",
      "identity",
      "trace",
      "idempotency",
      "payload"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/common/command-envelope.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/common/command-envelope.schema.json",
    "source_sha256": "a1a3d78bb3e3fba6e80a531a57c7eed54e9529b194769fc405174fc423a900e8"
  },
  "kolibri.document_data": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "document_data_id",
      "document_type",
      "title",
      "client_name",
      "contractor_name",
      "estimate_id",
      "currency",
      "total",
      "locale",
      "jurisdiction",
      "sections",
      "totals",
      "attachments",
      "provenance"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "document_data_id",
      "document_type",
      "title",
      "client_name",
      "contractor_name",
      "estimate_id",
      "currency",
      "total",
      "locale",
      "jurisdiction",
      "sections",
      "totals",
      "attachments",
      "provenance"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/documents/document-data.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/documents/document-data.schema.json",
    "source_sha256": "d01cacc5bebbc80d2209bcfd573425168e77fbf150c25278e489a1c6661fb35b"
  },
  "kolibri.document_render_request": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "request_id",
      "template_id",
      "template_version",
      "template_locale",
      "template_jurisdiction",
      "requested_outputs",
      "document_data",
      "idempotency_key",
      "tenant_id",
      "project_id"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "request_id",
      "template_id",
      "template_version",
      "template_locale",
      "template_jurisdiction",
      "requested_outputs",
      "document_data"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/documents/document-render-request.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/documents/document-render-request.schema.json",
    "source_sha256": "6e8a90dd924abd567db3b77c3d8c0818b0bfb88fd018cd463c8babaa92762b32"
  },
  "kolibri.document_render_result": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "request_id",
      "document_id",
      "template_id",
      "template_version",
      "status",
      "generated_at",
      "rendered_locale",
      "rendered_jurisdiction",
      "assets",
      "warnings",
      "error"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "request_id",
      "document_id",
      "template_id",
      "template_version",
      "status",
      "generated_at",
      "assets"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/documents/document-render-result.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/documents/document-render-result.schema.json",
    "source_sha256": "1bb56efcd3fbc5a5f1def39450e82fc765a2cf84fac6c137b4ab36484426d076"
  },
  "kolibri.document_template": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "template_id",
      "template_version",
      "document_type",
      "locale",
      "jurisdictions",
      "output_formats",
      "data_contract",
      "layout_fingerprint",
      "required_fields",
      "prohibited_fields",
      "reproducible",
      "created_at",
      "updated_at",
      "notes"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "template_id",
      "template_version",
      "document_type",
      "locale",
      "jurisdictions",
      "output_formats",
      "data_contract",
      "layout_fingerprint",
      "required_fields",
      "prohibited_fields",
      "reproducible",
      "created_at",
      "updated_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/documents/document-template.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/documents/document-template.schema.json",
    "source_sha256": "a259324acfb286a26e6ce3e6d16365bfd027a9697190bfff923cdcdccff0e613"
  },
  "kolibri.document_template_registry": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "registry_id",
      "generated_at",
      "templates"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "registry_id",
      "generated_at",
      "templates"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/documents/document-template-registry.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/documents/document-template-registry.schema.json",
    "source_sha256": "2c6ec62c2ab0b26d2de7f8d7c50cbd4bca3a691a25efb1979edfe35e02820efb"
  },
  "kolibri.error": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "error_id",
      "in_response_to",
      "occurred_at",
      "http_status",
      "code",
      "category",
      "retryable",
      "retry_after_ms",
      "safe_message",
      "trace",
      "violations",
      "details"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "error_id",
      "in_response_to",
      "occurred_at",
      "http_status",
      "code",
      "category",
      "retryable",
      "retry_after_ms",
      "safe_message",
      "trace",
      "violations",
      "details"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/common/error-envelope.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/common/error-envelope.schema.json",
    "source_sha256": "975fd703088952385270240dfb4db825ecd7da734592b92fca9e7648943de525"
  },
  "kolibri.event": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "message_id",
      "event_name",
      "payload_schema_id",
      "payload_schema_version",
      "occurred_at",
      "recorded_at",
      "producer_owner",
      "identity",
      "trace",
      "aggregate",
      "source_command_id",
      "deduplication_key",
      "payload"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "message_id",
      "event_name",
      "payload_schema_id",
      "payload_schema_version",
      "occurred_at",
      "recorded_at",
      "producer_owner",
      "identity",
      "trace",
      "aggregate",
      "source_command_id",
      "deduplication_key",
      "payload"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/common/event-envelope.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/common/event-envelope.schema.json",
    "source_sha256": "67437f3e7155bc1ce037dbd5ed2217ada35b338427842ea8f8d1411bc679d272"
  },
  "kolibri.evidence": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "evidence_id",
      "evidence_version",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "claim",
      "source",
      "method",
      "confidence",
      "applicability",
      "verifier",
      "status",
      "supersedes",
      "revocation",
      "created_by",
      "created_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "evidence_id",
      "evidence_version",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "claim",
      "source",
      "method",
      "confidence",
      "applicability",
      "verifier",
      "status",
      "supersedes",
      "revocation",
      "created_by",
      "created_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/quality/evidence.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/quality/evidence.schema.json",
    "source_sha256": "b54d41e68f896d80daafecd77dbced8782b5a4b7a5b4f147de69440423d845b0"
  },
  "kolibri.goal": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "goal_id",
      "tenant_id",
      "user_id",
      "intent",
      "acceptance_criteria",
      "budget_policy",
      "deadline_policy",
      "status",
      "blocking_question_ids",
      "case_id",
      "current_case_version",
      "workflow_id",
      "current_workflow_version",
      "version",
      "supersedes_goal_id",
      "created_at",
      "updated_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "goal_id",
      "tenant_id",
      "user_id",
      "intent",
      "acceptance_criteria",
      "budget_policy",
      "deadline_policy",
      "status",
      "blocking_question_ids",
      "case_id",
      "current_case_version",
      "workflow_id",
      "current_workflow_version",
      "version",
      "supersedes_goal_id",
      "created_at",
      "updated_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/goals/goal.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/goals/goal.schema.json",
    "source_sha256": "eba385bd8ead43c44741c151174800459fe651e18d67a022893c5c90b04eb220"
  },
  "kolibri.goal.changed.event": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "goal_id",
      "command_name",
      "change_type",
      "previous_version",
      "new_version",
      "previous_status",
      "new_status",
      "reason_provided"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "goal_id",
      "command_name",
      "change_type",
      "previous_version",
      "new_version",
      "previous_status",
      "new_status",
      "reason_provided"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/goals/goal-change-event.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/goals/goal-change-event.schema.json",
    "source_sha256": "46ebbac4266e077178e15fd7bee6e7b25207cf93cbecbe6a21d61b6b293edf7d"
  },
  "kolibri.goal.create.command": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "goal",
      "requested_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "goal",
      "requested_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/goals/goal-create.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/goals/goal-create.schema.json",
    "source_sha256": "ecaa94a0741a8e42dd073a77d85717858d552d3fae5480999629a6b6ca0c2e01"
  },
  "kolibri.goal.transition.command": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "goal_id",
      "expected_version",
      "next_version",
      "from_status",
      "to_status",
      "reason",
      "requested_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "goal_id",
      "expected_version",
      "next_version",
      "from_status",
      "to_status",
      "reason",
      "requested_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/goals/goal-transition.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/goals/goal-transition.schema.json",
    "source_sha256": "69904db06c8435a6570a21b5096fb1baa061a55e8737b1f343e38e2ea253b221"
  },
  "kolibri.goal.update.command": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "goal_id",
      "expected_version",
      "next_version",
      "goal",
      "reason",
      "requested_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "goal_id",
      "expected_version",
      "next_version",
      "goal",
      "reason",
      "requested_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/goals/goal-update.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/goals/goal-update.schema.json",
    "source_sha256": "23a346af4cb72eb829c99f8e1823e72f6f48f46aec5d104adecb4d05ed0e52e9"
  },
  "kolibri.product.agui.projection": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "thread_id",
      "run_id",
      "source_event_id",
      "source_sequence",
      "protocol",
      "protocol_version",
      "adapter_package",
      "adapter_version",
      "event_type",
      "custom_schema_id",
      "custom_schema_version",
      "payload",
      "projected_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "thread_id",
      "run_id",
      "source_event_id",
      "source_sequence",
      "protocol",
      "protocol_version",
      "adapter_package",
      "adapter_version",
      "event_type",
      "custom_schema_id",
      "custom_schema_version",
      "payload",
      "projected_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/agui-projection.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/agui-projection.schema.json",
    "source_sha256": "9ca18e2e05d21322f6740c33460a933a432371ed0f5da1cc8e33d38eba052501"
  },
  "kolibri.product.attachment": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "user_id",
      "project_id",
      "attachment_id",
      "artifact_id",
      "artifact_version",
      "content_hash",
      "filename",
      "mime_type",
      "size_bytes",
      "content_path",
      "status",
      "created_by",
      "created_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "user_id",
      "project_id",
      "attachment_id",
      "artifact_id",
      "artifact_version",
      "content_hash",
      "filename",
      "mime_type",
      "size_bytes",
      "content_path",
      "status",
      "created_by",
      "created_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/attachment.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/attachment.schema.json",
    "source_sha256": "f7c2fa87391e671e64ef61a6106a20bc667cf480848b10dfd5b1226f0d5232bc"
  },
  "kolibri.product.delivery_cursor": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "user_id",
      "project_id",
      "thread_id",
      "run_id",
      "last_sequence",
      "last_event_id",
      "ledger_version",
      "issued_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "user_id",
      "project_id",
      "thread_id",
      "run_id",
      "last_sequence",
      "last_event_id",
      "ledger_version",
      "issued_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/delivery-cursor.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/delivery-cursor.schema.json",
    "source_sha256": "111e86cc732b5821d1d836a95dee08b2dc4d8b3ded47d551bc30b7add856c6a2"
  },
  "kolibri.product.developer_dispatch": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "source_command_ref",
      "run_id",
      "project_id",
      "thread_id",
      "input_message_id",
      "runtime_profile",
      "runtime_capability",
      "model",
      "reasoning_effort",
      "service_tier",
      "workspace_ref",
      "access_mode",
      "sandbox",
      "approval_policy",
      "reviewer"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "source_command_ref",
      "run_id",
      "project_id",
      "thread_id",
      "input_message_id",
      "runtime_profile",
      "runtime_capability",
      "model",
      "reasoning_effort",
      "service_tier",
      "workspace_ref",
      "access_mode",
      "sandbox",
      "approval_policy",
      "reviewer"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/developer-dispatch.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/developer-dispatch.schema.json",
    "source_sha256": "8ddb035c0f6423791cb4847ef89a4513fc815c5fc8b840836dd00415b48c4f28"
  },
  "kolibri.product.developer_dispatch.v1_1": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "source_command_ref",
      "run_id",
      "project_id",
      "thread_id",
      "input_message_id",
      "runtime_profile",
      "runtime_capability",
      "model",
      "reasoning_effort",
      "service_tier",
      "workspace_ref",
      "access_mode",
      "sandbox",
      "approval_policy",
      "reviewer",
      "trusted_agent_profile_id",
      "trusted_agent_profile_epoch",
      "trusted_agent_workspace_binding_id",
      "trusted_agent_workspace_binding_epoch"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "source_command_ref",
      "run_id",
      "project_id",
      "thread_id",
      "input_message_id",
      "runtime_profile",
      "runtime_capability",
      "model",
      "reasoning_effort",
      "service_tier",
      "workspace_ref",
      "access_mode",
      "sandbox",
      "approval_policy",
      "reviewer",
      "trusted_agent_profile_id",
      "trusted_agent_profile_epoch",
      "trusted_agent_workspace_binding_id",
      "trusted_agent_workspace_binding_epoch"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/developer-dispatch-v1.1.schema.json",
    "schema_version": "1.1",
    "source_path": "contracts/v1/product/developer-dispatch-v1.1.schema.json",
    "source_sha256": "0450a6d912c8fcff560b00638d701b448d39147a25ee5fb03f26cce08dcc845d"
  },
  "kolibri.product.developer_lease_source": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "source_command_ref",
      "canonical_request_hash",
      "source_command_hash",
      "tenant_id",
      "task_id",
      "task_version",
      "attempt_id",
      "assignment_id",
      "effect_id",
      "lease_id",
      "fencing_token",
      "runtime_profile",
      "access_policy"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "source_command_ref",
      "canonical_request_hash",
      "source_command_hash",
      "tenant_id",
      "task_id",
      "task_version",
      "attempt_id",
      "assignment_id",
      "effect_id",
      "lease_id",
      "fencing_token",
      "runtime_profile",
      "access_policy"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/developer-lease-source.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/developer-lease-source.schema.json",
    "source_sha256": "717cd3cda833129e041687e5d80141ee99bffd4a0b2a349051bf2e712aedeb6e"
  },
  "kolibri.product.developer_lease_source.v1_1": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "source_command_ref",
      "canonical_request_hash",
      "source_command_hash",
      "tenant_id",
      "task_id",
      "task_version",
      "attempt_id",
      "assignment_id",
      "effect_id",
      "lease_id",
      "fencing_token",
      "runtime_profile",
      "access_policy",
      "trusted_agent_profile_id",
      "trusted_agent_profile_epoch",
      "trusted_agent_workspace_binding_id",
      "trusted_agent_workspace_binding_epoch"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "source_command_ref",
      "canonical_request_hash",
      "source_command_hash",
      "tenant_id",
      "task_id",
      "task_version",
      "attempt_id",
      "assignment_id",
      "effect_id",
      "lease_id",
      "fencing_token",
      "runtime_profile",
      "access_policy",
      "trusted_agent_profile_id",
      "trusted_agent_profile_epoch",
      "trusted_agent_workspace_binding_id",
      "trusted_agent_workspace_binding_epoch"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/developer-lease-source-v1.1.schema.json",
    "schema_version": "1.1",
    "source_path": "contracts/v1/product/developer-lease-source-v1.1.schema.json",
    "source_sha256": "3d5bcd3aa1f3d6c3251e157cb8aee3b4eafe4ff1545eefc6267d70a221fe0368"
  },
  "kolibri.product.developer_source_command": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "source_command_ref",
      "tenant_id",
      "goal_id",
      "case_id",
      "run_id",
      "task_id",
      "graph_id",
      "request_hash",
      "command_hash",
      "requested_runtime_profile",
      "runtime_profile",
      "runtime_capability",
      "access_policy",
      "state",
      "source_command"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "source_command_ref",
      "tenant_id",
      "goal_id",
      "case_id",
      "run_id",
      "task_id",
      "graph_id",
      "request_hash",
      "command_hash",
      "requested_runtime_profile",
      "runtime_profile",
      "runtime_capability",
      "access_policy",
      "state",
      "source_command"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/developer-source-command.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/developer-source-command.schema.json",
    "source_sha256": "89a4fb6e9c9a337c213c146aeb165b20bab2927ac7a30264d71dd97a5c38ecbf"
  },
  "kolibri.product.goal.initialization_status": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "run_id",
      "goal_id",
      "case_id",
      "status",
      "goal_version",
      "case_version",
      "error"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "run_id",
      "goal_id",
      "case_id",
      "status",
      "goal_version",
      "case_version",
      "error"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/product-goal-initialization-status.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/product-goal-initialization-status.schema.json",
    "source_sha256": "c2bc31c3994fc3c9af3336d509cf350c4f6cc1faebd049b1a4d889ca2a78fe2a"
  },
  "kolibri.product.goal.initialize.command": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "input_message_id",
      "goal_id",
      "prompt",
      "prompt_hash"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "input_message_id",
      "goal_id",
      "prompt",
      "prompt_hash"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/product-goal-initialize-command.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/product-goal-initialize-command.schema.json",
    "source_sha256": "c79a55e8713c2e15e74eca94da4ce247aaa3aa2d121391f132a10cd7b2f6deba"
  },
  "kolibri.product.interrupt": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "interrupt_id",
      "interrupt_version",
      "state",
      "kind",
      "prompt",
      "response_schema_id",
      "response_schema_version",
      "required_authority",
      "answer_message_id",
      "created_at",
      "updated_at",
      "expires_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "interrupt_id",
      "interrupt_version",
      "state",
      "kind",
      "prompt",
      "response_schema_id",
      "response_schema_version",
      "required_authority",
      "answer_message_id",
      "created_at",
      "updated_at",
      "expires_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/interrupt.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/interrupt.schema.json",
    "source_sha256": "9d0ad7f14b523f8cc281503e604a6db238002a9d8854d704b290a7a02490103d"
  },
  "kolibri.product.message": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "message_id",
      "sequence",
      "parent_message_id",
      "branch_id",
      "run_id",
      "role",
      "author_actor_id",
      "status",
      "parts",
      "version",
      "created_at",
      "committed_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "message_id",
      "sequence",
      "parent_message_id",
      "branch_id",
      "run_id",
      "role",
      "author_actor_id",
      "status",
      "parts",
      "version",
      "created_at",
      "committed_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/message.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/message.schema.json",
    "source_sha256": "931d837afb377e640d88440bdea5923a94751c85264b58a8dd94059fe9959365"
  },
  "kolibri.product.project": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "case_id",
      "goal_id",
      "name",
      "status",
      "default_thread_id",
      "version",
      "created_by",
      "created_at",
      "updated_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "case_id",
      "goal_id",
      "name",
      "status",
      "default_thread_id",
      "version",
      "created_by",
      "created_at",
      "updated_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/project.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/project.schema.json",
    "source_sha256": "51ee7a60658b1cc49d83a1b6cb317548ea0cd7f3e0a32338c41a52409d964c1b"
  },
  "kolibri.product.project_create_request": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "name"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "name"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/project-create-request.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/project-create-request.schema.json",
    "source_sha256": "fbd9274ab1d5ea490f0093139f3f33af767196ee7a0061439c38a50fb91d01ec"
  },
  "kolibri.product.provider.enrollment_intent.command": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "intent_id",
      "provider_id",
      "requested_by_user_id",
      "owner_authorization_decision_id",
      "purpose",
      "requested_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "intent_id",
      "provider_id",
      "requested_by_user_id",
      "owner_authorization_decision_id",
      "purpose",
      "requested_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/provider-enrollment-intent-command.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/provider-enrollment-intent-command.schema.json",
    "source_sha256": "6c93f6844182d12fea445a9791b6dfee0d494cb9034464379bec9f5e78cb9157"
  },
  "kolibri.product.provider.enrollment_status": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "intent_id",
      "provider_id",
      "status",
      "observed_at",
      "auth_flow_supported",
      "last_verified_at",
      "evidence_hash",
      "error"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "intent_id",
      "provider_id",
      "status",
      "observed_at",
      "auth_flow_supported",
      "last_verified_at",
      "evidence_hash",
      "error"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/provider-enrollment-status.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/provider-enrollment-status.schema.json",
    "source_sha256": "997c87f1d66e0f1d6e7e05a13789d3051afceb7005bfac2fa6f86b28833210d2"
  },
  "kolibri.product.run": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "run_sequence",
      "input_message_id",
      "retry_of_run_id",
      "resume_of_run_id",
      "case_id",
      "goal_id",
      "home_task_id",
      "lifecycle",
      "outcome",
      "last_event_sequence",
      "last_event_id",
      "active_interrupt_ids",
      "version",
      "created_by",
      "created_at",
      "updated_at",
      "finished_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "run_sequence",
      "input_message_id",
      "retry_of_run_id",
      "resume_of_run_id",
      "case_id",
      "goal_id",
      "home_task_id",
      "lifecycle",
      "outcome",
      "last_event_sequence",
      "last_event_id",
      "active_interrupt_ids",
      "version",
      "created_by",
      "created_at",
      "updated_at",
      "finished_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/run.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/run.schema.json",
    "source_sha256": "76630448fbb2a4a98f32ee7c817889464666567215bbcfbfec47b028de8a0967"
  },
  "kolibri.product.run.event": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "event_id",
      "sequence",
      "event_type",
      "payload_schema_id",
      "payload_schema_version",
      "payload",
      "trace",
      "source_task_id",
      "source_event_id",
      "occurred_at",
      "recorded_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "event_id",
      "sequence",
      "event_type",
      "payload_schema_id",
      "payload_schema_version",
      "payload",
      "trace",
      "source_task_id",
      "source_event_id",
      "occurred_at",
      "recorded_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/run-event.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/run-event.schema.json",
    "source_sha256": "2bdf3062fcb88993a32112541439e50311f3bc0dbc41687fe0dbfb45d0d522e5"
  },
  "kolibri.product.run.execute.command": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "input_message_id",
      "case_id",
      "goal_id",
      "prompt",
      "prompt_hash",
      "preferred_agent_profile"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "input_message_id",
      "case_id",
      "goal_id",
      "prompt",
      "prompt_hash",
      "preferred_agent_profile"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/run-execute-command.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/run-execute-command.schema.json",
    "source_sha256": "53fc9b47c5f28a6130c3641bf878fa047fb0862b6ca13756a7e752a9326c41fe"
  },
  "kolibri.product.run.execute.v1_1.command": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "input_message_id",
      "case_id",
      "goal_id",
      "prompt",
      "prompt_hash",
      "preferred_agent_profile",
      "preferred_model",
      "preferred_reasoning_effort"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "input_message_id",
      "case_id",
      "goal_id",
      "prompt",
      "prompt_hash",
      "preferred_agent_profile",
      "preferred_model",
      "preferred_reasoning_effort"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/run-execute-command-v1.1.schema.json",
    "schema_version": "1.1",
    "source_path": "contracts/v1/product/run-execute-command-v1.1.schema.json",
    "source_sha256": "43572695e4b7d3480c23a6f46e571cecb1042cc15e47573cb9d626fb2281eb6c"
  },
  "kolibri.product.run.execute.v1_2.command": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "input_message_id",
      "case_id",
      "goal_id",
      "prompt",
      "prompt_hash",
      "execution_mode",
      "runtime_profile",
      "model",
      "reasoning_effort",
      "service_tier",
      "workspace_ref",
      "access_mode",
      "sandbox",
      "approval_policy",
      "reviewer",
      "requester_role"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "input_message_id",
      "case_id",
      "goal_id",
      "prompt",
      "prompt_hash",
      "execution_mode",
      "runtime_profile",
      "model",
      "reasoning_effort",
      "service_tier",
      "workspace_ref",
      "access_mode",
      "sandbox",
      "approval_policy",
      "reviewer",
      "requester_role"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/run-execute-command-v1.2.schema.json",
    "schema_version": "1.2",
    "source_path": "contracts/v1/product/run-execute-command-v1.2.schema.json",
    "source_sha256": "04cfe4fc9355221c42176a3559d68b4ce9caf1836e3b538125bbbbc9ed024df5"
  },
  "kolibri.product.run.execute.v1_3.command": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "input_message_id",
      "case_id",
      "goal_id",
      "prompt",
      "prompt_hash",
      "execution_mode",
      "runtime_profile",
      "model",
      "reasoning_effort",
      "service_tier",
      "workspace_ref",
      "access_mode",
      "sandbox",
      "approval_policy",
      "reviewer",
      "requester_role",
      "trusted_agent_profile_id",
      "trusted_agent_profile_epoch",
      "trusted_agent_workspace_binding_id",
      "trusted_agent_workspace_binding_epoch"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "input_message_id",
      "case_id",
      "goal_id",
      "prompt",
      "prompt_hash",
      "execution_mode",
      "runtime_profile",
      "model",
      "reasoning_effort",
      "service_tier",
      "workspace_ref",
      "access_mode",
      "sandbox",
      "approval_policy",
      "reviewer",
      "requester_role",
      "trusted_agent_profile_id",
      "trusted_agent_profile_epoch",
      "trusted_agent_workspace_binding_id",
      "trusted_agent_workspace_binding_epoch"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/run-execute-command-v1.3.schema.json",
    "schema_version": "1.3",
    "source_path": "contracts/v1/product/run-execute-command-v1.3.schema.json",
    "source_sha256": "9c442583c83357ade736ce4f0c48d4aed157d9a3268c7601461e1658e2f0ae3f"
  },
  "kolibri.product.run.execution_status": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "run_id",
      "status",
      "profile",
      "execution_id",
      "verification_status",
      "result_text",
      "result_hash",
      "evidence",
      "error"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "run_id",
      "status",
      "profile",
      "execution_id",
      "verification_status",
      "result_text",
      "result_hash",
      "evidence",
      "error"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/run-execution-status.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/run-execution-status.schema.json",
    "source_sha256": "acb34add98b6e868400faa66da34da8982f5c61dacd51baedb48dd6649aa602e"
  },
  "kolibri.product.run.execution_status.v1_1": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "run_id",
      "status",
      "runtime_profile",
      "execution_id",
      "verification_status",
      "result_text",
      "result_hash",
      "evidence",
      "error"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "run_id",
      "status",
      "runtime_profile",
      "execution_id",
      "verification_status",
      "result_text",
      "result_hash",
      "evidence",
      "error"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/run-execution-status-v1.1.schema.json",
    "schema_version": "1.1",
    "source_path": "contracts/v1/product/run-execution-status-v1.1.schema.json",
    "source_sha256": "f78ad866af38796bdcce755cd9058333512ea12355b7c316a2f96612d2b9306d"
  },
  "kolibri.product.session": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "user_id",
      "session_kind",
      "expires_at",
      "product_api_version",
      "capabilities"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "user_id",
      "session_kind",
      "expires_at",
      "product_api_version",
      "capabilities"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/session.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/session.schema.json",
    "source_sha256": "eea2758f7b3fa70d4738f2434b58faa77ce5df6bd7c7544b2362c5072968e5a8"
  },
  "kolibri.product.text_run_request": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "expected_thread_version",
      "parent_message_id",
      "parts",
      "preferred_agent_profile"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "expected_thread_version",
      "parent_message_id",
      "parts",
      "preferred_agent_profile"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/text-run-request.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/text-run-request.schema.json",
    "source_sha256": "b29f68274aa8611579abbcb478ccfea755e01802acb8b2e82bd9149066f5229e"
  },
  "kolibri.product.thread": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "title",
      "status",
      "branch_count",
      "last_message_sequence",
      "last_run_sequence",
      "version",
      "created_by",
      "created_at",
      "updated_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "title",
      "status",
      "branch_count",
      "last_message_sequence",
      "last_run_sequence",
      "version",
      "created_by",
      "created_at",
      "updated_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/thread.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/thread.schema.json",
    "source_sha256": "07e7eeab8c95b5fa6fe0b812b6b9d77c5e396cfbc0c44fdc558abc58b744b6d0"
  },
  "kolibri.product.thread_update_request": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "expected_thread_version",
      "title"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "expected_thread_version",
      "title"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/product/thread-update-request.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/product/thread-update-request.schema.json",
    "source_sha256": "6707ab9d6f2ce6f343588e4723a409100cfc5fe40ae7d9db1658e0822cf3926e"
  },
  "kolibri.project_case": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "case_id",
      "goal_id",
      "goal_version",
      "tenant_id",
      "status",
      "version",
      "event_sequence",
      "intent_snapshot",
      "acceptance_criterion_ids",
      "facts",
      "assumptions",
      "proposals",
      "decisions",
      "open_questions",
      "requirements",
      "constraints",
      "domain_refs",
      "created_at",
      "updated_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "case_id",
      "goal_id",
      "goal_version",
      "tenant_id",
      "status",
      "version",
      "event_sequence",
      "intent_snapshot",
      "acceptance_criterion_ids",
      "facts",
      "assumptions",
      "proposals",
      "decisions",
      "open_questions",
      "requirements",
      "constraints",
      "domain_refs",
      "created_at",
      "updated_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/cases/project-case.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/cases/project-case.schema.json",
    "source_sha256": "374336ec67f2e9f98a78e37bc9771632d3ccdb15d03e51e16665a610958f8618"
  },
  "kolibri.project_case.transition.command": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "case_id",
      "expected_version",
      "next_version",
      "from_status",
      "to_status",
      "reason",
      "requested_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "case_id",
      "expected_version",
      "next_version",
      "from_status",
      "to_status",
      "reason",
      "requested_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/cases/project-case-transition.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/cases/project-case-transition.schema.json",
    "source_sha256": "76524be900477ef2ecf9549cc5ae02fc3aa675ade661bede1b9e3ff2e358df37"
  },
  "kolibri.project_workflow": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "workflow_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "workflow_type",
      "parent_workflow_id",
      "status",
      "version",
      "graph_id",
      "graph_version",
      "activity_count",
      "signal_count",
      "query_count",
      "timer_count",
      "activities",
      "pending_signals",
      "open_queries",
      "timers",
      "created_at",
      "updated_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "workflow_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "workflow_type",
      "status",
      "version",
      "graph_id",
      "graph_version",
      "activity_count",
      "signal_count",
      "query_count",
      "timer_count",
      "activities",
      "pending_signals",
      "open_queries",
      "timers",
      "created_at",
      "updated_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/workflows/project-workflow.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/workflows/project-workflow.schema.json",
    "source_sha256": "949312f09b7742d974d659f2929f40600d818399cef6f07380b6cb649feaaa2e"
  },
  "kolibri.provider_execution.catalog": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "agent_cards"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "agent_cards"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/provider-execution/catalog.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/provider-execution/catalog.schema.json",
    "source_sha256": "4bd5fe7f89c4fe2fc6a40de26ee177c1f6b760d6028caa0870e669bc96cd878e"
  },
  "kolibri.provider_execution.request": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "effect_key",
      "task",
      "attempt",
      "agent_assignment",
      "requester_assignment",
      "a2a_request",
      "developer_dispatch",
      "source_command",
      "lease_source"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "effect_key",
      "task",
      "attempt",
      "agent_assignment",
      "requester_assignment",
      "a2a_request",
      "developer_dispatch",
      "source_command",
      "lease_source"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/provider-execution/request.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/provider-execution/request.schema.json",
    "source_sha256": "ea8f22a40c7d33399aa69d1101f9cd4647cfd0089cb53ba0357b808da6c32d41"
  },
  "kolibri.provider_execution.result": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "effect_key",
      "request_hash",
      "task_id",
      "attempt_id",
      "assignment_id",
      "lease_id",
      "fencing_token",
      "runtime_profile",
      "status",
      "replayed",
      "output",
      "activity",
      "error"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "effect_key",
      "request_hash",
      "task_id",
      "attempt_id",
      "assignment_id",
      "lease_id",
      "fencing_token",
      "runtime_profile",
      "status",
      "replayed",
      "output",
      "activity",
      "error"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/provider-execution/result.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/provider-execution/result.schema.json",
    "source_sha256": "dad0e7acff92db6bbba53f2a8a85be39776d4101fc8c8c2b4f8e86d2df9b98ac"
  },
  "kolibri.review": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "review_id",
      "review_version",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "artifact_ref",
      "author_actor_id",
      "reviewer_actor_id",
      "reviewer_assignment_id",
      "scope",
      "criteria",
      "evidence_refs",
      "findings",
      "disposition",
      "status",
      "requested_at",
      "completed_at",
      "supersedes"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "review_id",
      "review_version",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "artifact_ref",
      "author_actor_id",
      "reviewer_actor_id",
      "reviewer_assignment_id",
      "scope",
      "criteria",
      "evidence_refs",
      "findings",
      "disposition",
      "status",
      "requested_at",
      "completed_at",
      "supersedes"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/quality/review.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/quality/review.schema.json",
    "source_sha256": "5de5019fd7d41bd22aadf02496f64448e0e8a76bf37e8acbb7d9e020b13ba721"
  },
  "kolibri.signoff": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "signoff_id",
      "signoff_version",
      "tenant_id",
      "goal_id",
      "case_id",
      "artifact_ref",
      "signoff_type",
      "signer",
      "authority_basis_ref",
      "policy_decision",
      "review_refs",
      "signature_ref",
      "status",
      "granted_at",
      "revocation",
      "supersedes"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "signoff_id",
      "signoff_version",
      "tenant_id",
      "goal_id",
      "case_id",
      "artifact_ref",
      "signoff_type",
      "signer",
      "authority_basis_ref",
      "policy_decision",
      "review_refs",
      "signature_ref",
      "status",
      "granted_at",
      "revocation",
      "supersedes"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/quality/signoff.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/quality/signoff.schema.json",
    "source_sha256": "fc925177b7ce848ecc0dabaec0d1728e39a1f9ce40f9c108b474795ba0aedf09"
  },
  "kolibri.task": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "task_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "title",
      "objective",
      "kind",
      "parent_task_id",
      "dependency_task_ids",
      "required_capabilities",
      "acceptance_criteria",
      "expected_outputs",
      "budget",
      "deadline_at",
      "risk_class",
      "state",
      "graph_version",
      "version",
      "current_attempt_id",
      "current_assignment_id",
      "created_at",
      "updated_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "task_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "title",
      "objective",
      "kind",
      "dependency_task_ids",
      "required_capabilities",
      "acceptance_criteria",
      "expected_outputs",
      "budget",
      "deadline_at",
      "risk_class",
      "state",
      "graph_version",
      "version",
      "current_attempt_id",
      "current_assignment_id",
      "created_at",
      "updated_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/tasks/task.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/tasks/task.schema.json",
    "source_sha256": "2d492bc9c2497f535366100246d887493ab4afaf52dfceb2126006875743ced5"
  },
  "kolibri.task.transition.command": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "task_id",
      "expected_version",
      "next_version",
      "from_status",
      "to_status",
      "attempt_id",
      "assignment_id",
      "lease_id",
      "fencing_token",
      "reason",
      "requested_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "task_id",
      "expected_version",
      "next_version",
      "from_status",
      "to_status",
      "attempt_id",
      "assignment_id",
      "lease_id",
      "fencing_token",
      "reason",
      "requested_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/tasks/task-transition.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/tasks/task-transition.schema.json",
    "source_sha256": "01b96ea84deb71bd7b0fd16bd0561f6395b53fe9fe4a2f29a51ded199eab46b4"
  },
  "kolibri.task_attempt": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "attempt_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "attempt_number",
      "assignment_id",
      "status",
      "lease",
      "effect_id",
      "result_artifact_refs",
      "result_hash",
      "error",
      "created_at",
      "updated_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "attempt_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "attempt_number",
      "assignment_id",
      "status",
      "lease",
      "effect_id",
      "result_artifact_refs",
      "result_hash",
      "error",
      "created_at",
      "updated_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/tasks/attempt.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/tasks/attempt.schema.json",
    "source_sha256": "254efba0af0b5db76244c53054f3c91fc369a90761f3672791260f375b53755c"
  },
  "kolibri.task_graph": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "graph_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "graph_version",
      "tasks",
      "relations",
      "topological_task_ids",
      "runnable_task_ids",
      "created_at",
      "updated_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "graph_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "graph_version",
      "tasks",
      "relations",
      "topological_task_ids",
      "runnable_task_ids",
      "created_at",
      "updated_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/tasks/task-graph.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/tasks/task-graph.schema.json",
    "source_sha256": "50cef8e8f097b76d9e64348b116015908b8d3ffb65dc0724b89f538941666698"
  },
  "kolibri.task_graph.apply.command": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "graph_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "expected_graph_version",
      "next_graph_version",
      "tasks",
      "reason",
      "requested_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "graph_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "expected_graph_version",
      "next_graph_version",
      "tasks",
      "reason",
      "requested_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/tasks/task-graph-apply.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/tasks/task-graph-apply.schema.json",
    "source_sha256": "a730d6addd2b7fcb0484ea173bf982e1daf30cc459446e4ac1a29b3a3f06b3d8"
  },
  "kolibri.task_graph.changed.event": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "graph_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "previous_graph_version",
      "new_graph_version",
      "task_count",
      "runnable_task_ids"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "graph_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "previous_graph_version",
      "new_graph_version",
      "task_count",
      "runnable_task_ids"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/tasks/task-graph-change-event.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/tasks/task-graph-change-event.schema.json",
    "source_sha256": "458f78591b9bc3102851b11b7769ec59db3801e4aa40a821f06943dbf9fa67e1"
  },
  "kolibri.task_owner_state": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "task_id",
      "task_version",
      "current_status",
      "current_attempt_id",
      "current_assignment_id",
      "lease_id",
      "authority_id",
      "authority_epoch",
      "fencing_token",
      "lease_expires_at",
      "committed_effects"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "task_id",
      "task_version",
      "current_status",
      "current_attempt_id",
      "current_assignment_id",
      "lease_id",
      "authority_id",
      "authority_epoch",
      "fencing_token",
      "lease_expires_at",
      "committed_effects"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/tasks/owner-state.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/tasks/owner-state.schema.json",
    "source_sha256": "416f347144fda12e2479e7788c8139c0e3124a97f22f7572793684988d514774"
  },
  "kolibri.workflow.query": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "workflow_id",
      "query_id",
      "query_type",
      "query_scope",
      "requested_at",
      "response_contract_id"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "workflow_id",
      "query_id",
      "query_type",
      "requested_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/workflows/workflow-query.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/workflows/workflow-query.schema.json",
    "source_sha256": "17d3aec294b42a6c1c38287d8002d2ceaaf3707bdaf2d9e2f941c36a3a128984"
  },
  "kolibri.workflow.signal": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "workflow_id",
      "signal_id",
      "signal_type",
      "source",
      "payload_hash",
      "requested_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "workflow_id",
      "signal_id",
      "signal_type",
      "source",
      "payload_hash",
      "requested_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/workflows/workflow-signal.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/workflows/workflow-signal.schema.json",
    "source_sha256": "0999e877d4ae2b013bbba006e8d574940cac1e611e8d3516c055a64d1f7da5e8"
  },
  "kolibri.workflow.timer": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "workflow_id",
      "timer_id",
      "timer_type",
      "scheduled_at",
      "status",
      "fired_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "workflow_id",
      "timer_id",
      "timer_type",
      "scheduled_at",
      "status"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/workflows/workflow-timer.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/workflows/workflow-timer.schema.json",
    "source_sha256": "994e895fda8a9a5c80a519f0b4c93efa23549106c810be71d6c46c984ccdb68d"
  },
  "kolibri.workflow.version.transition.command": {
    "allowed_fields": [
      "schema_id",
      "schema_version",
      "workflow_id",
      "expected_version",
      "next_version",
      "reason",
      "requested_at"
    ],
    "required_fields": [
      "schema_id",
      "schema_version",
      "workflow_id",
      "expected_version",
      "next_version",
      "reason",
      "requested_at"
    ],
    "schema_uri": "https://schemas.kolibriai.ru/v1/workflows/workflow-version.schema.json",
    "schema_version": "1.0",
    "source_path": "contracts/v1/workflows/workflow-version.schema.json",
    "source_sha256": "0f8364070f149f1197cb1a4dcd60c6004ca48e0f28686dd26580c8f474837ea9"
  }
} as const

const CONTRACT_SCHEMAS: Readonly<Record<string, unknown>> = {
  "https://kolibriai.ru/contracts/v1/devices/device-capability-manifest.schema.json": {
    "$id": "https://kolibriai.ru/contracts/v1/devices/device-capability-manifest.schema.json",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "additionalProperties": false,
    "allOf": [
      {
        "if": {
          "properties": {
            "outputs": {
              "contains": {
                "const": "display"
              }
            }
          },
          "required": [
            "outputs"
          ]
        },
        "then": {
          "required": [
            "screen"
          ]
        }
      }
    ],
    "properties": {
      "connectivity": {
        "items": {
          "enum": [
            "ethernet",
            "wifi",
            "cellular",
            "bluetooth",
            "usb",
            "serial",
            "mqtt",
            "offline_only"
          ]
        },
        "maxItems": 16,
        "type": "array",
        "uniqueItems": true
      },
      "deviceClass": {
        "enum": [
          "browser",
          "native_mobile",
          "desktop",
          "kiosk",
          "tv",
          "wearable",
          "vehicle",
          "spatial",
          "embedded",
          "headless",
          "gateway"
        ]
      },
      "deviceId": {
        "pattern": "^device_[a-zA-Z0-9][a-zA-Z0-9._-]{7,127}$",
        "type": "string"
      },
      "formFactor": {
        "enum": [
          "phone",
          "tablet",
          "laptop",
          "desktop",
          "wall_display",
          "tv",
          "kiosk",
          "watch",
          "glasses",
          "vehicle_console",
          "speaker",
          "printer",
          "sensor",
          "controller",
          "gateway",
          "other"
        ]
      },
      "inputs": {
        "items": {
          "enum": [
            "touch",
            "pointer",
            "keyboard",
            "remote_control",
            "microphone",
            "camera",
            "barcode",
            "nfc",
            "biometric",
            "location",
            "motion",
            "sensor",
            "gpio",
            "serial"
          ]
        },
        "maxItems": 32,
        "type": "array",
        "uniqueItems": true
      },
      "localExecution": {
        "additionalProperties": false,
        "properties": {
          "localInference": {
            "type": "boolean"
          },
          "offlineQueue": {
            "type": "boolean"
          },
          "rust": {
            "type": "boolean"
          },
          "wasm": {
            "type": "boolean"
          }
        },
        "required": [
          "rust",
          "wasm",
          "offlineQueue",
          "localInference"
        ],
        "type": "object"
      },
      "outputs": {
        "items": {
          "enum": [
            "display",
            "audio",
            "haptics",
            "notification",
            "file",
            "printer",
            "led",
            "actuator",
            "gpio",
            "serial"
          ]
        },
        "maxItems": 32,
        "type": "array",
        "uniqueItems": true
      },
      "platform": {
        "additionalProperties": false,
        "properties": {
          "architecture": {
            "pattern": "^[a-zA-Z0-9][a-zA-Z0-9._-]{1,31}$",
            "type": "string"
          },
          "os": {
            "pattern": "^[a-z][a-z0-9._-]{1,63}$",
            "type": "string"
          },
          "osVersion": {
            "maxLength": 64,
            "minLength": 1,
            "type": "string"
          }
        },
        "required": [
          "os",
          "osVersion",
          "architecture"
        ],
        "type": "object"
      },
      "runtime": {
        "enum": [
          "web",
          "pwa",
          "react_native",
          "tauri",
          "native_ios",
          "native_android",
          "native_other",
          "rust_headless"
        ]
      },
      "runtimeVersion": {
        "maxLength": 64,
        "minLength": 1,
        "type": "string"
      },
      "schemaVersion": {
        "const": "1.0"
      },
      "screen": {
        "additionalProperties": false,
        "properties": {
          "color": {
            "type": "boolean"
          },
          "height": {
            "maximum": 65535,
            "minimum": 1,
            "type": "integer"
          },
          "pixelRatio": {
            "exclusiveMinimum": 0,
            "maximum": 16,
            "type": "number"
          },
          "touch": {
            "type": "boolean"
          },
          "width": {
            "maximum": 65535,
            "minimum": 1,
            "type": "integer"
          }
        },
        "required": [
          "width",
          "height",
          "pixelRatio",
          "color"
        ],
        "type": "object"
      },
      "security": {
        "additionalProperties": false,
        "properties": {
          "attestation": {
            "enum": [
              "none",
              "declared",
              "platform",
              "managed"
            ]
          },
          "biometric": {
            "type": "boolean"
          },
          "hardwareBackedKey": {
            "type": "boolean"
          },
          "secureStorage": {
            "type": "boolean"
          }
        },
        "required": [
          "secureStorage",
          "hardwareBackedKey",
          "biometric",
          "attestation"
        ],
        "type": "object"
      }
    },
    "required": [
      "schemaVersion",
      "deviceId",
      "deviceClass",
      "runtime",
      "platform",
      "formFactor",
      "inputs",
      "outputs",
      "connectivity",
      "security",
      "localExecution"
    ],
    "title": "Kolibri device capability manifest",
    "type": "object"
  },
  "https://kolibriai.ru/contracts/v1/estimates/calculation-request.schema.json": {
    "$defs": {
      "decimal": {
        "pattern": "^(0|[1-9][0-9]*)(\\.[0-9]+)?$",
        "type": "string"
      },
      "identifier": {
        "maxLength": 160,
        "minLength": 1,
        "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:/-]*$",
        "type": "string"
      },
      "line": {
        "additionalProperties": false,
        "properties": {
          "category": {
            "enum": [
              "work",
              "material",
              "equipment",
              "service",
              "delivery",
              "other"
            ]
          },
          "id": {
            "$ref": "#/$defs/identifier"
          },
          "priceStatus": {
            "enum": [
              "missing",
              "preliminary",
              "source_backed",
              "verified"
            ]
          },
          "quantity": {
            "$ref": "#/$defs/decimal"
          },
          "sourceId": {
            "oneOf": [
              {
                "$ref": "#/$defs/identifier"
              },
              {
                "type": "null"
              }
            ]
          },
          "title": {
            "maxLength": 500,
            "minLength": 1,
            "type": "string"
          },
          "unit": {
            "maxLength": 32,
            "minLength": 1,
            "type": "string"
          },
          "unitPrice": {
            "oneOf": [
              {
                "$ref": "#/$defs/decimal"
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "id",
          "category",
          "title",
          "unit",
          "quantity",
          "unitPrice",
          "priceStatus",
          "sourceId"
        ],
        "type": "object"
      },
      "terms": {
        "additionalProperties": false,
        "properties": {
          "discountPercent": {
            "$ref": "#/$defs/decimal"
          },
          "overheadPercent": {
            "$ref": "#/$defs/decimal"
          },
          "profitPercent": {
            "$ref": "#/$defs/decimal"
          },
          "taxPercent": {
            "$ref": "#/$defs/decimal"
          }
        },
        "required": [
          "overheadPercent",
          "profitPercent",
          "discountPercent",
          "taxPercent"
        ],
        "type": "object"
      }
    },
    "$id": "https://kolibriai.ru/contracts/v1/estimates/calculation-request.schema.json",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "additionalProperties": false,
    "properties": {
      "calculationId": {
        "$ref": "#/$defs/identifier"
      },
      "currency": {
        "pattern": "^[A-Z]{3}$",
        "type": "string"
      },
      "lines": {
        "items": {
          "$ref": "#/$defs/line"
        },
        "maxItems": 10000,
        "minItems": 1,
        "type": "array"
      },
      "releaseMode": {
        "type": "boolean"
      },
      "rulesVersion": {
        "$ref": "#/$defs/identifier"
      },
      "schemaVersion": {
        "const": "1.0"
      },
      "terms": {
        "$ref": "#/$defs/terms"
      }
    },
    "required": [
      "schemaVersion",
      "calculationId",
      "currency",
      "rulesVersion",
      "releaseMode",
      "lines",
      "terms"
    ],
    "title": "Kolibri estimate calculation request v1",
    "type": "object"
  },
  "https://kolibriai.ru/contracts/v1/estimates/calculation-result.schema.json": {
    "$defs": {
      "decimal": {
        "pattern": "^(0|[1-9][0-9]*)(\\.[0-9]+)?$",
        "type": "string"
      }
    },
    "$id": "https://kolibriai.ru/contracts/v1/estimates/calculation-result.schema.json",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "additionalProperties": false,
    "properties": {
      "calculationId": {
        "type": "string"
      },
      "currency": {
        "pattern": "^[A-Z]{3}$",
        "type": "string"
      },
      "engineVersion": {
        "const": "kolibri-estimate-kernel/0.1.0",
        "type": "string"
      },
      "lines": {
        "items": {
          "additionalProperties": false,
          "properties": {
            "category": {
              "enum": [
                "work",
                "material",
                "equipment",
                "service",
                "delivery",
                "other"
              ]
            },
            "id": {
              "type": "string"
            },
            "normalizedQuantity": {
              "$ref": "#/$defs/decimal"
            },
            "priceStatus": {
              "enum": [
                "missing",
                "preliminary",
                "source_backed",
                "verified"
              ]
            },
            "sourceId": {
              "type": [
                "string",
                "null"
              ]
            },
            "subtotal": {
              "oneOf": [
                {
                  "$ref": "#/$defs/decimal"
                },
                {
                  "type": "null"
                }
              ]
            },
            "title": {
              "type": "string"
            },
            "unit": {
              "type": "string"
            },
            "unitPrice": {
              "oneOf": [
                {
                  "$ref": "#/$defs/decimal"
                },
                {
                  "type": "null"
                }
              ]
            }
          },
          "required": [
            "id",
            "category",
            "title",
            "unit",
            "normalizedQuantity",
            "unitPrice",
            "subtotal",
            "priceStatus",
            "sourceId"
          ],
          "type": "object"
        },
        "maxItems": 10000,
        "minItems": 1,
        "type": "array"
      },
      "roundingPolicy": {
        "additionalProperties": false,
        "properties": {
          "midpoint": {
            "const": "away_from_zero"
          },
          "moneyScale": {
            "const": 2
          },
          "quantityScale": {
            "const": 6
          }
        },
        "required": [
          "moneyScale",
          "quantityScale",
          "midpoint"
        ],
        "type": "object"
      },
      "rulesVersion": {
        "type": "string"
      },
      "schemaVersion": {
        "const": "1.0"
      },
      "totals": {
        "additionalProperties": false,
        "properties": {
          "byCategory": {
            "additionalProperties": false,
            "properties": {
              "delivery": {
                "$ref": "#/$defs/decimal"
              },
              "equipment": {
                "$ref": "#/$defs/decimal"
              },
              "material": {
                "$ref": "#/$defs/decimal"
              },
              "other": {
                "$ref": "#/$defs/decimal"
              },
              "service": {
                "$ref": "#/$defs/decimal"
              },
              "work": {
                "$ref": "#/$defs/decimal"
              }
            },
            "required": [
              "work",
              "material",
              "equipment",
              "service",
              "delivery",
              "other"
            ],
            "type": "object"
          },
          "complete": {
            "type": "boolean"
          },
          "directCost": {
            "$ref": "#/$defs/decimal"
          },
          "discount": {
            "$ref": "#/$defs/decimal"
          },
          "overhead": {
            "$ref": "#/$defs/decimal"
          },
          "profit": {
            "$ref": "#/$defs/decimal"
          },
          "tax": {
            "$ref": "#/$defs/decimal"
          },
          "total": {
            "$ref": "#/$defs/decimal"
          }
        },
        "required": [
          "byCategory",
          "directCost",
          "overhead",
          "profit",
          "discount",
          "tax",
          "total",
          "complete"
        ],
        "type": "object"
      },
      "validation": {
        "additionalProperties": false,
        "properties": {
          "missingPriceLineIds": {
            "items": {
              "type": "string"
            },
            "type": "array"
          },
          "preliminaryPriceLineIds": {
            "items": {
              "type": "string"
            },
            "type": "array"
          },
          "status": {
            "enum": [
              "passed",
              "blocked"
            ]
          }
        },
        "required": [
          "status",
          "missingPriceLineIds",
          "preliminaryPriceLineIds"
        ],
        "type": "object"
      }
    },
    "required": [
      "schemaVersion",
      "engineVersion",
      "calculationId",
      "currency",
      "rulesVersion",
      "roundingPolicy",
      "lines",
      "totals",
      "validation"
    ],
    "title": "Kolibri estimate calculation result v1",
    "type": "object"
  },
  "https://kolibriai.ru/contracts/v1/verticals/vertical-pack-manifest.schema.json": {
    "$defs": {
      "agentCapability": {
        "additionalProperties": false,
        "properties": {
          "humanApprovalRequired": {
            "type": "boolean"
          },
          "id": {
            "$ref": "#/$defs/capabilityId"
          },
          "inputContractId": {
            "$ref": "#/$defs/contractId"
          },
          "outputContractId": {
            "$ref": "#/$defs/contractId"
          }
        },
        "required": [
          "id",
          "inputContractId",
          "outputContractId",
          "humanApprovalRequired"
        ],
        "type": "object"
      },
      "artifactKind": {
        "additionalProperties": false,
        "properties": {
          "contractId": {
            "$ref": "#/$defs/contractId"
          },
          "editorKey": {
            "oneOf": [
              {
                "$ref": "#/$defs/contractId"
              },
              {
                "type": "null"
              }
            ]
          },
          "exportFormats": {
            "items": {
              "pattern": "^[a-z0-9][a-z0-9._-]{0,31}$",
              "type": "string"
            },
            "maxItems": 32,
            "type": "array",
            "uniqueItems": true
          },
          "kind": {
            "$ref": "#/$defs/capabilityId"
          },
          "rendererKey": {
            "$ref": "#/$defs/contractId"
          }
        },
        "required": [
          "kind",
          "contractId",
          "rendererKey",
          "editorKey",
          "exportFormats"
        ],
        "type": "object"
      },
      "capability": {
        "additionalProperties": false,
        "properties": {
          "clientSurfaces": {
            "$ref": "#/$defs/clientSurfaces"
          },
          "contractId": {
            "$ref": "#/$defs/contractId"
          },
          "id": {
            "$ref": "#/$defs/capabilityId"
          },
          "kind": {
            "enum": [
              "navigation",
              "workflow",
              "calculation",
              "source",
              "export",
              "integration"
            ]
          },
          "requiredEntitlement": {
            "$ref": "#/$defs/entitlement"
          }
        },
        "required": [
          "id",
          "kind",
          "contractId",
          "clientSurfaces",
          "requiredEntitlement"
        ],
        "type": "object"
      },
      "capabilityId": {
        "maxLength": 160,
        "minLength": 3,
        "pattern": "^[a-z][a-z0-9]*(\\.[a-z][a-z0-9_-]*)+$",
        "type": "string"
      },
      "clientSurfaces": {
        "items": {
          "enum": [
            "web",
            "ios",
            "android",
            "desktop"
          ]
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "contractId": {
        "maxLength": 240,
        "minLength": 3,
        "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:/-]*$",
        "type": "string"
      },
      "entitlement": {
        "maxLength": 160,
        "minLength": 3,
        "pattern": "^[a-z][a-z0-9]*(\\.[a-z][a-z0-9_-]*)+$",
        "type": "string"
      },
      "policies": {
        "additionalProperties": false,
        "properties": {
          "approvalPolicyId": {
            "$ref": "#/$defs/contractId"
          },
          "crossTenantSharingAllowed": {
            "const": false
          },
          "dataClassification": {
            "enum": [
              "business",
              "sensitive",
              "regulated"
            ]
          },
          "sourcePolicyId": {
            "$ref": "#/$defs/contractId"
          }
        },
        "required": [
          "dataClassification",
          "sourcePolicyId",
          "approvalPolicyId",
          "crossTenantSharingAllowed"
        ],
        "type": "object"
      }
    },
    "$id": "https://kolibriai.ru/contracts/v1/verticals/vertical-pack-manifest.schema.json",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "additionalProperties": false,
    "properties": {
      "agentCapabilities": {
        "items": {
          "$ref": "#/$defs/agentCapability"
        },
        "maxItems": 128,
        "type": "array"
      },
      "artifactKinds": {
        "items": {
          "$ref": "#/$defs/artifactKind"
        },
        "maxItems": 64,
        "type": "array"
      },
      "capabilities": {
        "items": {
          "$ref": "#/$defs/capability"
        },
        "maxItems": 128,
        "minItems": 1,
        "type": "array"
      },
      "displayName": {
        "additionalProperties": false,
        "properties": {
          "en": {
            "maxLength": 120,
            "minLength": 1,
            "type": "string"
          },
          "ru": {
            "maxLength": 120,
            "minLength": 1,
            "type": "string"
          }
        },
        "required": [
          "ru"
        ],
        "type": "object"
      },
      "packageVersion": {
        "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$",
        "type": "string"
      },
      "policies": {
        "$ref": "#/$defs/policies"
      },
      "schemaVersion": {
        "const": "1.0"
      },
      "verticalId": {
        "$ref": "#/$defs/capabilityId"
      }
    },
    "required": [
      "schemaVersion",
      "verticalId",
      "packageVersion",
      "displayName",
      "capabilities",
      "artifactKinds",
      "agentCapabilities",
      "policies"
    ],
    "title": "Kolibri vertical pack manifest v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/a2a/delivery-cursor.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/a2a/delivery-cursor.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "accepted_messages": {
        "additionalProperties": {
          "pattern": "^sha256:[0-9a-f]{64}$",
          "type": "string"
        },
        "type": "object"
      },
      "channel_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "deduplication_index": {
        "additionalProperties": {
          "additionalProperties": false,
          "properties": {
            "content_hash": {
              "pattern": "^sha256:[0-9a-f]{64}$",
              "type": "string"
            },
            "message_id": {
              "$ref": "#/definitions/opaque_id"
            }
          },
          "required": [
            "message_id",
            "content_hash"
          ],
          "type": "object"
        },
        "type": "object"
      },
      "last_message_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "last_sequence": {
        "minimum": 0,
        "type": "integer"
      },
      "schema_id": {
        "const": "kolibri.a2a.delivery_cursor"
      },
      "schema_version": {
        "const": "1.0"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "channel_id",
      "last_sequence",
      "last_message_id",
      "accepted_messages",
      "deduplication_index"
    ],
    "title": "Kolibri A2A delivery cursor v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/a2a/message.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/a2a/message.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "else": {
          "properties": {
            "previous_message_id": {
              "type": "string"
            }
          }
        },
        "if": {
          "properties": {
            "sequence": {
              "const": 1
            }
          },
          "required": [
            "sequence"
          ]
        },
        "then": {
          "properties": {
            "previous_message_id": {
              "type": "null"
            }
          }
        }
      }
    ],
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "a2a_message_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "channel_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "content": {
        "additionalProperties": false,
        "properties": {
          "reference_ids": {
            "items": {
              "$ref": "#/definitions/opaque_id"
            },
            "type": "array",
            "uniqueItems": true
          },
          "structured_data": {
            "type": "object"
          },
          "text": {
            "maxLength": 32000,
            "minLength": 1,
            "type": "string"
          },
          "trust": {
            "const": "untrusted_content"
          }
        },
        "required": [
          "trust",
          "text",
          "structured_data",
          "reference_ids"
        ],
        "type": "object"
      },
      "content_hash": {
        "pattern": "^sha256:[0-9a-f]{64}$",
        "type": "string"
      },
      "deduplication_key": {
        "maxLength": 200,
        "minLength": 16,
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._:~-]+$",
        "type": "string"
      },
      "expires_at": {
        "format": "date-time",
        "type": "string"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "message_type": {
        "enum": [
          "request",
          "clarification",
          "proposal",
          "challenge",
          "handoff",
          "review",
          "revision_request",
          "approval",
          "rejection",
          "escalation"
        ],
        "type": "string"
      },
      "previous_message_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "purpose": {
        "maxLength": 1000,
        "minLength": 1,
        "type": "string"
      },
      "recipient_assignment_ids": {
        "items": {
          "$ref": "#/definitions/opaque_id"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "recipient_capability": {
        "oneOf": [
          {
            "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "response_to_message_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "schema_id": {
        "const": "kolibri.a2a.message_appended.event"
      },
      "schema_version": {
        "const": "1.0"
      },
      "sender_actor_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "sender_assignment_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "sent_at": {
        "format": "date-time",
        "type": "string"
      },
      "sequence": {
        "minimum": 1,
        "type": "integer"
      },
      "task_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "task_version": {
        "minimum": 1,
        "type": "integer"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "a2a_message_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "task_version",
      "channel_id",
      "sequence",
      "previous_message_id",
      "sender_actor_id",
      "sender_assignment_id",
      "recipient_assignment_ids",
      "recipient_capability",
      "message_type",
      "purpose",
      "response_to_message_id",
      "content",
      "content_hash",
      "deduplication_key",
      "sent_at",
      "expires_at"
    ],
    "title": "Kolibri typed A2A message event payload v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/agents/agent-card.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/agents/agent-card.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "agent_card_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "agent_kind": {
        "enum": [
          "model",
          "worker",
          "human",
          "hybrid",
          "service"
        ],
        "type": "string"
      },
      "availability": {
        "enum": [
          "available",
          "busy",
          "degraded",
          "offline",
          "revoked"
        ],
        "type": "string"
      },
      "capabilities": {
        "items": {
          "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
          "type": "string"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "display_name": {
        "maxLength": 160,
        "minLength": 1,
        "type": "string"
      },
      "domain_tags": {
        "items": {
          "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
          "type": "string"
        },
        "type": "array",
        "uniqueItems": true
      },
      "jurisdictions": {
        "items": {
          "pattern": "^[A-Z]{2}(-[A-Z0-9]{1,8})?$",
          "type": "string"
        },
        "type": "array",
        "uniqueItems": true
      },
      "limits": {
        "additionalProperties": false,
        "properties": {
          "currency": {
            "pattern": "^[A-Z]{3}$",
            "type": "string"
          },
          "latency_slo_ms": {
            "minimum": 1,
            "type": "integer"
          },
          "max_concurrent_assignments": {
            "minimum": 1,
            "type": "integer"
          },
          "max_context_bytes": {
            "minimum": 1,
            "type": "integer"
          },
          "max_external_spend_minor": {
            "minimum": 0,
            "type": "integer"
          }
        },
        "required": [
          "max_concurrent_assignments",
          "max_context_bytes",
          "max_external_spend_minor",
          "currency",
          "latency_slo_ms"
        ],
        "type": "object"
      },
      "model_profiles": {
        "items": {
          "$ref": "#/definitions/opaque_id"
        },
        "type": "array",
        "uniqueItems": true
      },
      "policy_constraints": {
        "items": {
          "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
          "type": "string"
        },
        "type": "array",
        "uniqueItems": true
      },
      "schema_id": {
        "const": "kolibri.agent_card"
      },
      "schema_version": {
        "const": "1.0"
      },
      "skills": {
        "items": {
          "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
          "type": "string"
        },
        "type": "array",
        "uniqueItems": true
      },
      "tenant_scope": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "const": "platform"
          }
        ]
      },
      "tool_ids": {
        "items": {
          "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
          "type": "string"
        },
        "type": "array",
        "uniqueItems": true
      },
      "updated_at": {
        "format": "date-time",
        "type": "string"
      },
      "version": {
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "agent_card_id",
      "tenant_scope",
      "display_name",
      "agent_kind",
      "capabilities",
      "skills",
      "model_profiles",
      "tool_ids",
      "jurisdictions",
      "domain_tags",
      "limits",
      "availability",
      "policy_constraints",
      "version",
      "updated_at"
    ],
    "title": "Kolibri AgentCard v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/agents/assignment-status-changed-event.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/agents/assignment-status-changed-event.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "assignment_status": {
        "enum": [
          "pending",
          "active",
          "suspended",
          "completed",
          "revoked",
          "expired",
          "superseded"
        ],
        "type": "string"
      },
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "assignment_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "new_status": {
        "$ref": "#/definitions/assignment_status"
      },
      "new_version": {
        "minimum": 2,
        "type": "integer"
      },
      "previous_status": {
        "$ref": "#/definitions/assignment_status"
      },
      "previous_version": {
        "minimum": 1,
        "type": "integer"
      },
      "reason": {
        "maxLength": 2000,
        "minLength": 1,
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.agent_assignment.status_changed.event"
      },
      "schema_version": {
        "const": "1.0"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "assignment_id",
      "previous_status",
      "new_status",
      "previous_version",
      "new_version",
      "reason"
    ],
    "title": "Kolibri AgentAssignment status changed event payload v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/agents/assignment.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/agents/assignment.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "agent_card_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "agent_card_version": {
        "minimum": 1,
        "type": "integer"
      },
      "assignee_actor_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "assignment_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "attempt_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "authority_profile": {
        "$ref": "https://schemas.kolibriai.ru/v1/agents/authority-profile.schema.json"
      },
      "budget": {
        "additionalProperties": false,
        "properties": {
          "compute_units_limit": {
            "minimum": 0,
            "type": "integer"
          },
          "currency": {
            "pattern": "^[A-Z]{3}$",
            "type": "string"
          },
          "external_spend_limit_minor": {
            "minimum": 0,
            "type": "integer"
          },
          "tool_calls_limit": {
            "minimum": 0,
            "type": "integer"
          }
        },
        "required": [
          "compute_units_limit",
          "tool_calls_limit",
          "external_spend_limit_minor",
          "currency"
        ],
        "type": "object"
      },
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "context_slice": {
        "additionalProperties": false,
        "properties": {
          "artifact_refs": {
            "items": {
              "$ref": "#/definitions/opaque_id"
            },
            "type": "array",
            "uniqueItems": true
          },
          "assumption_ids": {
            "items": {
              "$ref": "#/definitions/opaque_id"
            },
            "type": "array",
            "uniqueItems": true
          },
          "case_version": {
            "minimum": 1,
            "type": "integer"
          },
          "classification": {
            "enum": [
              "public",
              "internal",
              "confidential",
              "restricted"
            ],
            "type": "string"
          },
          "decision_ids": {
            "items": {
              "$ref": "#/definitions/opaque_id"
            },
            "type": "array",
            "uniqueItems": true
          },
          "fact_ids": {
            "items": {
              "$ref": "#/definitions/opaque_id"
            },
            "type": "array",
            "uniqueItems": true
          },
          "max_bytes": {
            "minimum": 1,
            "type": "integer"
          }
        },
        "required": [
          "case_version",
          "fact_ids",
          "assumption_ids",
          "decision_ids",
          "artifact_refs",
          "classification",
          "max_bytes"
        ],
        "type": "object"
      },
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "deadline_at": {
        "format": "date-time",
        "type": "string"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "lease_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "purpose": {
        "maxLength": 2000,
        "minLength": 1,
        "type": "string"
      },
      "required_evidence_types": {
        "items": {
          "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
          "type": "string"
        },
        "type": "array",
        "uniqueItems": true
      },
      "required_output_ids": {
        "items": {
          "$ref": "#/definitions/opaque_id"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "schema_id": {
        "const": "kolibri.agent_assignment"
      },
      "schema_version": {
        "const": "1.0"
      },
      "status": {
        "enum": [
          "pending",
          "active",
          "suspended",
          "completed",
          "revoked",
          "expired",
          "superseded"
        ],
        "type": "string"
      },
      "task_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "task_version": {
        "minimum": 1,
        "type": "integer"
      },
      "temporary_role": {
        "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
        "type": "string"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "updated_at": {
        "format": "date-time",
        "type": "string"
      },
      "version": {
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "assignment_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "task_version",
      "attempt_id",
      "assignee_actor_id",
      "agent_card_id",
      "agent_card_version",
      "temporary_role",
      "purpose",
      "authority_profile",
      "context_slice",
      "budget",
      "lease_id",
      "deadline_at",
      "required_output_ids",
      "required_evidence_types",
      "status",
      "version",
      "created_at",
      "updated_at"
    ],
    "title": "Kolibri AgentAssignment v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/agents/authority-profile.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/agents/authority-profile.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "allowed_resource_refs": {
        "items": {
          "$ref": "#/definitions/opaque_id"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "allowed_tool_ids": {
        "items": {
          "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
          "type": "string"
        },
        "type": "array",
        "uniqueItems": true
      },
      "authority_epoch": {
        "minimum": 1,
        "type": "integer"
      },
      "authority_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "authority_role": {
        "const": "logical_home_control_plane"
      },
      "authorization_decision_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "capabilities": {
        "items": {
          "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
          "type": "string"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "expires_at": {
        "format": "date-time",
        "type": "string"
      }
    },
    "required": [
      "authority_id",
      "authority_role",
      "authority_epoch",
      "authorization_decision_id",
      "capabilities",
      "allowed_tool_ids",
      "allowed_resource_refs",
      "expires_at"
    ],
    "title": "Kolibri AssignmentAuthorityProfile v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/artifacts/artifact-state-transition.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/artifacts/artifact-state-transition.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "artifact_id": {
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "artifact_version": {
        "minimum": 1,
        "type": "integer"
      },
      "content_hash": {
        "pattern": "^sha256:[a-f0-9]{64}$",
        "type": "string"
      },
      "expected_state_version": {
        "minimum": 1,
        "type": "integer"
      },
      "from_status": {
        "$ref": "https://schemas.kolibriai.ru/v1/artifacts/artifact-state.schema.json#/definitions/status"
      },
      "invalidated_by": {
        "items": {
          "additionalProperties": false,
          "properties": {
            "content_hash": {
              "pattern": "^sha256:[a-f0-9]{64}$",
              "type": "string"
            },
            "ref_id": {
              "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
              "type": "string"
            },
            "ref_version": {
              "minimum": 1,
              "type": "integer"
            }
          },
          "required": [
            "ref_id",
            "ref_version",
            "content_hash"
          ],
          "type": "object"
        },
        "maxItems": 10000,
        "type": "array"
      },
      "next_state_version": {
        "minimum": 2,
        "type": "integer"
      },
      "reason": {
        "maxLength": 1000,
        "minLength": 1,
        "type": "string"
      },
      "requested_at": {
        "format": "date-time",
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.artifact.state.transition.command"
      },
      "schema_version": {
        "const": "1.0"
      },
      "to_status": {
        "$ref": "https://schemas.kolibriai.ru/v1/artifacts/artifact-state.schema.json#/definitions/status"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "artifact_id",
      "artifact_version",
      "content_hash",
      "expected_state_version",
      "next_state_version",
      "from_status",
      "to_status",
      "reason",
      "invalidated_by",
      "requested_at"
    ],
    "title": "Kolibri Artifact state transition command payload v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/artifacts/artifact-state.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/artifacts/artifact-state.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "if": {
          "properties": {
            "status": {
              "enum": [
                "stale",
                "revoked"
              ]
            }
          },
          "required": [
            "status"
          ]
        },
        "then": {
          "properties": {
            "reason": {
              "type": "string"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "status": {
              "const": "stale"
            }
          },
          "required": [
            "status"
          ]
        },
        "then": {
          "properties": {
            "invalidated_by": {
              "minItems": 1
            }
          }
        }
      }
    ],
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "sha256": {
        "pattern": "^sha256:[a-f0-9]{64}$",
        "type": "string"
      },
      "status": {
        "enum": [
          "draft",
          "in_review",
          "approved_internal",
          "released",
          "stale",
          "revoked",
          "superseded"
        ],
        "type": "string"
      }
    },
    "properties": {
      "artifact_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "artifact_version": {
        "minimum": 1,
        "type": "integer"
      },
      "changed_at": {
        "format": "date-time",
        "type": "string"
      },
      "content_hash": {
        "$ref": "#/definitions/sha256"
      },
      "invalidated_by": {
        "items": {
          "additionalProperties": false,
          "properties": {
            "content_hash": {
              "$ref": "#/definitions/sha256"
            },
            "ref_id": {
              "$ref": "#/definitions/opaque_id"
            },
            "ref_version": {
              "minimum": 1,
              "type": "integer"
            }
          },
          "required": [
            "ref_id",
            "ref_version",
            "content_hash"
          ],
          "type": "object"
        },
        "maxItems": 10000,
        "type": "array",
        "uniqueItems": true
      },
      "reason": {
        "oneOf": [
          {
            "maxLength": 1000,
            "minLength": 1,
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "schema_id": {
        "const": "kolibri.artifact_state"
      },
      "schema_version": {
        "const": "1.0"
      },
      "state_version": {
        "minimum": 1,
        "type": "integer"
      },
      "status": {
        "$ref": "#/definitions/status"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "artifact_id",
      "artifact_version",
      "content_hash",
      "tenant_id",
      "status",
      "state_version",
      "changed_at",
      "reason",
      "invalidated_by"
    ],
    "title": "Kolibri Artifact lifecycle projection v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/artifacts/artifact.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/artifacts/artifact.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "artifact_ref": {
        "additionalProperties": false,
        "properties": {
          "artifact_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "artifact_version": {
            "minimum": 1,
            "type": "integer"
          },
          "content_hash": {
            "$ref": "#/definitions/sha256"
          }
        },
        "required": [
          "artifact_id",
          "artifact_version",
          "content_hash"
        ],
        "type": "object"
      },
      "input_ref": {
        "additionalProperties": false,
        "properties": {
          "content_hash": {
            "$ref": "#/definitions/sha256"
          },
          "input_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "input_kind": {
            "enum": [
              "fact",
              "assumption",
              "decision",
              "domain_aggregate",
              "artifact",
              "source_document",
              "tool_result"
            ],
            "type": "string"
          },
          "ref_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "ref_version": {
            "minimum": 1,
            "type": "integer"
          },
          "role": {
            "maxLength": 240,
            "minLength": 1,
            "type": "string"
          }
        },
        "required": [
          "input_id",
          "input_kind",
          "ref_id",
          "ref_version",
          "content_hash",
          "role"
        ],
        "type": "object"
      },
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "provenance": {
        "additionalProperties": false,
        "properties": {
          "actor_or_tool_ref": {
            "$ref": "#/definitions/opaque_id"
          },
          "effective_at": {
            "oneOf": [
              {
                "format": "date-time",
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "kind": {
            "enum": [
              "user_input",
              "source_document",
              "calculation",
              "tool_execution",
              "model_generation",
              "human_edit"
            ],
            "type": "string"
          },
          "provenance_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "recorded_at": {
            "format": "date-time",
            "type": "string"
          },
          "source_ref": {
            "$ref": "#/definitions/opaque_id"
          }
        },
        "required": [
          "provenance_id",
          "kind",
          "source_ref",
          "recorded_at",
          "effective_at",
          "actor_or_tool_ref"
        ],
        "type": "object"
      },
      "sha256": {
        "pattern": "^sha256:[a-f0-9]{64}$",
        "type": "string"
      }
    },
    "properties": {
      "artifact_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "artifact_type": {
        "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
        "type": "string"
      },
      "artifact_version": {
        "minimum": 1,
        "type": "integer"
      },
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "content": {
        "additionalProperties": false,
        "properties": {
          "content_hash": {
            "$ref": "#/definitions/sha256"
          },
          "filename": {
            "maxLength": 240,
            "minLength": 1,
            "pattern": "^[^/\\\\\\u0000\\r\\n]+$",
            "type": "string"
          },
          "media_type": {
            "pattern": "^[a-z0-9][a-z0-9!#$&^_.+-]{0,126}/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}$",
            "type": "string"
          },
          "size_bytes": {
            "minimum": 0,
            "type": "integer"
          },
          "storage_ref": {
            "maxLength": 500,
            "minLength": 8,
            "pattern": "^(cas|artifact-store)://[A-Za-z0-9._~:/-]+$",
            "type": "string"
          }
        },
        "required": [
          "storage_ref",
          "media_type",
          "size_bytes",
          "content_hash",
          "filename"
        ],
        "type": "object"
      },
      "contract": {
        "additionalProperties": false,
        "properties": {
          "renderer_id": {
            "oneOf": [
              {
                "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "renderer_version": {
            "oneOf": [
              {
                "pattern": "^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$",
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "schema_id": {
            "pattern": "^kolibri\\.[a-z][a-z0-9_.]+$",
            "type": "string"
          },
          "schema_version": {
            "pattern": "^[1-9][0-9]*\\.[0-9]+$",
            "type": "string"
          }
        },
        "required": [
          "schema_id",
          "schema_version",
          "renderer_id",
          "renderer_version"
        ],
        "type": "object"
      },
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "created_by": {
        "$ref": "#/definitions/opaque_id"
      },
      "domain_output": {
        "additionalProperties": false,
        "properties": {
          "aggregate_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "aggregate_type": {
            "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
            "type": "string"
          },
          "aggregate_version": {
            "minimum": 1,
            "type": "integer"
          }
        },
        "required": [
          "aggregate_type",
          "aggregate_id",
          "aggregate_version"
        ],
        "type": "object"
      },
      "generator": {
        "additionalProperties": false,
        "properties": {
          "execution_ref": {
            "$ref": "#/definitions/opaque_id"
          },
          "generator_id": {
            "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
            "type": "string"
          },
          "generator_version": {
            "pattern": "^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$",
            "type": "string"
          }
        },
        "required": [
          "generator_id",
          "generator_version",
          "execution_ref"
        ],
        "type": "object"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "inputs": {
        "items": {
          "$ref": "#/definitions/input_ref"
        },
        "maxItems": 10000,
        "minItems": 1,
        "type": "array"
      },
      "provenance": {
        "items": {
          "$ref": "#/definitions/provenance"
        },
        "maxItems": 10000,
        "minItems": 1,
        "type": "array"
      },
      "schema_id": {
        "const": "kolibri.artifact"
      },
      "schema_version": {
        "const": "1.0"
      },
      "supersedes": {
        "oneOf": [
          {
            "$ref": "#/definitions/artifact_ref"
          },
          {
            "type": "null"
          }
        ]
      },
      "task_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "artifact_id",
      "artifact_version",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "artifact_type",
      "domain_output",
      "content",
      "contract",
      "generator",
      "inputs",
      "provenance",
      "supersedes",
      "created_by",
      "created_at"
    ],
    "title": "Kolibri immutable Artifact version v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/cases/assumption.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/cases/assumption.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "else": {
          "properties": {
            "superseded_by": {
              "type": "null"
            }
          }
        },
        "if": {
          "properties": {
            "status": {
              "const": "superseded"
            }
          },
          "required": [
            "status"
          ]
        },
        "then": {
          "properties": {
            "superseded_by": {
              "type": "string"
            }
          }
        }
      }
    ],
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "allowed_until_stage": {
        "enum": [
          "concept",
          "estimate_draft",
          "internal_review",
          "release"
        ],
        "type": "string"
      },
      "assumption_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "confidence": {
        "maximum": 1,
        "minimum": 0,
        "type": "number"
      },
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "impact": {
        "additionalProperties": false,
        "properties": {
          "severity": {
            "enum": [
              "low",
              "medium",
              "high",
              "critical"
            ],
            "type": "string"
          },
          "summary": {
            "maxLength": 1000,
            "minLength": 1,
            "type": "string"
          }
        },
        "required": [
          "severity",
          "summary"
        ],
        "type": "object"
      },
      "invalidation_targets": {
        "items": {
          "$ref": "#/definitions/opaque_id"
        },
        "maxItems": 200,
        "type": "array",
        "uniqueItems": true
      },
      "owner_actor_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "rationale": {
        "maxLength": 2000,
        "minLength": 1,
        "type": "string"
      },
      "statement": {
        "maxLength": 2000,
        "minLength": 1,
        "type": "string"
      },
      "status": {
        "enum": [
          "proposed",
          "active",
          "confirmed",
          "rejected",
          "superseded"
        ],
        "type": "string"
      },
      "superseded_by": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      }
    },
    "required": [
      "assumption_id",
      "statement",
      "rationale",
      "confidence",
      "impact",
      "allowed_until_stage",
      "owner_actor_id",
      "status",
      "invalidation_targets",
      "created_at",
      "superseded_by"
    ],
    "title": "Kolibri ProjectCase assumption v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/cases/decision.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/cases/decision.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "alternatives": {
        "items": {
          "maxLength": 1000,
          "minLength": 1,
          "type": "string"
        },
        "maxItems": 50,
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "authority_decision_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "consequences": {
        "items": {
          "maxLength": 1000,
          "minLength": 1,
          "type": "string"
        },
        "maxItems": 100,
        "type": "array"
      },
      "decided_at": {
        "format": "date-time",
        "type": "string"
      },
      "decision_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "effective_case_version": {
        "minimum": 1,
        "type": "integer"
      },
      "evidence_refs": {
        "items": {
          "$ref": "#/definitions/opaque_id"
        },
        "maxItems": 200,
        "type": "array",
        "uniqueItems": true
      },
      "made_by_actor_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "question": {
        "maxLength": 2000,
        "minLength": 1,
        "type": "string"
      },
      "selected_option": {
        "maxLength": 1000,
        "minLength": 1,
        "type": "string"
      },
      "selected_proposal_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "supersedes_decision_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      }
    },
    "required": [
      "decision_id",
      "question",
      "alternatives",
      "selected_option",
      "selected_proposal_id",
      "evidence_refs",
      "authority_decision_id",
      "made_by_actor_id",
      "effective_case_version",
      "consequences",
      "decided_at",
      "supersedes_decision_id"
    ],
    "title": "Kolibri ProjectCase decision v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/cases/fact.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/cases/fact.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "else": {
          "properties": {
            "superseded_by": {
              "type": "null"
            }
          }
        },
        "if": {
          "properties": {
            "status": {
              "const": "superseded"
            }
          },
          "required": [
            "status"
          ]
        },
        "then": {
          "properties": {
            "superseded_by": {
              "type": "string"
            }
          }
        }
      }
    ],
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "confidence": {
        "maximum": 1,
        "minimum": 0,
        "type": "number"
      },
      "fact_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "key": {
        "pattern": "^[a-z][a-z0-9_.-]{1,127}$",
        "type": "string"
      },
      "recorded_at": {
        "format": "date-time",
        "type": "string"
      },
      "source": {
        "additionalProperties": false,
        "properties": {
          "locator": {
            "maxLength": 1000,
            "minLength": 1,
            "type": "string"
          },
          "observed_at": {
            "format": "date-time",
            "type": "string"
          },
          "reference_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "source_type": {
            "enum": [
              "user_message",
              "uploaded_document",
              "measurement",
              "domain_artifact",
              "external_registry",
              "human_confirmation"
            ],
            "type": "string"
          }
        },
        "required": [
          "source_type",
          "reference_id",
          "locator",
          "observed_at"
        ],
        "type": "object"
      },
      "status": {
        "enum": [
          "active",
          "refuted",
          "superseded"
        ],
        "type": "string"
      },
      "superseded_by": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "unit": {
        "oneOf": [
          {
            "maxLength": 40,
            "minLength": 1,
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "value": {},
      "value_type": {
        "enum": [
          "text",
          "number",
          "boolean",
          "date",
          "quantity",
          "reference",
          "json"
        ],
        "type": "string"
      }
    },
    "required": [
      "fact_id",
      "key",
      "value",
      "value_type",
      "unit",
      "source",
      "confidence",
      "status",
      "recorded_at",
      "superseded_by"
    ],
    "title": "Kolibri ProjectCase fact v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/cases/open-question.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/cases/open-question.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "else": {
          "properties": {
            "resolved_at": {
              "type": "string"
            }
          }
        },
        "if": {
          "properties": {
            "status": {
              "const": "open"
            }
          },
          "required": [
            "status"
          ]
        },
        "then": {
          "properties": {
            "answer_ref": {
              "type": "null"
            },
            "resolved_at": {
              "type": "null"
            }
          }
        }
      }
    ],
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "answer_ref": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "answer_type": {
        "enum": [
          "text",
          "number",
          "boolean",
          "single_choice",
          "multiple_choice",
          "document"
        ],
        "type": "string"
      },
      "blocking": {
        "type": "boolean"
      },
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "options": {
        "items": {
          "maxLength": 500,
          "minLength": 1,
          "type": "string"
        },
        "maxItems": 100,
        "type": "array",
        "uniqueItems": true
      },
      "owner_actor_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "question": {
        "maxLength": 2000,
        "minLength": 1,
        "type": "string"
      },
      "question_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "reason": {
        "maxLength": 2000,
        "minLength": 1,
        "type": "string"
      },
      "resolved_at": {
        "oneOf": [
          {
            "format": "date-time",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "status": {
        "enum": [
          "open",
          "answered",
          "waived"
        ],
        "type": "string"
      }
    },
    "required": [
      "question_id",
      "question",
      "reason",
      "blocking",
      "answer_type",
      "options",
      "status",
      "owner_actor_id",
      "answer_ref",
      "created_at",
      "resolved_at"
    ],
    "title": "Kolibri ProjectCase open question v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/cases/project-case-transition.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/cases/project-case-transition.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "case_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "expected_version": {
        "minimum": 1,
        "type": "integer"
      },
      "from_status": {
        "$ref": "https://schemas.kolibriai.ru/v1/cases/project-case.schema.json#/definitions/status"
      },
      "next_version": {
        "minimum": 2,
        "type": "integer"
      },
      "reason": {
        "maxLength": 1000,
        "minLength": 1,
        "type": "string"
      },
      "requested_at": {
        "format": "date-time",
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.project_case.transition.command"
      },
      "schema_version": {
        "const": "1.0"
      },
      "to_status": {
        "$ref": "https://schemas.kolibriai.ru/v1/cases/project-case.schema.json#/definitions/status"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "case_id",
      "expected_version",
      "next_version",
      "from_status",
      "to_status",
      "reason",
      "requested_at"
    ],
    "title": "Kolibri ProjectCase transition command payload v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/cases/project-case.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/cases/project-case.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "statement_item": {
        "additionalProperties": false,
        "properties": {
          "item_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "source_ref": {
            "$ref": "#/definitions/opaque_id"
          },
          "statement": {
            "maxLength": 2000,
            "minLength": 1,
            "type": "string"
          },
          "status": {
            "enum": [
              "active",
              "satisfied",
              "violated",
              "superseded"
            ],
            "type": "string"
          }
        },
        "required": [
          "item_id",
          "statement",
          "source_ref",
          "status"
        ],
        "type": "object"
      },
      "status": {
        "enum": [
          "draft",
          "intake",
          "working",
          "blocked",
          "review",
          "approved_internal",
          "released",
          "superseded",
          "closed"
        ],
        "type": "string"
      },
      "versioned_ref": {
        "additionalProperties": false,
        "properties": {
          "ref_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "ref_type": {
            "pattern": "^[a-z][a-z0-9_.-]{1,127}$",
            "type": "string"
          },
          "version": {
            "minimum": 1,
            "type": "integer"
          }
        },
        "required": [
          "ref_type",
          "ref_id",
          "version"
        ],
        "type": "object"
      }
    },
    "properties": {
      "acceptance_criterion_ids": {
        "items": {
          "$ref": "#/definitions/opaque_id"
        },
        "maxItems": 100,
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "assumptions": {
        "items": {
          "$ref": "https://schemas.kolibriai.ru/v1/cases/assumption.schema.json"
        },
        "maxItems": 2000,
        "type": "array"
      },
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "constraints": {
        "items": {
          "$ref": "#/definitions/statement_item"
        },
        "maxItems": 1000,
        "type": "array"
      },
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "decisions": {
        "items": {
          "$ref": "https://schemas.kolibriai.ru/v1/cases/decision.schema.json"
        },
        "maxItems": 2000,
        "type": "array"
      },
      "domain_refs": {
        "items": {
          "$ref": "#/definitions/versioned_ref"
        },
        "maxItems": 5000,
        "type": "array"
      },
      "event_sequence": {
        "minimum": 0,
        "type": "integer"
      },
      "facts": {
        "items": {
          "$ref": "https://schemas.kolibriai.ru/v1/cases/fact.schema.json"
        },
        "maxItems": 5000,
        "type": "array"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "goal_version": {
        "minimum": 1,
        "type": "integer"
      },
      "intent_snapshot": {
        "additionalProperties": false,
        "properties": {
          "goal_version": {
            "minimum": 1,
            "type": "integer"
          },
          "normalized_objective": {
            "maxLength": 4000,
            "minLength": 1,
            "type": "string"
          }
        },
        "required": [
          "goal_version",
          "normalized_objective"
        ],
        "type": "object"
      },
      "open_questions": {
        "items": {
          "$ref": "https://schemas.kolibriai.ru/v1/cases/open-question.schema.json"
        },
        "maxItems": 500,
        "type": "array"
      },
      "proposals": {
        "items": {
          "$ref": "https://schemas.kolibriai.ru/v1/cases/proposal.schema.json"
        },
        "maxItems": 2000,
        "type": "array"
      },
      "requirements": {
        "items": {
          "$ref": "#/definitions/statement_item"
        },
        "maxItems": 1000,
        "type": "array"
      },
      "schema_id": {
        "const": "kolibri.project_case"
      },
      "schema_version": {
        "const": "1.0"
      },
      "status": {
        "$ref": "#/definitions/status"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "updated_at": {
        "format": "date-time",
        "type": "string"
      },
      "version": {
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "case_id",
      "goal_id",
      "goal_version",
      "tenant_id",
      "status",
      "version",
      "event_sequence",
      "intent_snapshot",
      "acceptance_criterion_ids",
      "facts",
      "assumptions",
      "proposals",
      "decisions",
      "open_questions",
      "requirements",
      "constraints",
      "domain_refs",
      "created_at",
      "updated_at"
    ],
    "title": "Kolibri ProjectCase aggregate v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/cases/proposal.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/cases/proposal.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "created_by_actor_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "evidence_refs": {
        "items": {
          "$ref": "#/definitions/opaque_id"
        },
        "maxItems": 200,
        "type": "array",
        "uniqueItems": true
      },
      "option": {
        "maxLength": 2000,
        "minLength": 1,
        "type": "string"
      },
      "proposal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "question": {
        "maxLength": 2000,
        "minLength": 1,
        "type": "string"
      },
      "rationale": {
        "maxLength": 2000,
        "minLength": 1,
        "type": "string"
      },
      "status": {
        "enum": [
          "open",
          "selected",
          "rejected",
          "superseded"
        ],
        "type": "string"
      }
    },
    "required": [
      "proposal_id",
      "question",
      "option",
      "rationale",
      "evidence_refs",
      "status",
      "created_by_actor_id",
      "created_at"
    ],
    "title": "Kolibri ProjectCase proposal v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/common/command-envelope.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/common/command-envelope.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "if": {
          "properties": {
            "idempotency": {
              "properties": {
                "scope": {
                  "const": "goal"
                }
              },
              "required": [
                "scope"
              ]
            }
          },
          "required": [
            "idempotency"
          ]
        },
        "then": {
          "properties": {
            "identity": {
              "properties": {
                "subject_refs": {
                  "properties": {
                    "goal_id": {
                      "type": "string"
                    }
                  }
                }
              }
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "idempotency": {
              "properties": {
                "scope": {
                  "const": "case"
                }
              },
              "required": [
                "scope"
              ]
            }
          },
          "required": [
            "idempotency"
          ]
        },
        "then": {
          "properties": {
            "identity": {
              "properties": {
                "subject_refs": {
                  "properties": {
                    "case_id": {
                      "type": "string"
                    }
                  }
                }
              }
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "idempotency": {
              "properties": {
                "scope": {
                  "const": "task"
                }
              },
              "required": [
                "scope"
              ]
            }
          },
          "required": [
            "idempotency"
          ]
        },
        "then": {
          "properties": {
            "identity": {
              "properties": {
                "subject_refs": {
                  "properties": {
                    "task_id": {
                      "type": "string"
                    }
                  }
                }
              }
            }
          }
        }
      }
    ],
    "properties": {
      "command_name": {
        "maxLength": 160,
        "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$",
        "type": "string"
      },
      "deadline_at": {
        "format": "date-time",
        "type": "string"
      },
      "idempotency": {
        "$ref": "https://schemas.kolibriai.ru/v1/common/idempotency.schema.json"
      },
      "identity": {
        "$ref": "https://schemas.kolibriai.ru/v1/common/identity.schema.json"
      },
      "issued_at": {
        "format": "date-time",
        "type": "string"
      },
      "message_id": {
        "pattern": "^cmd_[A-Za-z0-9][A-Za-z0-9._~-]{7,127}$",
        "type": "string"
      },
      "payload": {
        "type": "object"
      },
      "payload_schema_id": {
        "maxLength": 200,
        "pattern": "^kolibri\\.[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+\\.command$",
        "type": "string"
      },
      "payload_schema_version": {
        "maxLength": 20,
        "pattern": "^[1-9][0-9]*\\.[0-9]+$",
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.command"
      },
      "schema_version": {
        "const": "1.0"
      },
      "target_owner": {
        "enum": [
          "logical_home_control_plane",
          "product_data_authority",
          "provider_execution_authority"
        ],
        "type": "string"
      },
      "trace": {
        "$ref": "https://schemas.kolibriai.ru/v1/common/trace.schema.json"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "message_id",
      "command_name",
      "payload_schema_id",
      "payload_schema_version",
      "issued_at",
      "deadline_at",
      "target_owner",
      "identity",
      "trace",
      "idempotency",
      "payload"
    ],
    "title": "Kolibri command envelope v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/common/error-envelope.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/common/error-envelope.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "if": {
          "properties": {
            "retryable": {
              "const": false
            }
          },
          "required": [
            "retryable"
          ]
        },
        "then": {
          "properties": {
            "retry_after_ms": {
              "type": "null"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "retry_after_ms": {
              "type": "integer"
            }
          },
          "required": [
            "retry_after_ms"
          ]
        },
        "then": {
          "properties": {
            "retryable": {
              "const": true
            }
          }
        }
      }
    ],
    "properties": {
      "category": {
        "enum": [
          "validation",
          "authentication",
          "authorization",
          "conflict",
          "not_found",
          "capacity",
          "dependency",
          "timeout",
          "internal"
        ],
        "type": "string"
      },
      "code": {
        "pattern": "^[a-z][a-z0-9_]{2,95}$",
        "type": "string"
      },
      "details": {
        "type": "object"
      },
      "error_id": {
        "pattern": "^err_[A-Za-z0-9][A-Za-z0-9._~-]{7,127}$",
        "type": "string"
      },
      "http_status": {
        "maximum": 599,
        "minimum": 400,
        "type": "integer"
      },
      "in_response_to": {
        "oneOf": [
          {
            "maxLength": 160,
            "minLength": 8,
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "occurred_at": {
        "format": "date-time",
        "type": "string"
      },
      "retry_after_ms": {
        "oneOf": [
          {
            "maximum": 86400000,
            "minimum": 0,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ]
      },
      "retryable": {
        "type": "boolean"
      },
      "safe_message": {
        "maxLength": 500,
        "minLength": 1,
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.error"
      },
      "schema_version": {
        "const": "1.0"
      },
      "trace": {
        "$ref": "https://schemas.kolibriai.ru/v1/common/trace.schema.json"
      },
      "violations": {
        "items": {
          "additionalProperties": false,
          "properties": {
            "code": {
              "pattern": "^[a-z][a-z0-9_]{2,95}$",
              "type": "string"
            },
            "message": {
              "maxLength": 300,
              "type": "string"
            },
            "path": {
              "maxLength": 240,
              "type": "string"
            }
          },
          "required": [
            "path",
            "code",
            "message"
          ],
          "type": "object"
        },
        "maxItems": 100,
        "type": "array"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "error_id",
      "in_response_to",
      "occurred_at",
      "http_status",
      "code",
      "category",
      "retryable",
      "retry_after_ms",
      "safe_message",
      "trace",
      "violations",
      "details"
    ],
    "title": "Kolibri error envelope v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/common/event-envelope.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/common/event-envelope.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "if": {
          "properties": {
            "source_command_id": {
              "type": "string"
            }
          },
          "required": [
            "source_command_id"
          ]
        },
        "then": {
          "properties": {
            "trace": {
              "properties": {
                "causation_id": {
                  "type": "string"
                }
              }
            }
          }
        }
      }
    ],
    "properties": {
      "aggregate": {
        "additionalProperties": false,
        "properties": {
          "aggregate_id": {
            "maxLength": 160,
            "minLength": 8,
            "type": "string"
          },
          "aggregate_type": {
            "pattern": "^[a-z][a-z0-9_]{1,63}$",
            "type": "string"
          },
          "aggregate_version": {
            "minimum": 1,
            "type": "integer"
          }
        },
        "required": [
          "aggregate_type",
          "aggregate_id",
          "aggregate_version"
        ],
        "type": "object"
      },
      "deduplication_key": {
        "maxLength": 200,
        "minLength": 16,
        "type": "string"
      },
      "event_name": {
        "maxLength": 160,
        "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$",
        "type": "string"
      },
      "identity": {
        "$ref": "https://schemas.kolibriai.ru/v1/common/identity.schema.json"
      },
      "message_id": {
        "pattern": "^evt_[A-Za-z0-9][A-Za-z0-9._~-]{7,127}$",
        "type": "string"
      },
      "occurred_at": {
        "format": "date-time",
        "type": "string"
      },
      "payload": {
        "type": "object"
      },
      "payload_schema_id": {
        "maxLength": 200,
        "pattern": "^kolibri\\.[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+\\.event$",
        "type": "string"
      },
      "payload_schema_version": {
        "maxLength": 20,
        "pattern": "^[1-9][0-9]*\\.[0-9]+$",
        "type": "string"
      },
      "producer_owner": {
        "enum": [
          "logical_home_control_plane",
          "product_data_authority",
          "provider_execution_authority"
        ],
        "type": "string"
      },
      "recorded_at": {
        "format": "date-time",
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.event"
      },
      "schema_version": {
        "const": "1.0"
      },
      "source_command_id": {
        "oneOf": [
          {
            "pattern": "^cmd_[A-Za-z0-9][A-Za-z0-9._~-]{7,127}$",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "trace": {
        "$ref": "https://schemas.kolibriai.ru/v1/common/trace.schema.json"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "message_id",
      "event_name",
      "payload_schema_id",
      "payload_schema_version",
      "occurred_at",
      "recorded_at",
      "producer_owner",
      "identity",
      "trace",
      "aggregate",
      "source_command_id",
      "deduplication_key",
      "payload"
    ],
    "title": "Kolibri event envelope v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/common/idempotency.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/common/idempotency.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "canonical_request_hash": {
        "pattern": "^sha256:[0-9a-f]{64}$",
        "type": "string"
      },
      "key": {
        "maxLength": 200,
        "minLength": 16,
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._:~-]+$",
        "type": "string"
      },
      "scope": {
        "enum": [
          "tenant",
          "goal",
          "case",
          "task",
          "aggregate"
        ],
        "type": "string"
      },
      "scope_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "required": [
      "key",
      "scope",
      "scope_id",
      "canonical_request_hash"
    ],
    "title": "Kolibri command idempotency context v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/common/identity.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/common/identity.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "if": {
          "properties": {
            "user_id": {
              "type": "null"
            }
          },
          "required": [
            "user_id"
          ]
        },
        "then": {
          "properties": {
            "actor": {
              "properties": {
                "actor_type": {
                  "const": "system"
                }
              },
              "required": [
                "actor_type"
              ]
            }
          }
        }
      }
    ],
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "actor": {
        "additionalProperties": false,
        "properties": {
          "actor_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "actor_type": {
            "enum": [
              "user",
              "service",
              "agent",
              "system"
            ],
            "type": "string"
          }
        },
        "required": [
          "actor_id",
          "actor_type"
        ],
        "type": "object"
      },
      "authority": {
        "additionalProperties": false,
        "properties": {
          "authority_epoch": {
            "minimum": 1,
            "type": "integer"
          },
          "authority_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "authority_placement_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "authority_role": {
            "enum": [
              "logical_home_control_plane",
              "product_data_authority",
              "provider_execution_authority"
            ],
            "type": "string"
          },
          "authorization_decision_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "capabilities": {
            "items": {
              "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
              "type": "string"
            },
            "minItems": 1,
            "type": "array",
            "uniqueItems": true
          }
        },
        "required": [
          "authority_id",
          "authority_role",
          "authority_epoch",
          "authority_placement_id",
          "authorization_decision_id",
          "capabilities"
        ],
        "type": "object"
      },
      "subject_refs": {
        "additionalProperties": false,
        "allOf": [
          {
            "if": {
              "properties": {
                "case_id": {
                  "type": "string"
                }
              },
              "required": [
                "case_id"
              ]
            },
            "then": {
              "properties": {
                "goal_id": {
                  "type": "string"
                }
              }
            }
          },
          {
            "if": {
              "properties": {
                "task_id": {
                  "type": "string"
                }
              },
              "required": [
                "task_id"
              ]
            },
            "then": {
              "properties": {
                "case_id": {
                  "type": "string"
                },
                "goal_id": {
                  "type": "string"
                }
              }
            }
          }
        ],
        "properties": {
          "case_id": {
            "oneOf": [
              {
                "$ref": "#/definitions/opaque_id"
              },
              {
                "type": "null"
              }
            ]
          },
          "goal_id": {
            "oneOf": [
              {
                "$ref": "#/definitions/opaque_id"
              },
              {
                "type": "null"
              }
            ]
          },
          "task_id": {
            "oneOf": [
              {
                "$ref": "#/definitions/opaque_id"
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "goal_id",
          "case_id",
          "task_id"
        ],
        "type": "object"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "user_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      }
    },
    "required": [
      "tenant_id",
      "user_id",
      "actor",
      "authority",
      "subject_refs"
    ],
    "title": "Kolibri identity and authority context v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/common/trace.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/common/trace.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "causation_id": {
        "oneOf": [
          {
            "maxLength": 160,
            "minLength": 8,
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "correlation_id": {
        "maxLength": 160,
        "minLength": 8,
        "type": "string"
      },
      "parent_span_id": {
        "oneOf": [
          {
            "pattern": "^[0-9a-f]{16}$",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "span_id": {
        "pattern": "^[0-9a-f]{16}$",
        "type": "string"
      },
      "trace_id": {
        "pattern": "^[0-9a-f]{32}$",
        "type": "string"
      }
    },
    "required": [
      "trace_id",
      "span_id",
      "parent_span_id",
      "correlation_id",
      "causation_id"
    ],
    "title": "Kolibri trace context v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/documents/document-data.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/documents/document-data.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "attachments": {
        "items": {
          "maxLength": 255,
          "minLength": 1,
          "type": "string"
        },
        "type": "array"
      },
      "client_name": {
        "maxLength": 255,
        "minLength": 1,
        "type": "string"
      },
      "contractor_name": {
        "maxLength": 255,
        "minLength": 1,
        "type": "string"
      },
      "currency": {
        "pattern": "^[A-Z]{3}$",
        "type": "string"
      },
      "document_data_id": {
        "pattern": "^DOCDATA_[A-Z0-9]{10}$",
        "type": "string"
      },
      "document_type": {
        "enum": [
          "commercial_offer",
          "contract",
          "completion_act",
          "invoice"
        ],
        "type": "string"
      },
      "estimate_id": {
        "maxLength": 64,
        "minLength": 10,
        "pattern": "^EST-[A-Z0-9]{10,64}$",
        "type": "string"
      },
      "jurisdiction": {
        "pattern": "^[A-Z]{2}$",
        "type": "string"
      },
      "locale": {
        "pattern": "^[a-z]{2}(?:-[A-Z]{2})?$",
        "type": "string"
      },
      "provenance": {
        "additionalProperties": false,
        "properties": {
          "created_at": {
            "format": "date-time",
            "type": "string"
          },
          "estimate_fingerprint": {
            "pattern": "^[a-f0-9]{64}$",
            "type": "string"
          },
          "source_version": {
            "maxLength": 64,
            "minLength": 1,
            "type": "string"
          },
          "updated_at": {
            "format": "date-time",
            "type": "string"
          }
        },
        "required": [
          "created_at",
          "updated_at",
          "estimate_fingerprint"
        ],
        "type": "object"
      },
      "schema_id": {
        "const": "kolibri.document_data"
      },
      "schema_version": {
        "const": "1.0"
      },
      "sections": {
        "items": {
          "additionalProperties": false,
          "properties": {
            "kind": {
              "enum": [
                "text",
                "table",
                "disclaimer",
                "heading"
              ],
              "type": "string"
            },
            "rows": {
              "items": {
                "additionalProperties": true,
                "minProperties": 1,
                "type": "object"
              },
              "type": "array"
            },
            "text": {
              "minLength": 1,
              "type": "string"
            },
            "title": {
              "maxLength": 255,
              "minLength": 1,
              "type": "string"
            }
          },
          "required": [
            "title",
            "text"
          ],
          "type": "object"
        },
        "minItems": 1,
        "type": "array"
      },
      "title": {
        "maxLength": 255,
        "minLength": 1,
        "type": "string"
      },
      "total": {
        "pattern": "^\\d+(?:\\.\\d{1,4})?$",
        "type": "string"
      },
      "totals": {
        "additionalProperties": false,
        "properties": {
          "grand_total": {
            "pattern": "^\\d+(?:\\.\\d{1,4})?$",
            "type": "string"
          },
          "labor": {
            "pattern": "^\\d+(?:\\.\\d{1,4})?$",
            "type": "string"
          },
          "materials": {
            "pattern": "^\\d+(?:\\.\\d{1,4})?$",
            "type": "string"
          },
          "overhead": {
            "pattern": "^\\d+(?:\\.\\d{1,4})?$",
            "type": "string"
          }
        },
        "required": [
          "grand_total",
          "labor",
          "materials",
          "overhead"
        ],
        "type": "object"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "document_data_id",
      "document_type",
      "title",
      "client_name",
      "contractor_name",
      "estimate_id",
      "currency",
      "total",
      "locale",
      "jurisdiction",
      "sections",
      "totals",
      "attachments",
      "provenance"
    ],
    "title": "Kolibri document data payload v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/documents/document-render-request.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/documents/document-render-request.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "document_data": {
        "additionalProperties": false,
        "properties": {
          "attachments": {
            "items": {
              "maxLength": 255,
              "type": "string"
            },
            "type": "array"
          },
          "client_name": {
            "maxLength": 255,
            "minLength": 1,
            "type": "string"
          },
          "contractor_name": {
            "maxLength": 255,
            "minLength": 1,
            "type": "string"
          },
          "currency": {
            "pattern": "^[A-Z]{3}$",
            "type": "string"
          },
          "document_data_id": {
            "pattern": "^DOCDATA_[A-Z0-9]{10}$",
            "type": "string"
          },
          "document_type": {
            "enum": [
              "commercial_offer",
              "contract",
              "completion_act",
              "invoice"
            ],
            "type": "string"
          },
          "estimate_id": {
            "pattern": "^EST-[A-Z0-9]{10,64}$",
            "type": "string"
          },
          "jurisdiction": {
            "pattern": "^[A-Z]{2}$",
            "type": "string"
          },
          "locale": {
            "pattern": "^[a-z]{2}(?:-[A-Z]{2})?$",
            "type": "string"
          },
          "provenance": {
            "additionalProperties": false,
            "properties": {
              "created_at": {
                "format": "date-time",
                "type": "string"
              },
              "estimate_fingerprint": {
                "pattern": "^[a-f0-9]{64}$",
                "type": "string"
              },
              "updated_at": {
                "format": "date-time",
                "type": "string"
              }
            },
            "required": [
              "created_at",
              "updated_at",
              "estimate_fingerprint"
            ],
            "type": "object"
          },
          "sections": {
            "items": {
              "additionalProperties": false,
              "properties": {
                "kind": {
                  "enum": [
                    "text",
                    "table",
                    "disclaimer",
                    "heading"
                  ],
                  "type": "string"
                },
                "rows": {
                  "items": {
                    "additionalProperties": true,
                    "minProperties": 1,
                    "type": "object"
                  },
                  "type": "array"
                },
                "text": {
                  "minLength": 1,
                  "type": "string"
                },
                "title": {
                  "maxLength": 255,
                  "minLength": 1,
                  "type": "string"
                }
              },
              "required": [
                "title",
                "text"
              ],
              "type": "object"
            },
            "minItems": 1,
            "type": "array"
          },
          "title": {
            "maxLength": 255,
            "minLength": 1,
            "type": "string"
          },
          "total": {
            "pattern": "^\\d+(?:\\.\\d{1,4})?$",
            "type": "string"
          },
          "totals": {
            "additionalProperties": false,
            "properties": {
              "grand_total": {
                "pattern": "^\\d+(?:\\.\\d{1,4})?$",
                "type": "string"
              },
              "labor": {
                "pattern": "^\\d+(?:\\.\\d{1,4})?$",
                "type": "string"
              },
              "materials": {
                "pattern": "^\\d+(?:\\.\\d{1,4})?$",
                "type": "string"
              },
              "overhead": {
                "pattern": "^\\d+(?:\\.\\d{1,4})?$",
                "type": "string"
              }
            },
            "required": [
              "grand_total",
              "labor",
              "materials",
              "overhead"
            ],
            "type": "object"
          }
        },
        "required": [
          "document_data_id",
          "document_type",
          "title",
          "client_name",
          "contractor_name",
          "estimate_id",
          "currency",
          "total",
          "locale",
          "jurisdiction",
          "sections",
          "totals",
          "attachments",
          "provenance"
        ],
        "type": "object"
      },
      "idempotency_key": {
        "maxLength": 120,
        "minLength": 6,
        "type": "string"
      },
      "project_id": {
        "maxLength": 64,
        "minLength": 8,
        "type": "string"
      },
      "request_id": {
        "maxLength": 64,
        "minLength": 10,
        "pattern": "^REQ-[A-Z0-9]{10,54}$",
        "type": "string"
      },
      "requested_outputs": {
        "items": {
          "enum": [
            "pdf",
            "docx",
            "xlsx"
          ],
          "type": "string"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "schema_id": {
        "const": "kolibri.document_render_request"
      },
      "schema_version": {
        "const": "1.0"
      },
      "template_id": {
        "pattern": "^[a-z0-9_\\-]+\\.v[0-9]+$",
        "type": "string"
      },
      "template_jurisdiction": {
        "pattern": "^[A-Z]{2}$",
        "type": "string"
      },
      "template_locale": {
        "pattern": "^[a-z]{2}(?:-[A-Z]{2})?$",
        "type": "string"
      },
      "template_version": {
        "pattern": "^\\d+\\.\\d+(?:\\.\\d+)?$",
        "type": "string"
      },
      "tenant_id": {
        "maxLength": 64,
        "minLength": 8,
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "request_id",
      "template_id",
      "template_version",
      "template_locale",
      "template_jurisdiction",
      "requested_outputs",
      "document_data"
    ],
    "title": "Kolibri document render request v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/documents/document-render-result.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/documents/document-render-result.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "else": {
          "required": [
            "error"
          ]
        },
        "if": {
          "properties": {
            "status": {
              "const": "rendered"
            }
          }
        },
        "then": {
          "properties": {
            "assets": {
              "minItems": 1
            },
            "error": {
              "type": "null"
            }
          },
          "required": [
            "assets"
          ]
        }
      }
    ],
    "properties": {
      "assets": {
        "items": {
          "additionalProperties": false,
          "properties": {
            "content_type": {
              "pattern": "^[a-z]+/[a-z0-9.+-]+$",
              "type": "string"
            },
            "format": {
              "enum": [
                "pdf",
                "docx",
                "xlsx"
              ],
              "type": "string"
            },
            "path": {
              "maxLength": 255,
              "minLength": 1,
              "type": "string"
            },
            "sha256": {
              "pattern": "^[a-f0-9]{64}$",
              "type": "string"
            },
            "size_bytes": {
              "minimum": 1,
              "type": "integer"
            }
          },
          "required": [
            "format",
            "content_type",
            "path",
            "size_bytes",
            "sha256"
          ],
          "type": "object"
        },
        "minItems": 0,
        "type": "array"
      },
      "document_id": {
        "pattern": "^DOC-[A-Z0-9]{10}$",
        "type": "string"
      },
      "error": {
        "maxLength": 400,
        "type": "string"
      },
      "generated_at": {
        "format": "date-time",
        "type": "string"
      },
      "rendered_jurisdiction": {
        "pattern": "^[A-Z]{2}$",
        "type": "string"
      },
      "rendered_locale": {
        "pattern": "^[a-z]{2}(?:-[A-Z]{2})?$",
        "type": "string"
      },
      "request_id": {
        "pattern": "^REQ-[A-Z0-9]{10,54}$",
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.document_render_result"
      },
      "schema_version": {
        "const": "1.0"
      },
      "status": {
        "enum": [
          "rendered",
          "failed",
          "deferred"
        ],
        "type": "string"
      },
      "template_id": {
        "pattern": "^[a-z0-9_\\-]+\\.v[0-9]+$",
        "type": "string"
      },
      "template_version": {
        "pattern": "^\\d+\\.\\d+(?:\\.\\d+)?$",
        "type": "string"
      },
      "warnings": {
        "items": {
          "maxLength": 200,
          "type": "string"
        },
        "type": "array"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "request_id",
      "document_id",
      "template_id",
      "template_version",
      "status",
      "generated_at",
      "assets"
    ],
    "title": "Kolibri document render result v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/documents/document-template-registry.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/documents/document-template-registry.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "generated_at": {
        "format": "date-time",
        "type": "string"
      },
      "registry_id": {
        "maxLength": 64,
        "minLength": 8,
        "pattern": "^[a-z0-9_\\-]+$",
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.document_template_registry"
      },
      "schema_version": {
        "const": "1.0"
      },
      "templates": {
        "items": {
          "additionalProperties": false,
          "properties": {
            "document_type": {
              "enum": [
                "commercial_offer",
                "contract",
                "completion_act",
                "invoice"
              ],
              "type": "string"
            },
            "jurisdictions": {
              "items": {
                "pattern": "^[A-Z]{2}$",
                "type": "string"
              },
              "minItems": 1,
              "type": "array",
              "uniqueItems": true
            },
            "layout_fingerprint": {
              "pattern": "^[a-f0-9]{64}$",
              "type": "string"
            },
            "locale": {
              "pattern": "^[a-z]{2}(?:-[A-Z]{2})?$",
              "type": "string"
            },
            "output_formats": {
              "items": {
                "enum": [
                  "pdf",
                  "docx",
                  "xlsx"
                ],
                "type": "string"
              },
              "minItems": 1,
              "type": "array",
              "uniqueItems": true
            },
            "render_enabled": {
              "type": "boolean"
            },
            "template_id": {
              "pattern": "^[a-z0-9_\\-]+\\.v[0-9]+$",
              "type": "string"
            },
            "template_version": {
              "pattern": "^\\d+\\.\\d+(?:\\.\\d+)?$",
              "type": "string"
            }
          },
          "required": [
            "template_id",
            "template_version",
            "document_type",
            "locale",
            "jurisdictions",
            "output_formats",
            "layout_fingerprint",
            "render_enabled"
          ],
          "type": "object"
        },
        "maxItems": 50,
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "registry_id",
      "generated_at",
      "templates"
    ],
    "title": "Kolibri document template registry v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/documents/document-template.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/documents/document-template.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "if": {
          "properties": {
            "output_formats": {
              "contains": {
                "const": "xlsx"
              }
            }
          }
        },
        "then": {
          "properties": {
            "required_fields": {
              "contains": {
                "const": "totals"
              }
            }
          },
          "required": [
            "required_fields"
          ]
        }
      }
    ],
    "properties": {
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "data_contract": {
        "additionalProperties": false,
        "properties": {
          "schema_id": {
            "const": "kolibri.document_data",
            "type": "string"
          },
          "schema_version": {
            "const": "1.0",
            "type": "string"
          }
        },
        "required": [
          "schema_id",
          "schema_version"
        ],
        "type": "object"
      },
      "document_type": {
        "enum": [
          "commercial_offer",
          "contract",
          "completion_act",
          "invoice"
        ],
        "type": "string"
      },
      "jurisdictions": {
        "items": {
          "pattern": "^[A-Z]{2}$",
          "type": "string"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "layout_fingerprint": {
        "pattern": "^[a-f0-9]{64}$",
        "type": "string"
      },
      "locale": {
        "pattern": "^[a-z]{2}(?:-[A-Z]{2})?$",
        "type": "string"
      },
      "notes": {
        "maxLength": 400,
        "type": "string"
      },
      "output_formats": {
        "items": {
          "enum": [
            "pdf",
            "docx",
            "xlsx"
          ],
          "type": "string"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "prohibited_fields": {
        "items": {
          "maxLength": 80,
          "minLength": 1,
          "type": "string"
        },
        "type": "array"
      },
      "reproducible": {
        "type": "boolean"
      },
      "required_fields": {
        "items": {
          "maxLength": 80,
          "minLength": 1,
          "type": "string"
        },
        "minItems": 1,
        "type": "array"
      },
      "schema_id": {
        "const": "kolibri.document_template"
      },
      "schema_version": {
        "const": "1.0"
      },
      "template_id": {
        "maxLength": 120,
        "minLength": 5,
        "pattern": "^[a-z0-9_\\-]+\\.v[0-9]+$",
        "type": "string"
      },
      "template_version": {
        "pattern": "^\\d+\\.\\d+(?:\\.\\d+)?$",
        "type": "string"
      },
      "updated_at": {
        "format": "date-time",
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "template_id",
      "template_version",
      "document_type",
      "locale",
      "jurisdictions",
      "output_formats",
      "data_contract",
      "layout_fingerprint",
      "required_fields",
      "prohibited_fields",
      "reproducible",
      "created_at",
      "updated_at"
    ],
    "title": "Kolibri document template contract v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/goals/goal-change-event.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/goals/goal-change-event.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "else": {
          "properties": {
            "previous_status": {
              "type": "string"
            },
            "previous_version": {
              "type": "integer"
            }
          }
        },
        "if": {
          "properties": {
            "change_type": {
              "const": "created"
            }
          },
          "required": [
            "change_type"
          ]
        },
        "then": {
          "properties": {
            "command_name": {
              "const": "goal.create"
            },
            "new_status": {
              "const": "new"
            },
            "new_version": {
              "const": 1
            },
            "previous_status": {
              "type": "null"
            },
            "previous_version": {
              "type": "null"
            },
            "reason_provided": {
              "const": false
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "change_type": {
              "const": "updated"
            }
          },
          "required": [
            "change_type"
          ]
        },
        "then": {
          "properties": {
            "command_name": {
              "const": "goal.update"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "change_type": {
              "enum": [
                "transitioned",
                "cancelled",
                "completed"
              ]
            }
          },
          "required": [
            "change_type"
          ]
        },
        "then": {
          "properties": {
            "command_name": {
              "const": "goal.transition"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "change_type": {
              "const": "cancelled"
            }
          },
          "required": [
            "change_type"
          ]
        },
        "then": {
          "properties": {
            "new_status": {
              "const": "cancelled"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "change_type": {
              "const": "completed"
            }
          },
          "required": [
            "change_type"
          ]
        },
        "then": {
          "properties": {
            "new_status": {
              "const": "completed"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "change_type": {
              "const": "transitioned"
            }
          },
          "required": [
            "change_type"
          ]
        },
        "then": {
          "properties": {
            "new_status": {
              "enum": [
                "new",
                "intake",
                "planning",
                "executing",
                "reviewing",
                "awaiting_user",
                "awaiting_approval",
                "awaiting_payment",
                "awaiting_external",
                "revising",
                "approved_internal",
                "released",
                "executing_physical",
                "failed_recoverable",
                "superseded"
              ]
            }
          }
        }
      }
    ],
    "properties": {
      "change_type": {
        "enum": [
          "created",
          "updated",
          "transitioned",
          "cancelled",
          "completed"
        ],
        "type": "string"
      },
      "command_name": {
        "enum": [
          "goal.create",
          "goal.update",
          "goal.transition"
        ],
        "type": "string"
      },
      "goal_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "new_status": {
        "$ref": "https://schemas.kolibriai.ru/v1/goals/goal.schema.json#/definitions/status"
      },
      "new_version": {
        "minimum": 1,
        "type": "integer"
      },
      "previous_status": {
        "oneOf": [
          {
            "$ref": "https://schemas.kolibriai.ru/v1/goals/goal.schema.json#/definitions/status"
          },
          {
            "type": "null"
          }
        ]
      },
      "previous_version": {
        "oneOf": [
          {
            "minimum": 1,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ]
      },
      "reason_provided": {
        "type": "boolean"
      },
      "schema_id": {
        "const": "kolibri.goal.changed.event"
      },
      "schema_version": {
        "const": "1.0"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "goal_id",
      "command_name",
      "change_type",
      "previous_version",
      "new_version",
      "previous_status",
      "new_status",
      "reason_provided"
    ],
    "title": "Kolibri Goal changed event payload v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/goals/goal-create.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/goals/goal-create.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "goal": {
        "$ref": "https://schemas.kolibriai.ru/v1/goals/goal.schema.json"
      },
      "requested_at": {
        "format": "date-time",
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.goal.create.command"
      },
      "schema_version": {
        "const": "1.0"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "goal",
      "requested_at"
    ],
    "title": "Kolibri Goal create command payload v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/goals/goal-transition.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/goals/goal-transition.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "expected_version": {
        "minimum": 1,
        "type": "integer"
      },
      "from_status": {
        "$ref": "https://schemas.kolibriai.ru/v1/goals/goal.schema.json#/definitions/status"
      },
      "goal_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "next_version": {
        "minimum": 2,
        "type": "integer"
      },
      "reason": {
        "maxLength": 1000,
        "minLength": 1,
        "type": "string"
      },
      "requested_at": {
        "format": "date-time",
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.goal.transition.command"
      },
      "schema_version": {
        "const": "1.0"
      },
      "to_status": {
        "$ref": "https://schemas.kolibriai.ru/v1/goals/goal.schema.json#/definitions/status"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "goal_id",
      "expected_version",
      "next_version",
      "from_status",
      "to_status",
      "reason",
      "requested_at"
    ],
    "title": "Kolibri Goal transition command payload v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/goals/goal-update.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/goals/goal-update.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "expected_version": {
        "minimum": 1,
        "type": "integer"
      },
      "goal": {
        "$ref": "https://schemas.kolibriai.ru/v1/goals/goal.schema.json"
      },
      "goal_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "next_version": {
        "minimum": 2,
        "type": "integer"
      },
      "reason": {
        "maxLength": 1000,
        "minLength": 1,
        "type": "string"
      },
      "requested_at": {
        "format": "date-time",
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.goal.update.command"
      },
      "schema_version": {
        "const": "1.0"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "goal_id",
      "expected_version",
      "next_version",
      "goal",
      "reason",
      "requested_at"
    ],
    "title": "Kolibri Goal update command payload v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/goals/goal.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/goals/goal.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "else": {
          "properties": {
            "current_case_version": {
              "type": "integer"
            }
          }
        },
        "if": {
          "properties": {
            "case_id": {
              "type": "null"
            }
          },
          "required": [
            "case_id"
          ]
        },
        "then": {
          "properties": {
            "current_case_version": {
              "type": "null"
            }
          }
        }
      },
      {
        "else": {
          "properties": {
            "current_workflow_version": {
              "type": "integer"
            }
          }
        },
        "if": {
          "properties": {
            "workflow_id": {
              "type": "null"
            }
          },
          "required": [
            "workflow_id"
          ]
        },
        "then": {
          "properties": {
            "current_workflow_version": {
              "type": "null"
            }
          }
        }
      }
    ],
    "definitions": {
      "acceptance_criterion": {
        "additionalProperties": false,
        "properties": {
          "criterion_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "required": {
            "type": "boolean"
          },
          "statement": {
            "maxLength": 1000,
            "minLength": 1,
            "type": "string"
          },
          "status": {
            "enum": [
              "pending",
              "satisfied",
              "waived",
              "failed"
            ],
            "type": "string"
          },
          "verification_method": {
            "maxLength": 1000,
            "minLength": 1,
            "type": "string"
          }
        },
        "required": [
          "criterion_id",
          "statement",
          "verification_method",
          "required",
          "status"
        ],
        "type": "object"
      },
      "budget_policy": {
        "additionalProperties": false,
        "properties": {
          "approval_required_above_minor": {
            "minimum": 0,
            "type": "integer"
          },
          "compute_units_limit": {
            "minimum": 1,
            "type": "integer"
          },
          "currency": {
            "pattern": "^[A-Z]{3}$",
            "type": "string"
          },
          "external_spend_limit_minor": {
            "minimum": 0,
            "type": "integer"
          },
          "human_services_limit_minor": {
            "minimum": 0,
            "type": "integer"
          },
          "tool_calls_limit": {
            "minimum": 0,
            "type": "integer"
          }
        },
        "required": [
          "currency",
          "compute_units_limit",
          "tool_calls_limit",
          "external_spend_limit_minor",
          "human_services_limit_minor",
          "approval_required_above_minor"
        ],
        "type": "object"
      },
      "deadline_policy": {
        "additionalProperties": false,
        "properties": {
          "due_at": {
            "oneOf": [
              {
                "format": "date-time",
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "late_action": {
            "enum": [
              "continue_and_flag",
              "escalate",
              "pause"
            ],
            "type": "string"
          },
          "timezone": {
            "maxLength": 100,
            "minLength": 1,
            "type": "string"
          }
        },
        "required": [
          "due_at",
          "timezone",
          "late_action"
        ],
        "type": "object"
      },
      "intent": {
        "additionalProperties": false,
        "properties": {
          "locale": {
            "pattern": "^[a-z]{2}(?:-[A-Z]{2})?$",
            "type": "string"
          },
          "normalized_objective": {
            "maxLength": 4000,
            "minLength": 1,
            "type": "string"
          },
          "original_request": {
            "maxLength": 20000,
            "minLength": 1,
            "type": "string"
          },
          "source_message_id": {
            "$ref": "#/definitions/opaque_id"
          }
        },
        "required": [
          "source_message_id",
          "original_request",
          "normalized_objective",
          "locale"
        ],
        "type": "object"
      },
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "status": {
        "enum": [
          "new",
          "intake",
          "planning",
          "executing",
          "reviewing",
          "awaiting_user",
          "awaiting_approval",
          "awaiting_payment",
          "awaiting_external",
          "revising",
          "approved_internal",
          "released",
          "executing_physical",
          "completed",
          "failed_recoverable",
          "cancelled",
          "superseded"
        ],
        "type": "string"
      }
    },
    "properties": {
      "acceptance_criteria": {
        "items": {
          "$ref": "#/definitions/acceptance_criterion"
        },
        "maxItems": 100,
        "minItems": 1,
        "type": "array"
      },
      "blocking_question_ids": {
        "items": {
          "$ref": "#/definitions/opaque_id"
        },
        "maxItems": 50,
        "type": "array",
        "uniqueItems": true
      },
      "budget_policy": {
        "$ref": "#/definitions/budget_policy"
      },
      "case_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "current_case_version": {
        "oneOf": [
          {
            "minimum": 1,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ]
      },
      "current_workflow_version": {
        "oneOf": [
          {
            "minimum": 1,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ]
      },
      "deadline_policy": {
        "$ref": "#/definitions/deadline_policy"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "intent": {
        "$ref": "#/definitions/intent"
      },
      "schema_id": {
        "const": "kolibri.goal"
      },
      "schema_version": {
        "const": "1.0"
      },
      "status": {
        "$ref": "#/definitions/status"
      },
      "supersedes_goal_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "updated_at": {
        "format": "date-time",
        "type": "string"
      },
      "user_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "version": {
        "minimum": 1,
        "type": "integer"
      },
      "workflow_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "goal_id",
      "tenant_id",
      "user_id",
      "intent",
      "acceptance_criteria",
      "budget_policy",
      "deadline_policy",
      "status",
      "blocking_question_ids",
      "case_id",
      "current_case_version",
      "workflow_id",
      "current_workflow_version",
      "version",
      "supersedes_goal_id",
      "created_at",
      "updated_at"
    ],
    "title": "Kolibri Goal aggregate v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/agui-projection.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/agui-projection.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "adapter_package": {
        "const": "@assistant-ui/react-ag-ui"
      },
      "adapter_version": {
        "const": "0.0.45"
      },
      "custom_schema_id": {
        "oneOf": [
          {
            "pattern": "^kolibri\\.product\\.agui\\.custom\\.[a-z][a-z0-9_.:-]{2,127}$",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "custom_schema_version": {
        "oneOf": [
          {
            "pattern": "^[1-9][0-9]*\\.[0-9]+$",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "event_type": {
        "enum": [
          "RUN_STARTED",
          "RUN_FINISHED",
          "RUN_CANCELLED",
          "RUN_ERROR",
          "TEXT_MESSAGE_START",
          "TEXT_MESSAGE_CONTENT",
          "TEXT_MESSAGE_END",
          "TEXT_MESSAGE_CHUNK",
          "TOOL_CALL_START",
          "TOOL_CALL_ARGS",
          "TOOL_CALL_END",
          "TOOL_CALL_CHUNK",
          "TOOL_CALL_RESULT",
          "STATE_SNAPSHOT",
          "STATE_DELTA",
          "MESSAGES_SNAPSHOT",
          "CUSTOM"
        ],
        "type": "string"
      },
      "payload": {
        "maxProperties": 128,
        "type": "object"
      },
      "projected_at": {
        "format": "date-time",
        "type": "string"
      },
      "protocol": {
        "const": "ag-ui"
      },
      "protocol_version": {
        "const": "0.0.57"
      },
      "run_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "schema_id": {
        "const": "kolibri.product.agui.projection"
      },
      "schema_version": {
        "const": "1.0"
      },
      "source_event_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "source_sequence": {
        "minimum": 1,
        "type": "integer"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "thread_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "thread_id",
      "run_id",
      "source_event_id",
      "source_sequence",
      "protocol",
      "protocol_version",
      "adapter_package",
      "adapter_version",
      "event_type",
      "custom_schema_id",
      "custom_schema_version",
      "payload",
      "projected_at"
    ],
    "title": "Kolibri Product AG-UI Projection v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/attachment.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/attachment.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "artifact_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "artifact_version": {
        "minimum": 1,
        "type": "integer"
      },
      "attachment_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "content_hash": {
        "pattern": "^sha256:[0-9a-f]{64}$",
        "type": "string"
      },
      "content_path": {
        "pattern": "^/api/product/v1/attachments/attachment_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}/content$",
        "type": "string"
      },
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "created_by": {
        "$ref": "#/definitions/opaque_id"
      },
      "filename": {
        "maxLength": 512,
        "minLength": 1,
        "type": "string"
      },
      "mime_type": {
        "maxLength": 160,
        "minLength": 3,
        "type": "string"
      },
      "project_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "schema_id": {
        "const": "kolibri.product.attachment"
      },
      "schema_version": {
        "const": "1.0"
      },
      "size_bytes": {
        "maximum": 52428800,
        "minimum": 1,
        "type": "integer"
      },
      "status": {
        "const": "available"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "user_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "user_id",
      "project_id",
      "attachment_id",
      "artifact_id",
      "artifact_version",
      "content_hash",
      "filename",
      "mime_type",
      "size_bytes",
      "content_path",
      "status",
      "created_by",
      "created_at"
    ],
    "title": "Kolibri Product Attachment v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/delivery-cursor.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/delivery-cursor.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "issued_at": {
        "format": "date-time",
        "type": "string"
      },
      "last_event_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "last_sequence": {
        "minimum": 0,
        "type": "integer"
      },
      "ledger_version": {
        "minimum": 1,
        "type": "integer"
      },
      "project_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "run_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "schema_id": {
        "const": "kolibri.product.delivery_cursor"
      },
      "schema_version": {
        "const": "1.0"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "thread_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "user_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "user_id",
      "project_id",
      "thread_id",
      "run_id",
      "last_sequence",
      "last_event_id",
      "ledger_version",
      "issued_at"
    ],
    "title": "Kolibri Product Delivery Cursor v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/developer-dispatch-v1.1.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/developer-dispatch-v1.1.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "epoch": {
        "maximum": 9007199254740991,
        "minimum": 1,
        "type": "integer"
      },
      "execution_option": {
        "maxLength": 32,
        "minLength": 1,
        "pattern": "^[a-z0-9][a-z0-9_-]{0,31}$",
        "type": "string"
      },
      "model_selection": {
        "maxLength": 120,
        "minLength": 1,
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$",
        "type": "string"
      },
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "runtime_profile": {
        "maxLength": 96,
        "minLength": 2,
        "pattern": "^[a-z0-9][a-z0-9._-]{1,95}$",
        "type": "string"
      },
      "source_command_ref": {
        "pattern": "^sourcecmd_[0-9a-f]{40}$",
        "type": "string"
      },
      "trusted_profile_id": {
        "pattern": "^tap_[0-9a-f]{32}$",
        "type": "string"
      },
      "trusted_workspace_binding_id": {
        "pattern": "^wsb_[0-9a-f]{32}$",
        "type": "string"
      }
    },
    "description": "Logical Home projection of a v1.3 command with immutable trusted-agent profile and workspace epochs.",
    "properties": {
      "access_mode": {
        "const": "full"
      },
      "approval_policy": {
        "const": "never"
      },
      "input_message_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "model": {
        "oneOf": [
          {
            "$ref": "#/definitions/model_selection"
          },
          {
            "type": "null"
          }
        ]
      },
      "project_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "reasoning_effort": {
        "oneOf": [
          {
            "$ref": "#/definitions/execution_option"
          },
          {
            "type": "null"
          }
        ]
      },
      "reviewer": {
        "type": "null"
      },
      "run_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "runtime_capability": {
        "pattern": "^developer\\.runtime\\.execute\\.[0-9a-f]{32}$",
        "type": "string"
      },
      "runtime_profile": {
        "$ref": "#/definitions/runtime_profile"
      },
      "sandbox": {
        "const": "danger-full-access"
      },
      "schema_id": {
        "const": "kolibri.product.developer_dispatch.v1_1"
      },
      "schema_version": {
        "const": "1.1"
      },
      "service_tier": {
        "oneOf": [
          {
            "$ref": "#/definitions/execution_option"
          },
          {
            "type": "null"
          }
        ]
      },
      "source_command_ref": {
        "$ref": "#/definitions/source_command_ref"
      },
      "thread_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "trusted_agent_profile_epoch": {
        "$ref": "#/definitions/epoch"
      },
      "trusted_agent_profile_id": {
        "$ref": "#/definitions/trusted_profile_id"
      },
      "trusted_agent_workspace_binding_epoch": {
        "$ref": "#/definitions/epoch"
      },
      "trusted_agent_workspace_binding_id": {
        "$ref": "#/definitions/trusted_workspace_binding_id"
      },
      "workspace_ref": {
        "maxLength": 160,
        "minLength": 1,
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$",
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "source_command_ref",
      "run_id",
      "project_id",
      "thread_id",
      "input_message_id",
      "runtime_profile",
      "runtime_capability",
      "model",
      "reasoning_effort",
      "service_tier",
      "workspace_ref",
      "access_mode",
      "sandbox",
      "approval_policy",
      "reviewer",
      "trusted_agent_profile_id",
      "trusted_agent_profile_epoch",
      "trusted_agent_workspace_binding_id",
      "trusted_agent_workspace_binding_epoch"
    ],
    "title": "Kolibri trusted developer dispatch v1.1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/developer-dispatch.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/developer-dispatch.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "execution_option": {
        "maxLength": 32,
        "minLength": 1,
        "pattern": "^[a-z0-9][a-z0-9_-]{0,31}$",
        "type": "string"
      },
      "model_selection": {
        "maxLength": 120,
        "minLength": 1,
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$",
        "type": "string"
      },
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "runtime_profile": {
        "maxLength": 96,
        "minLength": 2,
        "pattern": "^[a-z0-9][a-z0-9._-]{1,95}$",
        "type": "string"
      },
      "source_command_ref": {
        "pattern": "^sourcecmd_[0-9a-f]{40}$",
        "type": "string"
      }
    },
    "description": "The server-frozen provider-neutral execution configuration projected by Logical Home for one developer task.",
    "properties": {
      "access_mode": {
        "enum": [
          "auto",
          "full"
        ],
        "type": "string"
      },
      "approval_policy": {
        "enum": [
          "on-request",
          "never"
        ],
        "type": "string"
      },
      "input_message_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "model": {
        "oneOf": [
          {
            "$ref": "#/definitions/model_selection"
          },
          {
            "type": "null"
          }
        ]
      },
      "project_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "reasoning_effort": {
        "oneOf": [
          {
            "$ref": "#/definitions/execution_option"
          },
          {
            "type": "null"
          }
        ]
      },
      "reviewer": {
        "oneOf": [
          {
            "maxLength": 120,
            "minLength": 1,
            "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "run_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "runtime_capability": {
        "pattern": "^developer\\.runtime\\.execute\\.[0-9a-f]{32}$",
        "type": "string"
      },
      "runtime_profile": {
        "$ref": "#/definitions/runtime_profile"
      },
      "sandbox": {
        "enum": [
          "workspace-write",
          "danger-full-access"
        ],
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.product.developer_dispatch"
      },
      "schema_version": {
        "const": "1.0"
      },
      "service_tier": {
        "oneOf": [
          {
            "$ref": "#/definitions/execution_option"
          },
          {
            "type": "null"
          }
        ]
      },
      "source_command_ref": {
        "$ref": "#/definitions/source_command_ref"
      },
      "thread_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "workspace_ref": {
        "maxLength": 160,
        "minLength": 1,
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$",
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "source_command_ref",
      "run_id",
      "project_id",
      "thread_id",
      "input_message_id",
      "runtime_profile",
      "runtime_capability",
      "model",
      "reasoning_effort",
      "service_tier",
      "workspace_ref",
      "access_mode",
      "sandbox",
      "approval_policy",
      "reviewer"
    ],
    "title": "Kolibri Product developer dispatch v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/developer-lease-source-v1.1.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/developer-lease-source-v1.1.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "access_policy": {
        "additionalProperties": false,
        "properties": {
          "compute_units_limit": {
            "maximum": 9007199254740991,
            "minimum": 0,
            "type": "integer"
          },
          "policy_id": {
            "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
            "type": "string"
          },
          "tool_calls_limit": {
            "maximum": 9007199254740991,
            "minimum": 0,
            "type": "integer"
          },
          "tool_ids": {
            "items": {
              "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
              "type": "string"
            },
            "maxItems": 64,
            "type": "array",
            "uniqueItems": true
          }
        },
        "required": [
          "policy_id",
          "tool_ids",
          "compute_units_limit",
          "tool_calls_limit"
        ],
        "type": "object"
      },
      "epoch": {
        "maximum": 9007199254740991,
        "minimum": 1,
        "type": "integer"
      },
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "runtime_profile": {
        "maxLength": 96,
        "minLength": 2,
        "pattern": "^[a-z0-9][a-z0-9._-]{1,95}$",
        "type": "string"
      },
      "sha256": {
        "pattern": "^sha256:[0-9a-f]{64}$",
        "type": "string"
      },
      "source_command_ref": {
        "pattern": "^sourcecmd_[0-9a-f]{40}$",
        "type": "string"
      },
      "trusted_profile_id": {
        "pattern": "^tap_[0-9a-f]{32}$",
        "type": "string"
      },
      "trusted_workspace_binding_id": {
        "pattern": "^wsb_[0-9a-f]{32}$",
        "type": "string"
      }
    },
    "description": "The exact v1.3 trusted-agent authority tuple, command hashes, assignment and Home lease fence forwarded to Provider Execution Authority.",
    "properties": {
      "access_policy": {
        "$ref": "#/definitions/access_policy"
      },
      "assignment_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "attempt_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "canonical_request_hash": {
        "$ref": "#/definitions/sha256"
      },
      "effect_id": {
        "pattern": "^effect_[0-9a-f]{40}$",
        "type": "string"
      },
      "fencing_token": {
        "maximum": 9007199254740991,
        "minimum": 1,
        "type": "integer"
      },
      "lease_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "runtime_profile": {
        "$ref": "#/definitions/runtime_profile"
      },
      "schema_id": {
        "const": "kolibri.product.developer_lease_source.v1_1"
      },
      "schema_version": {
        "const": "1.1"
      },
      "source_command_hash": {
        "$ref": "#/definitions/sha256"
      },
      "source_command_ref": {
        "$ref": "#/definitions/source_command_ref"
      },
      "task_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "task_version": {
        "maximum": 9007199254740991,
        "minimum": 1,
        "type": "integer"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "trusted_agent_profile_epoch": {
        "$ref": "#/definitions/epoch"
      },
      "trusted_agent_profile_id": {
        "$ref": "#/definitions/trusted_profile_id"
      },
      "trusted_agent_workspace_binding_epoch": {
        "$ref": "#/definitions/epoch"
      },
      "trusted_agent_workspace_binding_id": {
        "$ref": "#/definitions/trusted_workspace_binding_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "source_command_ref",
      "canonical_request_hash",
      "source_command_hash",
      "tenant_id",
      "task_id",
      "task_version",
      "attempt_id",
      "assignment_id",
      "effect_id",
      "lease_id",
      "fencing_token",
      "runtime_profile",
      "access_policy",
      "trusted_agent_profile_id",
      "trusted_agent_profile_epoch",
      "trusted_agent_workspace_binding_id",
      "trusted_agent_workspace_binding_epoch"
    ],
    "title": "Kolibri trusted developer lease source v1.1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/developer-lease-source.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/developer-lease-source.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "access_policy": {
        "additionalProperties": false,
        "properties": {
          "compute_units_limit": {
            "maximum": 9007199254740991,
            "minimum": 0,
            "type": "integer"
          },
          "policy_id": {
            "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
            "type": "string"
          },
          "tool_calls_limit": {
            "maximum": 9007199254740991,
            "minimum": 0,
            "type": "integer"
          },
          "tool_ids": {
            "items": {
              "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
              "type": "string"
            },
            "maxItems": 64,
            "type": "array",
            "uniqueItems": true
          }
        },
        "required": [
          "policy_id",
          "tool_ids",
          "compute_units_limit",
          "tool_calls_limit"
        ],
        "type": "object"
      },
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "runtime_profile": {
        "maxLength": 96,
        "minLength": 2,
        "pattern": "^[a-z0-9][a-z0-9._-]{1,95}$",
        "type": "string"
      },
      "sha256": {
        "pattern": "^sha256:[0-9a-f]{64}$",
        "type": "string"
      },
      "source_command_ref": {
        "pattern": "^sourcecmd_[0-9a-f]{40}$",
        "type": "string"
      }
    },
    "description": "The exact command hashes, assignment and Home lease fence forwarded to Provider Execution Authority. The source command is transported separately.",
    "properties": {
      "access_policy": {
        "$ref": "#/definitions/access_policy"
      },
      "assignment_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "attempt_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "canonical_request_hash": {
        "$ref": "#/definitions/sha256"
      },
      "effect_id": {
        "pattern": "^effect_[0-9a-f]{40}$",
        "type": "string"
      },
      "fencing_token": {
        "maximum": 9007199254740991,
        "minimum": 1,
        "type": "integer"
      },
      "lease_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "runtime_profile": {
        "$ref": "#/definitions/runtime_profile"
      },
      "schema_id": {
        "const": "kolibri.product.developer_lease_source"
      },
      "schema_version": {
        "const": "1.0"
      },
      "source_command_hash": {
        "$ref": "#/definitions/sha256"
      },
      "source_command_ref": {
        "$ref": "#/definitions/source_command_ref"
      },
      "task_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "task_version": {
        "maximum": 9007199254740991,
        "minimum": 1,
        "type": "integer"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "source_command_ref",
      "canonical_request_hash",
      "source_command_hash",
      "tenant_id",
      "task_id",
      "task_version",
      "attempt_id",
      "assignment_id",
      "effect_id",
      "lease_id",
      "fencing_token",
      "runtime_profile",
      "access_policy"
    ],
    "title": "Kolibri Product developer lease source v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/developer-source-command.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/developer-source-command.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "access_policy": {
        "additionalProperties": false,
        "properties": {
          "compute_units_limit": {
            "maximum": 9007199254740991,
            "minimum": 0,
            "type": "integer"
          },
          "policy_id": {
            "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
            "type": "string"
          },
          "tool_calls_limit": {
            "maximum": 9007199254740991,
            "minimum": 0,
            "type": "integer"
          },
          "tool_ids": {
            "items": {
              "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
              "type": "string"
            },
            "maxItems": 64,
            "type": "array",
            "uniqueItems": true
          }
        },
        "required": [
          "policy_id",
          "tool_ids",
          "compute_units_limit",
          "tool_calls_limit"
        ],
        "type": "object"
      },
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "runtime_profile": {
        "maxLength": 96,
        "minLength": 2,
        "pattern": "^[a-z0-9][a-z0-9._-]{1,95}$",
        "type": "string"
      },
      "sha256": {
        "pattern": "^sha256:[0-9a-f]{64}$",
        "type": "string"
      },
      "source_command_ref": {
        "pattern": "^sourcecmd_[0-9a-f]{40}$",
        "type": "string"
      }
    },
    "description": "The Home-owned durable provenance record for one admitted Product developer command.",
    "properties": {
      "access_policy": {
        "$ref": "#/definitions/access_policy"
      },
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "command_hash": {
        "$ref": "#/definitions/sha256"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "graph_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "request_hash": {
        "$ref": "#/definitions/sha256"
      },
      "requested_runtime_profile": {
        "$ref": "#/definitions/runtime_profile"
      },
      "run_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "runtime_capability": {
        "pattern": "^developer\\.runtime\\.execute\\.[0-9a-f]{32}$",
        "type": "string"
      },
      "runtime_profile": {
        "$ref": "#/definitions/runtime_profile"
      },
      "schema_id": {
        "const": "kolibri.product.developer_source_command"
      },
      "schema_version": {
        "const": "1.0"
      },
      "source_command": {
        "$ref": "https://schemas.kolibriai.ru/v1/common/command-envelope.schema.json"
      },
      "source_command_ref": {
        "$ref": "#/definitions/source_command_ref"
      },
      "state": {
        "enum": [
          "reserved",
          "ready"
        ],
        "type": "string"
      },
      "task_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "source_command_ref",
      "tenant_id",
      "goal_id",
      "case_id",
      "run_id",
      "task_id",
      "graph_id",
      "request_hash",
      "command_hash",
      "requested_runtime_profile",
      "runtime_profile",
      "runtime_capability",
      "access_policy",
      "state",
      "source_command"
    ],
    "title": "Kolibri Product durable developer source command v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/interrupt.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/interrupt.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "answer_message_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "expires_at": {
        "format": "date-time",
        "type": "string"
      },
      "interrupt_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "interrupt_version": {
        "minimum": 1,
        "type": "integer"
      },
      "kind": {
        "enum": [
          "clarification",
          "approval",
          "missing_source",
          "conflict"
        ],
        "type": "string"
      },
      "project_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "prompt": {
        "maxLength": 4000,
        "minLength": 1,
        "type": "string"
      },
      "required_authority": {
        "enum": [
          "user",
          "project_manager",
          "estimator",
          "finance",
          "owner"
        ],
        "type": "string"
      },
      "response_schema_id": {
        "pattern": "^kolibri\\.product\\.interrupt\\.response\\.[a-z][a-z0-9_.:-]{2,127}$",
        "type": "string"
      },
      "response_schema_version": {
        "pattern": "^[1-9][0-9]*\\.[0-9]+$",
        "type": "string"
      },
      "run_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "schema_id": {
        "const": "kolibri.product.interrupt"
      },
      "schema_version": {
        "const": "1.0"
      },
      "state": {
        "enum": [
          "pending",
          "answered",
          "expired",
          "cancelled"
        ],
        "type": "string"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "thread_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "updated_at": {
        "format": "date-time",
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "interrupt_id",
      "interrupt_version",
      "state",
      "kind",
      "prompt",
      "response_schema_id",
      "response_schema_version",
      "required_authority",
      "answer_message_id",
      "created_at",
      "updated_at",
      "expires_at"
    ],
    "title": "Kolibri Product Interrupt v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/message-part.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/message-part.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "definitions": {
      "artifact_ref": {
        "additionalProperties": false,
        "properties": {
          "artifact_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "artifact_kind": {
            "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
            "type": "string"
          },
          "artifact_version": {
            "minimum": 1,
            "type": "integer"
          },
          "content_hash": {
            "$ref": "#/definitions/hash"
          },
          "part_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "tenant_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "type": {
            "const": "artifact_ref"
          }
        },
        "required": [
          "part_id",
          "type",
          "tenant_id",
          "artifact_id",
          "artifact_version",
          "content_hash",
          "artifact_kind"
        ],
        "type": "object"
      },
      "attachment_ref": {
        "additionalProperties": false,
        "properties": {
          "artifact_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "artifact_version": {
            "minimum": 1,
            "type": "integer"
          },
          "content_hash": {
            "$ref": "#/definitions/hash"
          },
          "filename": {
            "maxLength": 512,
            "minLength": 1,
            "type": "string"
          },
          "mime_type": {
            "maxLength": 160,
            "minLength": 3,
            "type": "string"
          },
          "part_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "size_bytes": {
            "minimum": 0,
            "type": "integer"
          },
          "tenant_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "type": {
            "const": "attachment_ref"
          }
        },
        "required": [
          "part_id",
          "type",
          "tenant_id",
          "artifact_id",
          "artifact_version",
          "content_hash",
          "filename",
          "mime_type",
          "size_bytes"
        ],
        "type": "object"
      },
      "base": {
        "properties": {
          "part_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "type": {
            "type": "string"
          }
        },
        "required": [
          "part_id",
          "type"
        ],
        "type": "object"
      },
      "citation_ref": {
        "additionalProperties": false,
        "properties": {
          "content_hash": {
            "$ref": "#/definitions/hash"
          },
          "label": {
            "maxLength": 500,
            "minLength": 1,
            "type": "string"
          },
          "locator": {
            "maxLength": 1000,
            "minLength": 1,
            "type": "string"
          },
          "part_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "source_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "source_version": {
            "minimum": 1,
            "type": "integer"
          },
          "type": {
            "const": "citation_ref"
          }
        },
        "required": [
          "part_id",
          "type",
          "source_id",
          "source_version",
          "content_hash",
          "label",
          "locator"
        ],
        "type": "object"
      },
      "hash": {
        "pattern": "^sha256:[0-9a-f]{64}$",
        "type": "string"
      },
      "interrupt_ref": {
        "additionalProperties": false,
        "properties": {
          "interrupt_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "interrupt_version": {
            "minimum": 1,
            "type": "integer"
          },
          "part_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "type": {
            "const": "interrupt_ref"
          }
        },
        "required": [
          "part_id",
          "type",
          "interrupt_id",
          "interrupt_version"
        ],
        "type": "object"
      },
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "text": {
        "additionalProperties": false,
        "properties": {
          "format": {
            "enum": [
              "plain",
              "markdown"
            ],
            "type": "string"
          },
          "part_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "text": {
            "maxLength": 200000,
            "minLength": 1,
            "type": "string"
          },
          "type": {
            "const": "text"
          }
        },
        "required": [
          "part_id",
          "type",
          "format",
          "text"
        ],
        "type": "object"
      },
      "tool_call_ref": {
        "additionalProperties": false,
        "properties": {
          "input_hash": {
            "$ref": "#/definitions/hash"
          },
          "input_schema_id": {
            "pattern": "^kolibri\\.[a-z][a-z0-9_.:-]{2,127}$",
            "type": "string"
          },
          "input_schema_version": {
            "pattern": "^[1-9][0-9]*\\.[0-9]+$",
            "type": "string"
          },
          "part_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "tool_call_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "tool_name": {
            "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
            "type": "string"
          },
          "type": {
            "const": "tool_call_ref"
          }
        },
        "required": [
          "part_id",
          "type",
          "tool_call_id",
          "tool_name",
          "input_schema_id",
          "input_schema_version",
          "input_hash"
        ],
        "type": "object"
      },
      "tool_result_ref": {
        "additionalProperties": false,
        "properties": {
          "part_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "result_hash": {
            "$ref": "#/definitions/hash"
          },
          "result_schema_id": {
            "pattern": "^kolibri\\.[a-z][a-z0-9_.:-]{2,127}$",
            "type": "string"
          },
          "result_schema_version": {
            "pattern": "^[1-9][0-9]*\\.[0-9]+$",
            "type": "string"
          },
          "tool_call_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "type": {
            "const": "tool_result_ref"
          }
        },
        "required": [
          "part_id",
          "type",
          "tool_call_id",
          "result_schema_id",
          "result_schema_version",
          "result_hash"
        ],
        "type": "object"
      }
    },
    "oneOf": [
      {
        "$ref": "#/definitions/text"
      },
      {
        "$ref": "#/definitions/attachment_ref"
      },
      {
        "$ref": "#/definitions/tool_call_ref"
      },
      {
        "$ref": "#/definitions/tool_result_ref"
      },
      {
        "$ref": "#/definitions/artifact_ref"
      },
      {
        "$ref": "#/definitions/citation_ref"
      },
      {
        "$ref": "#/definitions/interrupt_ref"
      }
    ],
    "title": "Kolibri Product Message Part v1"
  },
  "https://schemas.kolibriai.ru/v1/product/message.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/message.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "author_actor_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "branch_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "committed_at": {
        "format": "date-time",
        "type": "string"
      },
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "message_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "parent_message_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "parts": {
        "items": {
          "$ref": "https://schemas.kolibriai.ru/v1/product/message-part.schema.json"
        },
        "maxItems": 256,
        "minItems": 1,
        "type": "array"
      },
      "project_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "role": {
        "enum": [
          "user",
          "assistant",
          "system"
        ],
        "type": "string"
      },
      "run_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "schema_id": {
        "const": "kolibri.product.message"
      },
      "schema_version": {
        "const": "1.0"
      },
      "sequence": {
        "minimum": 1,
        "type": "integer"
      },
      "status": {
        "enum": [
          "committed",
          "superseded",
          "redacted"
        ],
        "type": "string"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "thread_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "version": {
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "message_id",
      "sequence",
      "parent_message_id",
      "branch_id",
      "run_id",
      "role",
      "author_actor_id",
      "status",
      "parts",
      "version",
      "created_at",
      "committed_at"
    ],
    "title": "Kolibri Product Message v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/product-goal-initialization-status.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/product-goal-initialization-status.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "else": {
          "properties": {
            "case_version": {
              "type": "null"
            },
            "error": {
              "$ref": "https://schemas.kolibriai.ru/v1/common/error-envelope.schema.json"
            },
            "goal_version": {
              "type": "null"
            }
          }
        },
        "if": {
          "properties": {
            "status": {
              "const": "initialized"
            }
          },
          "required": [
            "status"
          ]
        },
        "then": {
          "properties": {
            "case_version": {
              "minimum": 1,
              "type": "integer"
            },
            "error": {
              "type": "null"
            },
            "goal_version": {
              "minimum": 1,
              "type": "integer"
            }
          }
        }
      }
    ],
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "description": "Terminal Logical Home result for a Product-authenticated Goal initialization request.",
    "properties": {
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "case_version": {
        "oneOf": [
          {
            "minimum": 1,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ]
      },
      "error": {
        "oneOf": [
          {
            "$ref": "https://schemas.kolibriai.ru/v1/common/error-envelope.schema.json"
          },
          {
            "type": "null"
          }
        ]
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "goal_version": {
        "oneOf": [
          {
            "minimum": 1,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ]
      },
      "run_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "schema_id": {
        "const": "kolibri.product.goal.initialization_status"
      },
      "schema_version": {
        "const": "1.0"
      },
      "status": {
        "enum": [
          "initialized",
          "failed"
        ],
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "run_id",
      "goal_id",
      "case_id",
      "status",
      "goal_version",
      "case_version",
      "error"
    ],
    "title": "Kolibri Product goal initialization status v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/product-goal-initialize-command.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/product-goal-initialize-command.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "sha256": {
        "pattern": "^sha256:[0-9a-f]{64}$",
        "type": "string"
      }
    },
    "description": "Product/Data Authority request for Logical Home to initialize one canonical Goal and its deterministic ProjectCase.",
    "properties": {
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "input_message_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "project_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "prompt": {
        "maxLength": 20000,
        "minLength": 1,
        "type": "string"
      },
      "prompt_hash": {
        "$ref": "#/definitions/sha256"
      },
      "run_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "schema_id": {
        "const": "kolibri.product.goal.initialize.command"
      },
      "schema_version": {
        "const": "1.0"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "thread_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "input_message_id",
      "goal_id",
      "prompt",
      "prompt_hash"
    ],
    "title": "Kolibri Product goal initialization command payload v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/project-create-request.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/project-create-request.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "name": {
        "maxLength": 160,
        "minLength": 1,
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.product.project_create_request"
      },
      "schema_version": {
        "const": "1.0"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "name"
    ],
    "title": "Kolibri Product project create request v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/project.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/project.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "created_by": {
        "$ref": "#/definitions/opaque_id"
      },
      "default_thread_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "goal_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "name": {
        "maxLength": 240,
        "minLength": 1,
        "type": "string"
      },
      "project_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "schema_id": {
        "const": "kolibri.product.project"
      },
      "schema_version": {
        "const": "1.0"
      },
      "status": {
        "enum": [
          "active",
          "archived",
          "deleted"
        ],
        "type": "string"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "updated_at": {
        "format": "date-time",
        "type": "string"
      },
      "version": {
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "case_id",
      "goal_id",
      "name",
      "status",
      "default_thread_id",
      "version",
      "created_by",
      "created_at",
      "updated_at"
    ],
    "title": "Kolibri Product Project v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/provider-enrollment-intent-command.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/provider-enrollment-intent-command.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "description": "A secretless Product/Data Authority request for Provider Execution Authority to begin or inspect one owner-approved provider enrollment. Provider credentials and authorization URLs are forbidden.",
    "properties": {
      "intent_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "owner_authorization_decision_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "provider_id": {
        "enum": [
          "mimo-code",
          "codex-cli"
        ],
        "type": "string"
      },
      "purpose": {
        "const": "owner_provider_enrollment"
      },
      "requested_at": {
        "format": "date-time",
        "type": "string"
      },
      "requested_by_user_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "schema_id": {
        "const": "kolibri.product.provider.enrollment_intent.command"
      },
      "schema_version": {
        "const": "1.0"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "intent_id",
      "provider_id",
      "requested_by_user_id",
      "owner_authorization_decision_id",
      "purpose",
      "requested_at"
    ],
    "title": "Kolibri Product provider enrollment intent command payload v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/provider-enrollment-status.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/provider-enrollment-status.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "description": "A sanitized provider-enrollment status. It never contains credentials, provider responses, filesystem paths, or authorization URLs.",
    "properties": {
      "auth_flow_supported": {
        "type": "boolean"
      },
      "error": {
        "oneOf": [
          {
            "$ref": "https://schemas.kolibriai.ru/v1/common/error-envelope.schema.json"
          },
          {
            "type": "null"
          }
        ]
      },
      "evidence_hash": {
        "oneOf": [
          {
            "pattern": "^sha256:[0-9a-f]{64}$",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "intent_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "last_verified_at": {
        "oneOf": [
          {
            "format": "date-time",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "observed_at": {
        "format": "date-time",
        "type": "string"
      },
      "provider_id": {
        "enum": [
          "mimo-code",
          "codex-cli"
        ],
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.product.provider.enrollment_status"
      },
      "schema_version": {
        "const": "1.0"
      },
      "status": {
        "enum": [
          "connected",
          "failed"
        ],
        "type": "string"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "intent_id",
      "provider_id",
      "status",
      "observed_at",
      "auth_flow_supported",
      "last_verified_at",
      "evidence_hash",
      "error"
    ],
    "title": "Kolibri Provider Execution Authority enrollment status v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/run-event.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/run-event.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "event_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "event_type": {
        "enum": [
          "run_started",
          "safe_progress",
          "message_part_delta",
          "message_part_committed",
          "tool_started",
          "tool_finished",
          "artifact_referenced",
          "interrupt_created",
          "invalidation",
          "heartbeat",
          "run_finished",
          "run_error"
        ],
        "type": "string"
      },
      "occurred_at": {
        "format": "date-time",
        "type": "string"
      },
      "payload": {
        "maxProperties": 128,
        "type": "object"
      },
      "payload_schema_id": {
        "pattern": "^kolibri\\.product\\.event\\.[a-z][a-z0-9_.:-]{2,127}$",
        "type": "string"
      },
      "payload_schema_version": {
        "pattern": "^[1-9][0-9]*\\.[0-9]+$",
        "type": "string"
      },
      "project_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "recorded_at": {
        "format": "date-time",
        "type": "string"
      },
      "run_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "schema_id": {
        "const": "kolibri.product.run.event"
      },
      "schema_version": {
        "const": "1.0"
      },
      "sequence": {
        "minimum": 1,
        "type": "integer"
      },
      "source_event_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "source_task_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "thread_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "trace": {
        "$ref": "https://schemas.kolibriai.ru/v1/common/trace.schema.json"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "event_id",
      "sequence",
      "event_type",
      "payload_schema_id",
      "payload_schema_version",
      "payload",
      "trace",
      "source_task_id",
      "source_event_id",
      "occurred_at",
      "recorded_at"
    ],
    "title": "Kolibri Product Run Event v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/run-execute-command-v1.1.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/run-execute-command-v1.1.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "oneOf": [
      {
        "properties": {
          "preferred_model": {
            "type": "string"
          },
          "preferred_reasoning_effort": {
            "type": "string"
          }
        },
        "required": [
          "preferred_agent_profile",
          "preferred_model",
          "preferred_reasoning_effort"
        ]
      },
      {
        "properties": {
          "preferred_model": {
            "type": "null"
          },
          "preferred_reasoning_effort": {
            "type": "null"
          }
        },
        "required": [
          "preferred_agent_profile",
          "preferred_model",
          "preferred_reasoning_effort"
        ]
      }
    ],
    "properties": {
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "input_message_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "preferred_agent_profile": {
        "maxLength": 96,
        "minLength": 2,
        "pattern": "^[a-z][a-z0-9._-]{1,95}$",
        "type": "string"
      },
      "preferred_model": {
        "maxLength": 120,
        "minLength": 1,
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$",
        "type": [
          "string",
          "null"
        ]
      },
      "preferred_reasoning_effort": {
        "maxLength": 32,
        "minLength": 1,
        "pattern": "^[a-z0-9][a-z0-9_-]{0,31}$",
        "type": [
          "string",
          "null"
        ]
      },
      "project_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "prompt": {
        "maxLength": 200000,
        "minLength": 1,
        "type": "string"
      },
      "prompt_hash": {
        "pattern": "^sha256:[0-9a-f]{64}$",
        "type": "string"
      },
      "run_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "schema_id": {
        "const": "kolibri.product.run.execute.v1_1.command"
      },
      "schema_version": {
        "const": "1.1"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "thread_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "input_message_id",
      "case_id",
      "goal_id",
      "prompt",
      "prompt_hash",
      "preferred_agent_profile",
      "preferred_model",
      "preferred_reasoning_effort"
    ],
    "title": "Kolibri Product run execute command payload v1.1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/run-execute-command-v1.2.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/run-execute-command-v1.2.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "execution_option": {
        "maxLength": 32,
        "minLength": 1,
        "pattern": "^[a-z0-9][a-z0-9_-]{0,31}$",
        "type": "string"
      },
      "model_selection": {
        "maxLength": 120,
        "minLength": 1,
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$",
        "type": "string"
      },
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "runtime_profile": {
        "maxLength": 96,
        "minLength": 2,
        "pattern": "^[a-z0-9][a-z0-9._-]{1,95}$",
        "type": "string"
      }
    },
    "description": "Server-frozen universal AgentRuntime request. The runtime profile is opaque to Product/Data and no provider-specific routing semantics are encoded here.",
    "properties": {
      "access_mode": {
        "enum": [
          "auto",
          "full"
        ],
        "type": "string"
      },
      "approval_policy": {
        "enum": [
          "on-request",
          "never"
        ],
        "type": "string"
      },
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "execution_mode": {
        "const": "developer"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "input_message_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "model": {
        "oneOf": [
          {
            "$ref": "#/definitions/model_selection"
          },
          {
            "type": "null"
          }
        ]
      },
      "project_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "prompt": {
        "maxLength": 200000,
        "minLength": 1,
        "type": "string"
      },
      "prompt_hash": {
        "pattern": "^sha256:[0-9a-f]{64}$",
        "type": "string"
      },
      "reasoning_effort": {
        "oneOf": [
          {
            "$ref": "#/definitions/execution_option"
          },
          {
            "type": "null"
          }
        ]
      },
      "requester_role": {
        "const": "owner"
      },
      "reviewer": {
        "oneOf": [
          {
            "maxLength": 120,
            "minLength": 1,
            "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "run_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "runtime_profile": {
        "$ref": "#/definitions/runtime_profile"
      },
      "sandbox": {
        "enum": [
          "workspace-write",
          "danger-full-access"
        ],
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.product.run.execute.v1_2.command"
      },
      "schema_version": {
        "const": "1.2"
      },
      "service_tier": {
        "oneOf": [
          {
            "$ref": "#/definitions/execution_option"
          },
          {
            "type": "null"
          }
        ]
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "thread_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "workspace_ref": {
        "maxLength": 160,
        "minLength": 1,
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$",
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "input_message_id",
      "case_id",
      "goal_id",
      "prompt",
      "prompt_hash",
      "execution_mode",
      "runtime_profile",
      "model",
      "reasoning_effort",
      "service_tier",
      "workspace_ref",
      "access_mode",
      "sandbox",
      "approval_policy",
      "reviewer",
      "requester_role"
    ],
    "title": "Kolibri Product developer run execute command payload v1.2",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/run-execute-command-v1.3.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/run-execute-command-v1.3.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "epoch": {
        "maximum": 9007199254740991,
        "minimum": 1,
        "type": "integer"
      },
      "execution_option": {
        "maxLength": 32,
        "minLength": 1,
        "pattern": "^[a-z0-9][a-z0-9_-]{0,31}$",
        "type": "string"
      },
      "model_selection": {
        "maxLength": 120,
        "minLength": 1,
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$",
        "type": "string"
      },
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "runtime_profile": {
        "maxLength": 96,
        "minLength": 2,
        "pattern": "^[a-z0-9][a-z0-9._-]{1,95}$",
        "type": "string"
      },
      "trusted_profile_id": {
        "pattern": "^tap_[0-9a-f]{32}$",
        "type": "string"
      },
      "trusted_workspace_binding_id": {
        "pattern": "^wsb_[0-9a-f]{32}$",
        "type": "string"
      }
    },
    "description": "Server-frozen developer AgentRuntime request bound to the exact trusted-agent profile and workspace authority epochs.",
    "properties": {
      "access_mode": {
        "const": "full"
      },
      "approval_policy": {
        "const": "never"
      },
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "execution_mode": {
        "const": "developer"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "input_message_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "model": {
        "oneOf": [
          {
            "$ref": "#/definitions/model_selection"
          },
          {
            "type": "null"
          }
        ]
      },
      "project_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "prompt": {
        "maxLength": 200000,
        "minLength": 1,
        "type": "string"
      },
      "prompt_hash": {
        "pattern": "^sha256:[0-9a-f]{64}$",
        "type": "string"
      },
      "reasoning_effort": {
        "oneOf": [
          {
            "$ref": "#/definitions/execution_option"
          },
          {
            "type": "null"
          }
        ]
      },
      "requester_role": {
        "const": "owner"
      },
      "reviewer": {
        "type": "null"
      },
      "run_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "runtime_profile": {
        "maxLength": 96,
        "minLength": 2,
        "pattern": "^(?!auto$)[a-z0-9][a-z0-9._-]{1,95}$",
        "type": "string"
      },
      "sandbox": {
        "const": "danger-full-access"
      },
      "schema_id": {
        "const": "kolibri.product.run.execute.v1_3.command"
      },
      "schema_version": {
        "const": "1.3"
      },
      "service_tier": {
        "oneOf": [
          {
            "$ref": "#/definitions/execution_option"
          },
          {
            "type": "null"
          }
        ]
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "thread_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "trusted_agent_profile_epoch": {
        "$ref": "#/definitions/epoch"
      },
      "trusted_agent_profile_id": {
        "$ref": "#/definitions/trusted_profile_id"
      },
      "trusted_agent_workspace_binding_epoch": {
        "$ref": "#/definitions/epoch"
      },
      "trusted_agent_workspace_binding_id": {
        "$ref": "#/definitions/trusted_workspace_binding_id"
      },
      "workspace_ref": {
        "maxLength": 160,
        "minLength": 1,
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$",
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "input_message_id",
      "case_id",
      "goal_id",
      "prompt",
      "prompt_hash",
      "execution_mode",
      "runtime_profile",
      "model",
      "reasoning_effort",
      "service_tier",
      "workspace_ref",
      "access_mode",
      "sandbox",
      "approval_policy",
      "reviewer",
      "requester_role",
      "trusted_agent_profile_id",
      "trusted_agent_profile_epoch",
      "trusted_agent_workspace_binding_id",
      "trusted_agent_workspace_binding_epoch"
    ],
    "title": "Kolibri trusted developer run execute command payload v1.3",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/run-execute-command.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/run-execute-command.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "input_message_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "preferred_agent_profile": {
        "enum": [
          "auto",
          "mimo-code",
          "codex-cli"
        ],
        "type": "string"
      },
      "project_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "prompt": {
        "maxLength": 200000,
        "minLength": 1,
        "type": "string"
      },
      "prompt_hash": {
        "pattern": "^sha256:[0-9a-f]{64}$",
        "type": "string"
      },
      "run_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "schema_id": {
        "const": "kolibri.product.run.execute.command"
      },
      "schema_version": {
        "const": "1.0"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "thread_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "input_message_id",
      "case_id",
      "goal_id",
      "prompt",
      "prompt_hash",
      "preferred_agent_profile"
    ],
    "title": "Kolibri Product run execute command payload v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/run-execution-status-v1.1.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/run-execution-status-v1.1.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "evidence_ref": {
        "additionalProperties": false,
        "properties": {
          "content_hash": {
            "$ref": "#/definitions/sha256"
          },
          "evidence_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "evidence_version": {
            "minimum": 1,
            "type": "integer"
          }
        },
        "required": [
          "evidence_id",
          "evidence_version",
          "content_hash"
        ],
        "type": "object"
      },
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "sha256": {
        "pattern": "^sha256:[0-9a-f]{64}$",
        "type": "string"
      }
    },
    "description": "Internal Logical Home to Product/Data execution status for a resolved opaque runtime profile. It exposes no provider routing or credentials.",
    "properties": {
      "error": {
        "oneOf": [
          {
            "$ref": "https://schemas.kolibriai.ru/v1/common/error-envelope.schema.json"
          },
          {
            "type": "null"
          }
        ]
      },
      "evidence": {
        "oneOf": [
          {
            "$ref": "#/definitions/evidence_ref"
          },
          {
            "type": "null"
          }
        ]
      },
      "execution_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "result_hash": {
        "oneOf": [
          {
            "$ref": "#/definitions/sha256"
          },
          {
            "type": "null"
          }
        ]
      },
      "result_text": {
        "oneOf": [
          {
            "maxLength": 200000,
            "minLength": 1,
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "run_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "runtime_profile": {
        "maxLength": 96,
        "minLength": 2,
        "pattern": "^[a-z0-9][a-z0-9._-]{1,95}$",
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.product.run.execution_status.v1_1"
      },
      "schema_version": {
        "const": "1.1"
      },
      "status": {
        "enum": [
          "accepted",
          "running",
          "succeeded",
          "failed"
        ],
        "type": "string"
      },
      "verification_status": {
        "enum": [
          "not_applicable",
          "unverified",
          "verified"
        ],
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "run_id",
      "status",
      "runtime_profile",
      "execution_id",
      "verification_status",
      "result_text",
      "result_hash",
      "evidence",
      "error"
    ],
    "title": "Kolibri Product universal AgentRuntime execution status v1.1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/run-execution-status.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/run-execution-status.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "evidence_ref": {
        "additionalProperties": false,
        "properties": {
          "content_hash": {
            "$ref": "#/definitions/sha256"
          },
          "evidence_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "evidence_version": {
            "minimum": 1,
            "type": "integer"
          }
        },
        "required": [
          "evidence_id",
          "evidence_version",
          "content_hash"
        ],
        "type": "object"
      },
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "sha256": {
        "pattern": "^sha256:[0-9a-f]{64}$",
        "type": "string"
      }
    },
    "description": "Internal Logical Home to Product/Data execution status. It reports a resolved execution profile without exposing provider routing or credentials.",
    "properties": {
      "error": {
        "oneOf": [
          {
            "$ref": "https://schemas.kolibriai.ru/v1/common/error-envelope.schema.json"
          },
          {
            "type": "null"
          }
        ]
      },
      "evidence": {
        "oneOf": [
          {
            "$ref": "#/definitions/evidence_ref"
          },
          {
            "type": "null"
          }
        ]
      },
      "execution_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "profile": {
        "enum": [
          "mimo-code",
          "codex-cli"
        ],
        "type": "string"
      },
      "result_hash": {
        "oneOf": [
          {
            "$ref": "#/definitions/sha256"
          },
          {
            "type": "null"
          }
        ]
      },
      "result_text": {
        "oneOf": [
          {
            "maxLength": 200000,
            "minLength": 1,
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "run_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "schema_id": {
        "const": "kolibri.product.run.execution_status"
      },
      "schema_version": {
        "const": "1.0"
      },
      "status": {
        "enum": [
          "accepted",
          "running",
          "succeeded",
          "failed"
        ],
        "type": "string"
      },
      "verification_status": {
        "enum": [
          "not_applicable",
          "unverified",
          "verified"
        ],
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "run_id",
      "status",
      "profile",
      "execution_id",
      "verification_status",
      "result_text",
      "result_hash",
      "evidence",
      "error"
    ],
    "title": "Kolibri Product run execution status v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/run.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/run.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "active_interrupt_ids": {
        "items": {
          "$ref": "#/definitions/opaque_id"
        },
        "maxItems": 64,
        "type": "array",
        "uniqueItems": true
      },
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "created_by": {
        "$ref": "#/definitions/opaque_id"
      },
      "finished_at": {
        "oneOf": [
          {
            "format": "date-time",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "goal_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "home_task_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "input_message_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "last_event_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "last_event_sequence": {
        "minimum": 0,
        "type": "integer"
      },
      "lifecycle": {
        "enum": [
          "accepted",
          "running",
          "cancellation_requested",
          "finished"
        ],
        "type": "string"
      },
      "outcome": {
        "oneOf": [
          {
            "enum": [
              "success",
              "interrupt",
              "failure",
              "cancelled"
            ],
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "project_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "resume_of_run_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "retry_of_run_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "run_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "run_sequence": {
        "minimum": 1,
        "type": "integer"
      },
      "schema_id": {
        "const": "kolibri.product.run"
      },
      "schema_version": {
        "const": "1.0"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "thread_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "updated_at": {
        "format": "date-time",
        "type": "string"
      },
      "version": {
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "run_id",
      "run_sequence",
      "input_message_id",
      "retry_of_run_id",
      "resume_of_run_id",
      "case_id",
      "goal_id",
      "home_task_id",
      "lifecycle",
      "outcome",
      "last_event_sequence",
      "last_event_id",
      "active_interrupt_ids",
      "version",
      "created_by",
      "created_at",
      "updated_at",
      "finished_at"
    ],
    "title": "Kolibri Product Run v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/session.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/session.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "capabilities": {
        "items": {
          "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
          "type": "string"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "expires_at": {
        "oneOf": [
          {
            "format": "date-time",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "product_api_version": {
        "const": "v1"
      },
      "schema_id": {
        "const": "kolibri.product.session"
      },
      "schema_version": {
        "const": "1.0"
      },
      "session_kind": {
        "enum": [
          "anonymous",
          "authenticated"
        ],
        "type": "string"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "user_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "user_id",
      "session_kind",
      "expires_at",
      "product_api_version",
      "capabilities"
    ],
    "title": "Kolibri Product session v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/text-run-request.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/text-run-request.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "expected_thread_version": {
        "minimum": 1,
        "type": "integer"
      },
      "parent_message_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "parts": {
        "items": {
          "$ref": "https://schemas.kolibriai.ru/v1/product/message-part.schema.json"
        },
        "maxItems": 16,
        "minItems": 1,
        "type": "array"
      },
      "preferred_agent_profile": {
        "enum": [
          "auto",
          "mimo-code",
          "codex-cli"
        ],
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.product.text_run_request"
      },
      "schema_version": {
        "const": "1.0"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "expected_thread_version",
      "parent_message_id",
      "parts",
      "preferred_agent_profile"
    ],
    "title": "Kolibri Product text run request v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/thread-update-request.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/thread-update-request.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "expected_thread_version": {
        "minimum": 1,
        "type": "integer"
      },
      "schema_id": {
        "const": "kolibri.product.thread_update_request"
      },
      "schema_version": {
        "const": "1.0"
      },
      "title": {
        "maxLength": 160,
        "minLength": 1,
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "expected_thread_version",
      "title"
    ],
    "title": "Kolibri Product thread update request v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/product/thread.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/product/thread.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "branch_count": {
        "minimum": 1,
        "type": "integer"
      },
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "created_by": {
        "$ref": "#/definitions/opaque_id"
      },
      "last_message_sequence": {
        "minimum": 0,
        "type": "integer"
      },
      "last_run_sequence": {
        "minimum": 0,
        "type": "integer"
      },
      "project_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "schema_id": {
        "const": "kolibri.product.thread"
      },
      "schema_version": {
        "const": "1.0"
      },
      "status": {
        "enum": [
          "active",
          "archived",
          "deleted"
        ],
        "type": "string"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "thread_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "title": {
        "maxLength": 240,
        "minLength": 1,
        "type": "string"
      },
      "updated_at": {
        "format": "date-time",
        "type": "string"
      },
      "version": {
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "project_id",
      "thread_id",
      "title",
      "status",
      "branch_count",
      "last_message_sequence",
      "last_run_sequence",
      "version",
      "created_by",
      "created_at",
      "updated_at"
    ],
    "title": "Kolibri Product Thread v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/provider-execution/catalog.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/provider-execution/catalog.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "agent_cards": {
        "items": {
          "$ref": "https://schemas.kolibriai.ru/v1/agents/agent-card.schema.json"
        },
        "maxItems": 64,
        "type": "array",
        "uniqueItems": true
      },
      "schema_id": {
        "const": "kolibri.provider_execution.catalog"
      },
      "schema_version": {
        "const": "1.0"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "agent_cards"
    ],
    "title": "Kolibri provider execution catalog v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/provider-execution/request.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/provider-execution/request.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "a2a_request": {
        "$ref": "https://schemas.kolibriai.ru/v1/a2a/message.schema.json"
      },
      "agent_assignment": {
        "$ref": "https://schemas.kolibriai.ru/v1/agents/assignment.schema.json"
      },
      "attempt": {
        "$ref": "https://schemas.kolibriai.ru/v1/tasks/attempt.schema.json"
      },
      "developer_dispatch": {
        "oneOf": [
          {
            "$ref": "https://schemas.kolibriai.ru/v1/product/developer-dispatch.schema.json"
          },
          {
            "$ref": "https://schemas.kolibriai.ru/v1/product/developer-dispatch-v1.1.schema.json"
          }
        ]
      },
      "effect_key": {
        "pattern": "^effect_[0-9a-f]{40}$",
        "type": "string"
      },
      "lease_source": {
        "oneOf": [
          {
            "$ref": "https://schemas.kolibriai.ru/v1/product/developer-lease-source.schema.json"
          },
          {
            "$ref": "https://schemas.kolibriai.ru/v1/product/developer-lease-source-v1.1.schema.json"
          }
        ]
      },
      "requester_assignment": {
        "$ref": "https://schemas.kolibriai.ru/v1/agents/assignment.schema.json"
      },
      "schema_id": {
        "const": "kolibri.provider_execution.request"
      },
      "schema_version": {
        "const": "1.0"
      },
      "source_command": {
        "$ref": "https://schemas.kolibriai.ru/v1/common/command-envelope.schema.json"
      },
      "task": {
        "$ref": "https://schemas.kolibriai.ru/v1/tasks/task.schema.json"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "effect_key",
      "task",
      "attempt",
      "agent_assignment",
      "requester_assignment",
      "a2a_request",
      "developer_dispatch",
      "source_command",
      "lease_source"
    ],
    "title": "Kolibri provider execution request v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/provider-execution/result.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/provider-execution/result.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "else": {
          "properties": {
            "error": {
              "$ref": "#/definitions/error"
            },
            "output": {
              "type": "null"
            }
          }
        },
        "if": {
          "properties": {
            "status": {
              "const": "completed"
            }
          },
          "required": [
            "status"
          ]
        },
        "then": {
          "properties": {
            "error": {
              "type": "null"
            },
            "output": {
              "$ref": "#/definitions/output"
            }
          }
        }
      }
    ],
    "definitions": {
      "activity_event": {
        "additionalProperties": false,
        "properties": {
          "payload": {
            "type": "object"
          },
          "phase": {
            "maxLength": 120,
            "minLength": 1,
            "type": "string"
          }
        },
        "required": [
          "phase",
          "payload"
        ],
        "type": "object"
      },
      "bounded_id": {
        "maxLength": 512,
        "minLength": 1,
        "pattern": "^[^\\u0000]+$",
        "type": "string"
      },
      "error": {
        "additionalProperties": false,
        "properties": {
          "category": {
            "enum": [
              "configuration",
              "authentication",
              "unavailable",
              "invalid_output",
              "execution"
            ],
            "type": "string"
          },
          "code": {
            "pattern": "^[a-z][a-z0-9_.-]{2,95}$",
            "type": "string"
          },
          "retryable": {
            "type": "boolean"
          },
          "safe_message": {
            "maxLength": 1000,
            "minLength": 1,
            "type": "string"
          }
        },
        "required": [
          "code",
          "category",
          "retryable",
          "safe_message"
        ],
        "type": "object"
      },
      "output": {
        "additionalProperties": false,
        "oneOf": [
          {
            "properties": {
              "response": {
                "type": "string"
              },
              "tool_call": {
                "type": "null"
              }
            }
          },
          {
            "properties": {
              "response": {
                "type": "null"
              },
              "tool_call": {
                "type": "object"
              }
            }
          }
        ],
        "properties": {
          "response": {
            "oneOf": [
              {
                "maxLength": 200000,
                "minLength": 1,
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "session_id": {
            "oneOf": [
              {
                "maxLength": 256,
                "minLength": 1,
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "tool_call": {
            "oneOf": [
              {
                "additionalProperties": false,
                "properties": {
                  "arguments": {
                    "type": "object"
                  },
                  "name": {
                    "pattern": "^[a-z0-9][a-z0-9._-]{1,95}$",
                    "type": "string"
                  }
                },
                "required": [
                  "name",
                  "arguments"
                ],
                "type": "object"
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "response",
          "session_id",
          "tool_call"
        ],
        "type": "object"
      }
    },
    "properties": {
      "activity": {
        "items": {
          "$ref": "#/definitions/activity_event"
        },
        "maxItems": 128,
        "type": "array"
      },
      "assignment_id": {
        "$ref": "#/definitions/bounded_id"
      },
      "attempt_id": {
        "$ref": "#/definitions/bounded_id"
      },
      "effect_key": {
        "pattern": "^effect_[0-9a-f]{40}$",
        "type": "string"
      },
      "error": {
        "oneOf": [
          {
            "$ref": "#/definitions/error"
          },
          {
            "type": "null"
          }
        ]
      },
      "fencing_token": {
        "maximum": 9007199254740991,
        "minimum": 1,
        "type": "integer"
      },
      "lease_id": {
        "$ref": "#/definitions/bounded_id"
      },
      "output": {
        "oneOf": [
          {
            "$ref": "#/definitions/output"
          },
          {
            "type": "null"
          }
        ]
      },
      "replayed": {
        "type": "boolean"
      },
      "request_hash": {
        "pattern": "^sha256:[0-9a-f]{64}$",
        "type": "string"
      },
      "runtime_profile": {
        "pattern": "^[a-z0-9][a-z0-9._-]{1,95}$",
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.provider_execution.result"
      },
      "schema_version": {
        "const": "1.0"
      },
      "status": {
        "enum": [
          "completed",
          "failed"
        ],
        "type": "string"
      },
      "task_id": {
        "$ref": "#/definitions/bounded_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "effect_key",
      "request_hash",
      "task_id",
      "attempt_id",
      "assignment_id",
      "lease_id",
      "fencing_token",
      "runtime_profile",
      "status",
      "replayed",
      "output",
      "activity",
      "error"
    ],
    "title": "Kolibri provider execution result v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/quality/evidence.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/quality/evidence.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "if": {
          "properties": {
            "status": {
              "enum": [
                "withdrawn",
                "revoked"
              ]
            }
          },
          "required": [
            "status"
          ]
        },
        "then": {
          "properties": {
            "revocation": {
              "type": "object"
            }
          }
        }
      }
    ],
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "sha256": {
        "pattern": "^sha256:[a-f0-9]{64}$",
        "type": "string"
      }
    },
    "properties": {
      "applicability": {
        "enum": [
          "applicable",
          "partially_applicable",
          "not_applicable",
          "unknown"
        ],
        "type": "string"
      },
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "claim": {
        "additionalProperties": false,
        "properties": {
          "claim_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "statement": {
            "maxLength": 4000,
            "minLength": 1,
            "type": "string"
          },
          "target": {
            "additionalProperties": false,
            "properties": {
              "locator": {
                "maxLength": 1000,
                "minLength": 1,
                "type": "string"
              },
              "ref_id": {
                "$ref": "#/definitions/opaque_id"
              },
              "ref_version": {
                "minimum": 1,
                "type": "integer"
              }
            },
            "required": [
              "ref_id",
              "ref_version",
              "locator"
            ],
            "type": "object"
          }
        },
        "required": [
          "claim_id",
          "statement",
          "target"
        ],
        "type": "object"
      },
      "confidence": {
        "maximum": 1,
        "minimum": 0,
        "type": "number"
      },
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "created_by": {
        "$ref": "#/definitions/opaque_id"
      },
      "evidence_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "evidence_version": {
        "minimum": 1,
        "type": "integer"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "method": {
        "additionalProperties": false,
        "properties": {
          "method_ref": {
            "$ref": "#/definitions/opaque_id"
          },
          "method_type": {
            "enum": [
              "direct",
              "calculation",
              "retrieval",
              "inspection",
              "test",
              "human_attestation"
            ],
            "type": "string"
          },
          "method_version": {
            "pattern": "^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$",
            "type": "string"
          }
        },
        "required": [
          "method_type",
          "method_ref",
          "method_version"
        ],
        "type": "object"
      },
      "revocation": {
        "oneOf": [
          {
            "additionalProperties": false,
            "properties": {
              "reason": {
                "maxLength": 1000,
                "minLength": 1,
                "type": "string"
              },
              "revoked_at": {
                "format": "date-time",
                "type": "string"
              },
              "revoked_by": {
                "$ref": "#/definitions/opaque_id"
              }
            },
            "required": [
              "reason",
              "revoked_by",
              "revoked_at"
            ],
            "type": "object"
          },
          {
            "type": "null"
          }
        ]
      },
      "schema_id": {
        "const": "kolibri.evidence"
      },
      "schema_version": {
        "const": "1.0"
      },
      "source": {
        "additionalProperties": false,
        "properties": {
          "content_hash": {
            "$ref": "#/definitions/sha256"
          },
          "effective_from": {
            "oneOf": [
              {
                "format": "date-time",
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "effective_to": {
            "oneOf": [
              {
                "format": "date-time",
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "jurisdiction": {
            "oneOf": [
              {
                "maxLength": 160,
                "minLength": 1,
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "locator": {
            "maxLength": 2000,
            "minLength": 1,
            "type": "string"
          },
          "publisher_or_author": {
            "maxLength": 500,
            "minLength": 1,
            "type": "string"
          },
          "region": {
            "oneOf": [
              {
                "maxLength": 160,
                "minLength": 1,
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "retrieved_at": {
            "format": "date-time",
            "type": "string"
          },
          "source_type": {
            "enum": [
              "user_input",
              "document",
              "normative_source",
              "market_quote",
              "measurement",
              "calculation",
              "tool_result",
              "artifact",
              "test_result"
            ],
            "type": "string"
          }
        },
        "required": [
          "source_type",
          "locator",
          "publisher_or_author",
          "retrieved_at",
          "effective_from",
          "effective_to",
          "jurisdiction",
          "region",
          "content_hash"
        ],
        "type": "object"
      },
      "status": {
        "enum": [
          "active",
          "superseded",
          "withdrawn",
          "stale",
          "revoked"
        ],
        "type": "string"
      },
      "supersedes": {
        "oneOf": [
          {
            "additionalProperties": false,
            "properties": {
              "evidence_id": {
                "$ref": "#/definitions/opaque_id"
              },
              "evidence_version": {
                "minimum": 1,
                "type": "integer"
              }
            },
            "required": [
              "evidence_id",
              "evidence_version"
            ],
            "type": "object"
          },
          {
            "type": "null"
          }
        ]
      },
      "task_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "verifier": {
        "additionalProperties": false,
        "properties": {
          "check_refs": {
            "items": {
              "$ref": "#/definitions/opaque_id"
            },
            "type": "array",
            "uniqueItems": true
          },
          "status": {
            "enum": [
              "unverified",
              "passed",
              "failed",
              "inconclusive"
            ],
            "type": "string"
          },
          "verified_at": {
            "oneOf": [
              {
                "format": "date-time",
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "verified_by": {
            "oneOf": [
              {
                "$ref": "#/definitions/opaque_id"
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "status",
          "verified_by",
          "verified_at",
          "check_refs"
        ],
        "type": "object"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "evidence_id",
      "evidence_version",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "claim",
      "source",
      "method",
      "confidence",
      "applicability",
      "verifier",
      "status",
      "supersedes",
      "revocation",
      "created_by",
      "created_at"
    ],
    "title": "Kolibri Evidence v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/quality/finding.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/quality/finding.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "if": {
          "properties": {
            "status": {
              "enum": [
                "resolved",
                "accepted_risk"
              ]
            }
          },
          "required": [
            "status"
          ]
        },
        "then": {
          "properties": {
            "resolution": {
              "type": "object"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "status": {
              "const": "open"
            }
          },
          "required": [
            "status"
          ]
        },
        "then": {
          "properties": {
            "resolution": {
              "type": "null"
            }
          }
        }
      }
    ],
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "versioned_ref": {
        "additionalProperties": false,
        "properties": {
          "ref_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "version": {
            "minimum": 1,
            "type": "integer"
          }
        },
        "required": [
          "ref_id",
          "version"
        ],
        "type": "object"
      }
    },
    "properties": {
      "artifact_locator": {
        "maxLength": 1000,
        "minLength": 1,
        "type": "string"
      },
      "category": {
        "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
        "type": "string"
      },
      "evidence_refs": {
        "items": {
          "$ref": "#/definitions/versioned_ref"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "finding_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "owner_ref": {
        "$ref": "#/definitions/opaque_id"
      },
      "required_action": {
        "maxLength": 2000,
        "minLength": 1,
        "type": "string"
      },
      "resolution": {
        "oneOf": [
          {
            "additionalProperties": false,
            "properties": {
              "disposition": {
                "enum": [
                  "fixed",
                  "not_reproducible",
                  "accepted_risk",
                  "superseded"
                ],
                "type": "string"
              },
              "evidence_refs": {
                "items": {
                  "$ref": "#/definitions/versioned_ref"
                },
                "minItems": 1,
                "type": "array",
                "uniqueItems": true
              },
              "resolved_at": {
                "format": "date-time",
                "type": "string"
              },
              "resolved_by": {
                "$ref": "#/definitions/opaque_id"
              }
            },
            "required": [
              "disposition",
              "resolved_by",
              "resolved_at",
              "evidence_refs"
            ],
            "type": "object"
          },
          {
            "type": "null"
          }
        ]
      },
      "severity": {
        "enum": [
          "info",
          "low",
          "medium",
          "high",
          "critical"
        ],
        "type": "string"
      },
      "statement": {
        "maxLength": 4000,
        "minLength": 1,
        "type": "string"
      },
      "status": {
        "enum": [
          "open",
          "accepted_risk",
          "resolved",
          "superseded"
        ],
        "type": "string"
      }
    },
    "required": [
      "finding_id",
      "severity",
      "category",
      "statement",
      "artifact_locator",
      "evidence_refs",
      "required_action",
      "owner_ref",
      "status",
      "resolution"
    ],
    "title": "Kolibri Review Finding v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/quality/quality-manifest.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/quality/quality-manifest.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "if": {
          "properties": {
            "eligibility": {
              "const": "ineligible"
            }
          },
          "required": [
            "eligibility"
          ]
        },
        "then": {
          "properties": {
            "blockers": {
              "minItems": 1
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "artifact_status": {
              "enum": [
                "stale",
                "revoked",
                "superseded"
              ]
            }
          },
          "required": [
            "artifact_status"
          ]
        },
        "then": {
          "properties": {
            "eligibility": {
              "const": "ineligible"
            }
          }
        }
      }
    ],
    "definitions": {
      "artifact_ref": {
        "additionalProperties": false,
        "properties": {
          "artifact_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "artifact_version": {
            "minimum": 1,
            "type": "integer"
          },
          "content_hash": {
            "$ref": "#/definitions/sha256"
          }
        },
        "required": [
          "artifact_id",
          "artifact_version",
          "content_hash"
        ],
        "type": "object"
      },
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "sha256": {
        "pattern": "^sha256:[a-f0-9]{64}$",
        "type": "string"
      },
      "versioned_ref": {
        "additionalProperties": false,
        "properties": {
          "ref_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "version": {
            "minimum": 1,
            "type": "integer"
          }
        },
        "required": [
          "ref_id",
          "version"
        ],
        "type": "object"
      }
    },
    "properties": {
      "artifact_ref": {
        "$ref": "#/definitions/artifact_ref"
      },
      "artifact_state_version": {
        "minimum": 1,
        "type": "integer"
      },
      "artifact_status": {
        "enum": [
          "draft",
          "in_review",
          "approved_internal",
          "released",
          "stale",
          "revoked",
          "superseded"
        ],
        "type": "string"
      },
      "blockers": {
        "items": {
          "enum": [
            "artifact_not_approved",
            "artifact_stale",
            "artifact_revoked",
            "evidence_missing_or_invalid",
            "review_incomplete",
            "blocking_finding",
            "signoff_missing",
            "signoff_stale_or_revoked",
            "policy_denied"
          ],
          "type": "string"
        },
        "type": "array",
        "uniqueItems": true
      },
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "eligibility": {
        "enum": [
          "eligible_internal",
          "eligible_release",
          "ineligible"
        ],
        "type": "string"
      },
      "evidence_refs": {
        "items": {
          "$ref": "#/definitions/versioned_ref"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "generated_at": {
        "format": "date-time",
        "type": "string"
      },
      "generated_by": {
        "$ref": "#/definitions/opaque_id"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "manifest_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "manifest_version": {
        "minimum": 1,
        "type": "integer"
      },
      "review_refs": {
        "items": {
          "$ref": "#/definitions/versioned_ref"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "schema_id": {
        "const": "kolibri.artifact_quality_manifest"
      },
      "schema_version": {
        "const": "1.0"
      },
      "signoff_refs": {
        "items": {
          "$ref": "#/definitions/versioned_ref"
        },
        "type": "array",
        "uniqueItems": true
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "manifest_id",
      "manifest_version",
      "tenant_id",
      "goal_id",
      "case_id",
      "artifact_ref",
      "artifact_state_version",
      "artifact_status",
      "evidence_refs",
      "review_refs",
      "signoff_refs",
      "eligibility",
      "blockers",
      "generated_at",
      "generated_by"
    ],
    "title": "Kolibri Artifact quality manifest v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/quality/review.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/quality/review.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "if": {
          "properties": {
            "status": {
              "const": "completed"
            }
          },
          "required": [
            "status"
          ]
        },
        "then": {
          "properties": {
            "completed_at": {
              "type": "string"
            },
            "disposition": {
              "enum": [
                "changes_requested",
                "rejected",
                "accepted_with_conditions",
                "approved_internal"
              ]
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "status": {
              "const": "open"
            }
          },
          "required": [
            "status"
          ]
        },
        "then": {
          "properties": {
            "completed_at": {
              "type": "null"
            },
            "disposition": {
              "const": "pending"
            }
          }
        }
      }
    ],
    "definitions": {
      "artifact_ref": {
        "additionalProperties": false,
        "properties": {
          "artifact_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "artifact_version": {
            "minimum": 1,
            "type": "integer"
          },
          "content_hash": {
            "$ref": "#/definitions/sha256"
          }
        },
        "required": [
          "artifact_id",
          "artifact_version",
          "content_hash"
        ],
        "type": "object"
      },
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "sha256": {
        "pattern": "^sha256:[a-f0-9]{64}$",
        "type": "string"
      },
      "versioned_ref": {
        "additionalProperties": false,
        "properties": {
          "ref_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "version": {
            "minimum": 1,
            "type": "integer"
          }
        },
        "required": [
          "ref_id",
          "version"
        ],
        "type": "object"
      }
    },
    "properties": {
      "artifact_ref": {
        "$ref": "#/definitions/artifact_ref"
      },
      "author_actor_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "completed_at": {
        "oneOf": [
          {
            "format": "date-time",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "criteria": {
        "items": {
          "additionalProperties": false,
          "properties": {
            "criterion_id": {
              "$ref": "#/definitions/opaque_id"
            },
            "evidence_refs": {
              "items": {
                "$ref": "#/definitions/versioned_ref"
              },
              "minItems": 1,
              "type": "array",
              "uniqueItems": true
            },
            "result": {
              "enum": [
                "passed",
                "failed",
                "not_applicable",
                "inconclusive"
              ],
              "type": "string"
            }
          },
          "required": [
            "criterion_id",
            "result",
            "evidence_refs"
          ],
          "type": "object"
        },
        "minItems": 1,
        "type": "array"
      },
      "disposition": {
        "enum": [
          "pending",
          "changes_requested",
          "rejected",
          "accepted_with_conditions",
          "approved_internal"
        ],
        "type": "string"
      },
      "evidence_refs": {
        "items": {
          "$ref": "#/definitions/versioned_ref"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "findings": {
        "items": {
          "$ref": "https://schemas.kolibriai.ru/v1/quality/finding.schema.json"
        },
        "maxItems": 1000,
        "type": "array"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "requested_at": {
        "format": "date-time",
        "type": "string"
      },
      "review_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "review_version": {
        "minimum": 1,
        "type": "integer"
      },
      "reviewer_actor_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "reviewer_assignment_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "schema_id": {
        "const": "kolibri.review"
      },
      "schema_version": {
        "const": "1.0"
      },
      "scope": {
        "items": {
          "enum": [
            "technical",
            "commercial",
            "legal",
            "quality",
            "security",
            "release"
          ],
          "type": "string"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "status": {
        "enum": [
          "open",
          "completed",
          "superseded",
          "stale",
          "revoked"
        ],
        "type": "string"
      },
      "supersedes": {
        "oneOf": [
          {
            "$ref": "#/definitions/versioned_ref"
          },
          {
            "type": "null"
          }
        ]
      },
      "task_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "review_id",
      "review_version",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "artifact_ref",
      "author_actor_id",
      "reviewer_actor_id",
      "reviewer_assignment_id",
      "scope",
      "criteria",
      "evidence_refs",
      "findings",
      "disposition",
      "status",
      "requested_at",
      "completed_at",
      "supersedes"
    ],
    "title": "Kolibri Artifact Review v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/quality/signoff.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/quality/signoff.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "if": {
          "properties": {
            "signoff_type": {
              "const": "internal_approval"
            }
          },
          "required": [
            "signoff_type"
          ]
        },
        "then": {
          "properties": {
            "signature_ref": {
              "type": "null"
            },
            "signer": {
              "properties": {
                "actor_type": {
                  "enum": [
                    "agent",
                    "service"
                  ]
                },
                "credential_ref": {
                  "type": "null"
                }
              }
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "signoff_type": {
              "const": "qualified_human_signoff"
            }
          },
          "required": [
            "signoff_type"
          ]
        },
        "then": {
          "properties": {
            "signature_ref": {
              "type": "string"
            },
            "signer": {
              "properties": {
                "actor_type": {
                  "const": "human"
                },
                "credential_ref": {
                  "type": "string"
                }
              }
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "status": {
              "const": "revoked"
            }
          },
          "required": [
            "status"
          ]
        },
        "then": {
          "properties": {
            "revocation": {
              "type": "object"
            }
          }
        }
      }
    ],
    "definitions": {
      "artifact_ref": {
        "additionalProperties": false,
        "properties": {
          "artifact_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "artifact_version": {
            "minimum": 1,
            "type": "integer"
          },
          "content_hash": {
            "$ref": "#/definitions/sha256"
          }
        },
        "required": [
          "artifact_id",
          "artifact_version",
          "content_hash"
        ],
        "type": "object"
      },
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "sha256": {
        "pattern": "^sha256:[a-f0-9]{64}$",
        "type": "string"
      },
      "versioned_ref": {
        "additionalProperties": false,
        "properties": {
          "ref_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "version": {
            "minimum": 1,
            "type": "integer"
          }
        },
        "required": [
          "ref_id",
          "version"
        ],
        "type": "object"
      }
    },
    "properties": {
      "artifact_ref": {
        "$ref": "#/definitions/artifact_ref"
      },
      "authority_basis_ref": {
        "$ref": "#/definitions/opaque_id"
      },
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "granted_at": {
        "format": "date-time",
        "type": "string"
      },
      "policy_decision": {
        "additionalProperties": false,
        "properties": {
          "decision_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "effect": {
            "const": "allow"
          },
          "policy_version": {
            "pattern": "^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$",
            "type": "string"
          }
        },
        "required": [
          "decision_id",
          "policy_version",
          "effect"
        ],
        "type": "object"
      },
      "review_refs": {
        "items": {
          "$ref": "#/definitions/versioned_ref"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "revocation": {
        "oneOf": [
          {
            "additionalProperties": false,
            "properties": {
              "reason": {
                "maxLength": 1000,
                "minLength": 1,
                "type": "string"
              },
              "revoked_at": {
                "format": "date-time",
                "type": "string"
              },
              "revoked_by": {
                "$ref": "#/definitions/opaque_id"
              }
            },
            "required": [
              "reason",
              "revoked_by",
              "revoked_at"
            ],
            "type": "object"
          },
          {
            "type": "null"
          }
        ]
      },
      "schema_id": {
        "const": "kolibri.signoff"
      },
      "schema_version": {
        "const": "1.0"
      },
      "signature_ref": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "signer": {
        "additionalProperties": false,
        "properties": {
          "actor_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "actor_type": {
            "enum": [
              "human",
              "agent",
              "service"
            ],
            "type": "string"
          },
          "credential_ref": {
            "oneOf": [
              {
                "$ref": "#/definitions/opaque_id"
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "actor_id",
          "actor_type",
          "credential_ref"
        ],
        "type": "object"
      },
      "signoff_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "signoff_type": {
        "enum": [
          "internal_approval",
          "corporate_release_authorization",
          "qualified_human_signoff",
          "client_acceptance"
        ],
        "type": "string"
      },
      "signoff_version": {
        "minimum": 1,
        "type": "integer"
      },
      "status": {
        "enum": [
          "granted",
          "revoked",
          "stale",
          "superseded"
        ],
        "type": "string"
      },
      "supersedes": {
        "oneOf": [
          {
            "$ref": "#/definitions/versioned_ref"
          },
          {
            "type": "null"
          }
        ]
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "signoff_id",
      "signoff_version",
      "tenant_id",
      "goal_id",
      "case_id",
      "artifact_ref",
      "signoff_type",
      "signer",
      "authority_basis_ref",
      "policy_decision",
      "review_refs",
      "signature_ref",
      "status",
      "granted_at",
      "revocation",
      "supersedes"
    ],
    "title": "Kolibri SignOff v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/tasks/attempt.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/tasks/attempt.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "assignment_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "attempt_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "attempt_number": {
        "minimum": 1,
        "type": "integer"
      },
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "effect_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "error": {
        "oneOf": [
          {
            "additionalProperties": false,
            "properties": {
              "error_type": {
                "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
                "type": "string"
              },
              "message": {
                "maxLength": 2000,
                "minLength": 1,
                "type": "string"
              },
              "retryable": {
                "type": "boolean"
              }
            },
            "required": [
              "error_type",
              "message",
              "retryable"
            ],
            "type": "object"
          },
          {
            "type": "null"
          }
        ]
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "lease": {
        "$ref": "https://schemas.kolibriai.ru/v1/tasks/lease.schema.json"
      },
      "result_artifact_refs": {
        "items": {
          "$ref": "#/definitions/opaque_id"
        },
        "type": "array",
        "uniqueItems": true
      },
      "result_hash": {
        "oneOf": [
          {
            "pattern": "^sha256:[0-9a-f]{64}$",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "schema_id": {
        "const": "kolibri.task_attempt"
      },
      "schema_version": {
        "const": "1.0"
      },
      "status": {
        "enum": [
          "created",
          "leased",
          "running",
          "submitted",
          "verifying",
          "completed",
          "failed_retryable",
          "failed_terminal",
          "expired",
          "cancelled"
        ],
        "type": "string"
      },
      "task_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "updated_at": {
        "format": "date-time",
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "attempt_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "task_id",
      "attempt_number",
      "assignment_id",
      "status",
      "lease",
      "effect_id",
      "result_artifact_refs",
      "result_hash",
      "error",
      "created_at",
      "updated_at"
    ],
    "title": "Kolibri TaskAttempt v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/tasks/lease.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/tasks/lease.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "acquired_at": {
        "format": "date-time",
        "type": "string"
      },
      "agent_card_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "authority_epoch": {
        "minimum": 1,
        "type": "integer"
      },
      "authority_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "expires_at": {
        "format": "date-time",
        "type": "string"
      },
      "fencing_token": {
        "minimum": 1,
        "type": "integer"
      },
      "heartbeat_at": {
        "format": "date-time",
        "type": "string"
      },
      "lease_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "worker_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "lease_id",
      "authority_id",
      "authority_epoch",
      "fencing_token",
      "worker_id",
      "agent_card_id",
      "acquired_at",
      "heartbeat_at",
      "expires_at"
    ],
    "title": "Kolibri TaskLease v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/tasks/owner-state.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/tasks/owner-state.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "authority_epoch": {
        "minimum": 1,
        "type": "integer"
      },
      "authority_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "committed_effects": {
        "additionalProperties": {
          "additionalProperties": false,
          "properties": {
            "attempt_id": {
              "$ref": "#/definitions/opaque_id"
            },
            "result_hash": {
              "pattern": "^sha256:[0-9a-f]{64}$",
              "type": "string"
            }
          },
          "required": [
            "attempt_id",
            "result_hash"
          ],
          "type": "object"
        },
        "type": "object"
      },
      "current_assignment_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "current_attempt_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "current_status": {
        "$ref": "https://schemas.kolibriai.ru/v1/tasks/task.schema.json#/definitions/status"
      },
      "fencing_token": {
        "minimum": 1,
        "type": "integer"
      },
      "lease_expires_at": {
        "format": "date-time",
        "type": "string"
      },
      "lease_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "schema_id": {
        "const": "kolibri.task_owner_state"
      },
      "schema_version": {
        "const": "1.0"
      },
      "task_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "task_version": {
        "minimum": 1,
        "type": "integer"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "tenant_id",
      "task_id",
      "task_version",
      "current_status",
      "current_attempt_id",
      "current_assignment_id",
      "lease_id",
      "authority_id",
      "authority_epoch",
      "fencing_token",
      "lease_expires_at",
      "committed_effects"
    ],
    "title": "Kolibri owner-local Task mutation state v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/tasks/task-graph-apply.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/tasks/task-graph-apply.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "expected_graph_version": {
        "minimum": 0,
        "type": "integer"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "graph_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "next_graph_version": {
        "minimum": 1,
        "type": "integer"
      },
      "reason": {
        "maxLength": 1000,
        "minLength": 1,
        "type": "string"
      },
      "requested_at": {
        "format": "date-time",
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.task_graph.apply.command"
      },
      "schema_version": {
        "const": "1.0"
      },
      "tasks": {
        "items": {
          "$ref": "https://schemas.kolibriai.ru/v1/tasks/task.schema.json"
        },
        "maxItems": 100,
        "minItems": 1,
        "type": "array"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "graph_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "expected_graph_version",
      "next_graph_version",
      "tasks",
      "reason",
      "requested_at"
    ],
    "title": "Kolibri TaskGraph apply command payload v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/tasks/task-graph-change-event.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/tasks/task-graph-change-event.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "if": {
          "properties": {
            "previous_graph_version": {
              "type": "null"
            }
          },
          "required": [
            "previous_graph_version"
          ]
        },
        "then": {
          "properties": {
            "new_graph_version": {
              "const": 1
            }
          }
        }
      }
    ],
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "graph_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "new_graph_version": {
        "minimum": 1,
        "type": "integer"
      },
      "previous_graph_version": {
        "oneOf": [
          {
            "minimum": 1,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ]
      },
      "runnable_task_ids": {
        "items": {
          "$ref": "#/definitions/opaque_id"
        },
        "type": "array",
        "uniqueItems": true
      },
      "schema_id": {
        "const": "kolibri.task_graph.changed.event"
      },
      "schema_version": {
        "const": "1.0"
      },
      "task_count": {
        "maximum": 100,
        "minimum": 1,
        "type": "integer"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "graph_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "previous_graph_version",
      "new_graph_version",
      "task_count",
      "runnable_task_ids"
    ],
    "title": "Kolibri TaskGraph changed event payload v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/tasks/task-graph.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/tasks/task-graph.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "properties": {
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "graph_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "graph_version": {
        "minimum": 1,
        "type": "integer"
      },
      "relations": {
        "items": {
          "additionalProperties": false,
          "properties": {
            "blocked_by_task_ids": {
              "items": {
                "$ref": "#/definitions/opaque_id"
              },
              "type": "array",
              "uniqueItems": true
            },
            "child_task_ids": {
              "items": {
                "$ref": "#/definitions/opaque_id"
              },
              "type": "array",
              "uniqueItems": true
            },
            "dependency_task_ids": {
              "items": {
                "$ref": "#/definitions/opaque_id"
              },
              "type": "array",
              "uniqueItems": true
            },
            "dependent_task_ids": {
              "items": {
                "$ref": "#/definitions/opaque_id"
              },
              "type": "array",
              "uniqueItems": true
            },
            "parent_task_id": {
              "oneOf": [
                {
                  "$ref": "#/definitions/opaque_id"
                },
                {
                  "type": "null"
                }
              ]
            },
            "runnable": {
              "type": "boolean"
            },
            "task_id": {
              "$ref": "#/definitions/opaque_id"
            }
          },
          "required": [
            "task_id",
            "parent_task_id",
            "child_task_ids",
            "dependency_task_ids",
            "dependent_task_ids",
            "blocked_by_task_ids",
            "runnable"
          ],
          "type": "object"
        },
        "maxItems": 100,
        "minItems": 1,
        "type": "array"
      },
      "runnable_task_ids": {
        "items": {
          "$ref": "#/definitions/opaque_id"
        },
        "type": "array",
        "uniqueItems": true
      },
      "schema_id": {
        "const": "kolibri.task_graph"
      },
      "schema_version": {
        "const": "1.0"
      },
      "tasks": {
        "items": {
          "$ref": "https://schemas.kolibriai.ru/v1/tasks/task.schema.json"
        },
        "maxItems": 100,
        "minItems": 1,
        "type": "array"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "topological_task_ids": {
        "items": {
          "$ref": "#/definitions/opaque_id"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "updated_at": {
        "format": "date-time",
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "graph_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "graph_version",
      "tasks",
      "relations",
      "topological_task_ids",
      "runnable_task_ids",
      "created_at",
      "updated_at"
    ],
    "title": "Kolibri TaskGraph read model v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/tasks/task-transition.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/tasks/task-transition.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "assignment_id": {
        "oneOf": [
          {
            "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "attempt_id": {
        "oneOf": [
          {
            "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "expected_version": {
        "minimum": 1,
        "type": "integer"
      },
      "fencing_token": {
        "oneOf": [
          {
            "minimum": 1,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ]
      },
      "from_status": {
        "$ref": "https://schemas.kolibriai.ru/v1/tasks/task.schema.json#/definitions/status"
      },
      "lease_id": {
        "oneOf": [
          {
            "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "next_version": {
        "minimum": 2,
        "type": "integer"
      },
      "reason": {
        "maxLength": 1000,
        "minLength": 1,
        "type": "string"
      },
      "requested_at": {
        "format": "date-time",
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.task.transition.command"
      },
      "schema_version": {
        "const": "1.0"
      },
      "task_id": {
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "to_status": {
        "$ref": "https://schemas.kolibriai.ru/v1/tasks/task.schema.json#/definitions/status"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "task_id",
      "expected_version",
      "next_version",
      "from_status",
      "to_status",
      "attempt_id",
      "assignment_id",
      "lease_id",
      "fencing_token",
      "reason",
      "requested_at"
    ],
    "title": "Kolibri Task transition command payload v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/tasks/task.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/tasks/task.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "if": {
          "properties": {
            "state": {
              "enum": [
                "leased",
                "running",
                "submitted",
                "verifying"
              ]
            }
          },
          "required": [
            "state"
          ]
        },
        "then": {
          "properties": {
            "current_assignment_id": {
              "type": "string"
            },
            "current_attempt_id": {
              "type": "string"
            }
          }
        }
      }
    ],
    "definitions": {
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "status": {
        "enum": [
          "proposed",
          "accepted",
          "ready",
          "leased",
          "running",
          "submitted",
          "verifying",
          "blocked",
          "revision_requested",
          "failed_retryable",
          "completed",
          "failed_terminal",
          "cancelled",
          "superseded"
        ],
        "type": "string"
      }
    },
    "properties": {
      "acceptance_criteria": {
        "items": {
          "additionalProperties": false,
          "properties": {
            "criterion_id": {
              "$ref": "#/definitions/opaque_id"
            },
            "required": {
              "type": "boolean"
            },
            "statement": {
              "maxLength": 1000,
              "minLength": 1,
              "type": "string"
            },
            "verification_method": {
              "maxLength": 1000,
              "minLength": 1,
              "type": "string"
            }
          },
          "required": [
            "criterion_id",
            "statement",
            "verification_method",
            "required"
          ],
          "type": "object"
        },
        "minItems": 1,
        "type": "array"
      },
      "budget": {
        "additionalProperties": false,
        "properties": {
          "compute_units_limit": {
            "minimum": 0,
            "type": "integer"
          },
          "currency": {
            "pattern": "^[A-Z]{3}$",
            "type": "string"
          },
          "external_spend_limit_minor": {
            "minimum": 0,
            "type": "integer"
          },
          "tool_calls_limit": {
            "minimum": 0,
            "type": "integer"
          }
        },
        "required": [
          "compute_units_limit",
          "tool_calls_limit",
          "external_spend_limit_minor",
          "currency"
        ],
        "type": "object"
      },
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "current_assignment_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "current_attempt_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "deadline_at": {
        "oneOf": [
          {
            "format": "date-time",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "dependency_task_ids": {
        "items": {
          "$ref": "#/definitions/opaque_id"
        },
        "type": "array",
        "uniqueItems": true
      },
      "expected_outputs": {
        "items": {
          "additionalProperties": false,
          "properties": {
            "artifact_type": {
              "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
              "type": "string"
            },
            "evidence_required": {
              "type": "boolean"
            },
            "output_id": {
              "$ref": "#/definitions/opaque_id"
            },
            "schema_id": {
              "pattern": "^kolibri\\.[a-z][a-z0-9_.]+$",
              "type": "string"
            }
          },
          "required": [
            "output_id",
            "artifact_type",
            "schema_id",
            "evidence_required"
          ],
          "type": "object"
        },
        "minItems": 1,
        "type": "array"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "graph_version": {
        "minimum": 1,
        "type": "integer"
      },
      "kind": {
        "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
        "type": "string"
      },
      "objective": {
        "maxLength": 4000,
        "minLength": 1,
        "type": "string"
      },
      "parent_task_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "required_capabilities": {
        "items": {
          "pattern": "^[a-z][a-z0-9_.:-]{2,127}$",
          "type": "string"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
      },
      "risk_class": {
        "enum": [
          "low",
          "medium",
          "high",
          "critical"
        ],
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.task"
      },
      "schema_version": {
        "const": "1.0"
      },
      "state": {
        "$ref": "#/definitions/status"
      },
      "task_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "title": {
        "maxLength": 240,
        "minLength": 1,
        "type": "string"
      },
      "updated_at": {
        "format": "date-time",
        "type": "string"
      },
      "version": {
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "task_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "title",
      "objective",
      "kind",
      "dependency_task_ids",
      "required_capabilities",
      "acceptance_criteria",
      "expected_outputs",
      "budget",
      "deadline_at",
      "risk_class",
      "state",
      "graph_version",
      "version",
      "current_attempt_id",
      "current_assignment_id",
      "created_at",
      "updated_at"
    ],
    "title": "Kolibri Task v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/workflows/project-workflow.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/workflows/project-workflow.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "allOf": [
      {
        "if": {
          "properties": {
            "activity_count": {
              "const": 0
            },
            "query_count": {
              "const": 0
            },
            "signal_count": {
              "const": 0
            },
            "timer_count": {
              "const": 0
            }
          }
        },
        "then": {
          "properties": {
            "activities": {
              "maxItems": 0
            },
            "open_queries": {
              "maxItems": 0
            },
            "pending_signals": {
              "maxItems": 0
            },
            "status": {
              "enum": [
                "completed",
                "failed",
                "cancelled",
                "superseded"
              ]
            },
            "timers": {
              "maxItems": 0
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "status": {
              "enum": [
                "completed",
                "failed",
                "cancelled",
                "superseded"
              ]
            }
          }
        },
        "then": {
          "properties": {
            "activity_count": {
              "minimum": 1
            },
            "version": {
              "minimum": 2
            }
          }
        }
      }
    ],
    "definitions": {
      "activity": {
        "additionalProperties": false,
        "properties": {
          "activity_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "activity_type": {
            "pattern": "^[a-z][a-z0-9_.-]{2,80}$",
            "type": "string"
          },
          "assigned_node": {
            "oneOf": [
              {
                "maxLength": 255,
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "execution_attempt": {
            "minimum": 1,
            "type": "integer"
          },
          "execution_attempt_id": {
            "oneOf": [
              {
                "$ref": "#/definitions/opaque_id"
              },
              {
                "type": "null"
              }
            ]
          },
          "started_at": {
            "format": "date-time",
            "type": "string"
          },
          "status": {
            "enum": [
              "queued",
              "assigned",
              "running",
              "waiting_signal",
              "waiting_timer",
              "succeeded",
              "failed",
              "cancelled",
              "superseded"
            ],
            "type": "string"
          },
          "task_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "updated_at": {
            "format": "date-time",
            "type": "string"
          }
        },
        "required": [
          "activity_id",
          "task_id",
          "activity_type",
          "status",
          "execution_attempt",
          "started_at",
          "updated_at"
        ],
        "type": "object"
      },
      "opaque_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "query_ref": {
        "additionalProperties": false,
        "properties": {
          "query_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "query_type": {
            "enum": [
              "task_projection",
              "artifact_state",
              "owner_state",
              "telemetry"
            ],
            "type": "string"
          },
          "requested_at": {
            "format": "date-time",
            "type": "string"
          },
          "status": {
            "enum": [
              "queued",
              "in_progress",
              "served",
              "failed"
            ],
            "type": "string"
          }
        },
        "required": [
          "query_id",
          "query_type",
          "status",
          "requested_at"
        ],
        "type": "object"
      },
      "signal_ref": {
        "additionalProperties": false,
        "properties": {
          "received_at": {
            "format": "date-time",
            "type": "string"
          },
          "signal_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "signal_type": {
            "enum": [
              "user_change",
              "approval",
              "payment",
              "policy_change",
              "cancellation"
            ],
            "type": "string"
          },
          "status": {
            "enum": [
              "queued",
              "applied",
              "ignored",
              "rejected",
              "failed"
            ],
            "type": "string"
          }
        },
        "required": [
          "signal_id",
          "signal_type",
          "status",
          "received_at"
        ],
        "type": "object"
      },
      "timer_ref": {
        "additionalProperties": false,
        "properties": {
          "fired_at": {
            "oneOf": [
              {
                "format": "date-time",
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "scheduled_at": {
            "format": "date-time",
            "type": "string"
          },
          "status": {
            "enum": [
              "waiting",
              "fired",
              "cancelled"
            ],
            "type": "string"
          },
          "timer_id": {
            "$ref": "#/definitions/opaque_id"
          },
          "timer_type": {
            "enum": [
              "lease_expiry",
              "retry_backoff",
              "deadline_policy"
            ],
            "type": "string"
          }
        },
        "required": [
          "timer_id",
          "timer_type",
          "scheduled_at",
          "status"
        ],
        "type": "object"
      }
    },
    "properties": {
      "activities": {
        "items": {
          "$ref": "#/definitions/activity"
        },
        "type": "array"
      },
      "activity_count": {
        "minimum": 0,
        "type": "integer"
      },
      "case_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "created_at": {
        "format": "date-time",
        "type": "string"
      },
      "goal_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "graph_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "graph_version": {
        "minimum": 1,
        "type": "integer"
      },
      "open_queries": {
        "items": {
          "$ref": "#/definitions/query_ref"
        },
        "type": "array"
      },
      "parent_workflow_id": {
        "oneOf": [
          {
            "$ref": "#/definitions/opaque_id"
          },
          {
            "type": "null"
          }
        ]
      },
      "pending_signals": {
        "items": {
          "$ref": "#/definitions/signal_ref"
        },
        "type": "array"
      },
      "query_count": {
        "minimum": 0,
        "type": "integer"
      },
      "schema_id": {
        "const": "kolibri.project_workflow"
      },
      "schema_version": {
        "const": "1.0"
      },
      "signal_count": {
        "minimum": 0,
        "type": "integer"
      },
      "status": {
        "enum": [
          "running",
          "waiting_signal",
          "waiting_query",
          "waiting_timer",
          "cancelling",
          "completed",
          "failed",
          "cancelled",
          "superseded"
        ],
        "type": "string"
      },
      "tenant_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "timer_count": {
        "minimum": 0,
        "type": "integer"
      },
      "timers": {
        "items": {
          "$ref": "#/definitions/timer_ref"
        },
        "type": "array"
      },
      "updated_at": {
        "format": "date-time",
        "type": "string"
      },
      "version": {
        "minimum": 1,
        "type": "integer"
      },
      "workflow_id": {
        "$ref": "#/definitions/opaque_id"
      },
      "workflow_type": {
        "enum": [
          "project",
          "child",
          "child.retry",
          "child.review"
        ],
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "workflow_id",
      "tenant_id",
      "goal_id",
      "case_id",
      "workflow_type",
      "status",
      "version",
      "graph_id",
      "graph_version",
      "activity_count",
      "signal_count",
      "query_count",
      "timer_count",
      "activities",
      "pending_signals",
      "open_queries",
      "timers",
      "created_at",
      "updated_at"
    ],
    "title": "Kolibri Project Workflow aggregate v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/workflows/workflow-query.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/workflows/workflow-query.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "query_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "query_scope": {
        "oneOf": [
          {
            "maxLength": 400,
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "query_type": {
        "enum": [
          "task_projection",
          "artifact_state",
          "owner_state",
          "telemetry"
        ],
        "type": "string"
      },
      "requested_at": {
        "format": "date-time",
        "type": "string"
      },
      "response_contract_id": {
        "maxLength": 255,
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.workflow.query"
      },
      "schema_version": {
        "const": "1.0"
      },
      "workflow_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "workflow_id",
      "query_id",
      "query_type",
      "requested_at"
    ],
    "title": "Kolibri Project Workflow query v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/workflows/workflow-signal.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/workflows/workflow-signal.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "payload_hash": {
        "pattern": "^sha256:[0-9a-f]{64}$",
        "type": "string"
      },
      "requested_at": {
        "format": "date-time",
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.workflow.signal"
      },
      "schema_version": {
        "const": "1.0"
      },
      "signal_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "signal_type": {
        "enum": [
          "user_change",
          "approval",
          "payment",
          "policy_change",
          "cancellation"
        ],
        "type": "string"
      },
      "source": {
        "maxLength": 120,
        "minLength": 2,
        "type": "string"
      },
      "workflow_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "workflow_id",
      "signal_id",
      "signal_type",
      "source",
      "payload_hash",
      "requested_at"
    ],
    "title": "Kolibri Project Workflow signal v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/workflows/workflow-timer.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/workflows/workflow-timer.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "fired_at": {
        "oneOf": [
          {
            "format": "date-time",
            "type": "string"
          },
          {
            "type": "null"
          }
        ]
      },
      "scheduled_at": {
        "format": "date-time",
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.workflow.timer"
      },
      "schema_version": {
        "const": "1.0"
      },
      "status": {
        "enum": [
          "waiting",
          "fired",
          "cancelled",
          "rescheduled"
        ],
        "type": "string"
      },
      "timer_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      },
      "timer_type": {
        "enum": [
          "lease_expiry",
          "retry_backoff",
          "deadline_policy",
          "poll_interval"
        ],
        "type": "string"
      },
      "workflow_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "workflow_id",
      "timer_id",
      "timer_type",
      "scheduled_at",
      "status"
    ],
    "title": "Kolibri Project Workflow timer v1",
    "type": "object"
  },
  "https://schemas.kolibriai.ru/v1/workflows/workflow-version.schema.json": {
    "$id": "https://schemas.kolibriai.ru/v1/workflows/workflow-version.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": false,
    "properties": {
      "expected_version": {
        "minimum": 1,
        "type": "integer"
      },
      "next_version": {
        "minimum": 2,
        "type": "integer"
      },
      "reason": {
        "maxLength": 1000,
        "minLength": 1,
        "type": "string"
      },
      "requested_at": {
        "format": "date-time",
        "type": "string"
      },
      "schema_id": {
        "const": "kolibri.workflow.version.transition.command"
      },
      "schema_version": {
        "const": "1.0"
      },
      "workflow_id": {
        "maxLength": 160,
        "minLength": 8,
        "pattern": "^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
        "type": "string"
      }
    },
    "required": [
      "schema_id",
      "schema_version",
      "workflow_id",
      "expected_version",
      "next_version",
      "reason",
      "requested_at"
    ],
    "title": "Kolibri Project Workflow version command v1",
    "type": "object"
  }
}

export interface ContractValidationResult {
  readonly ok: boolean
  readonly code: 'unsupported_schema' | 'invalid_contract' | null
  readonly violations: ReadonlyArray<{ readonly path: string; readonly code: string }>
}

export function validateContractTopLevel(
  value: unknown,
  expectedSchemaId?: KolibriContractSchemaId,
): ContractValidationResult {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return { ok: false, code: 'invalid_contract', violations: [{ path: '/', code: 'type' }] }
  }
  const record = value as Record<string, unknown>
  const schemaId = typeof record.schema_id === 'string' ? record.schema_id : ''
  const spec = CONTRACT_SPECS[schemaId as keyof typeof CONTRACT_SPECS]
  if (!spec || (expectedSchemaId && schemaId !== expectedSchemaId) || record.schema_version !== spec.schema_version) {
    return { ok: false, code: 'unsupported_schema', violations: [{ path: '/schema_version', code: 'unsupported_schema' }] }
  }
  const allowed = new Set<string>(spec.allowed_fields)
  const required = new Set<string>(spec.required_fields)
  const violations: Array<{ path: string; code: string }> = []
  for (const key of Object.keys(record)) {
    if (!allowed.has(key)) violations.push({ path: `/${key}`, code: 'additionalProperties' })
  }
  for (const key of required) {
    if (!(key in record)) violations.push({ path: `/${key}`, code: 'required' })
  }
  return { ok: violations.length === 0, code: violations.length ? 'invalid_contract' : null, violations }
}

export type ContractAuthorityRole =
  | 'logical_home_control_plane'
  | 'product_data_authority'
  | 'provider_execution_authority'

type JsonRecord = Readonly<Record<string, unknown>>
const RFC3339_DATE_TIME =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$/

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isRfc3339DateTime(value: string): boolean {
  const match = RFC3339_DATE_TIME.exec(value)
  if (!match) return false

  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const hour = Number(match[4])
  const minute = Number(match[5])
  const second = Number(match[6])
  if (
    year < 1 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    hour > 23 ||
    minute > 59 ||
    second > 59
  ) {
    return false
  }

  const calendar = new Date(0)
  calendar.setUTCFullYear(year, month - 1, day)
  calendar.setUTCHours(hour, minute, second, 0)
  if (
    calendar.getUTCFullYear() !== year ||
    calendar.getUTCMonth() !== month - 1 ||
    calendar.getUTCDate() !== day ||
    calendar.getUTCHours() !== hour ||
    calendar.getUTCMinutes() !== minute ||
    calendar.getUTCSeconds() !== second
  ) {
    return false
  }

  const zone = match[7]
  if (zone !== 'Z') {
    const offsetHour = Number(zone.slice(1, 3))
    const offsetMinute = Number(zone.slice(4, 6))
    if (offsetHour > 23 || offsetMinute > 59) return false
  }
  return !Number.isNaN(Date.parse(value))
}

function childPath(path: string, segment: string | number): string {
  const encoded = String(segment).replaceAll('~', '~0').replaceAll('/', '~1')
  return path === '/' ? `/${encoded}` : `${path}/${encoded}`
}

function pointer(document: unknown, fragment: string): unknown {
  let current = document
  if (!fragment) return current
  if (!fragment.startsWith('/')) throw new Error('unsupported_schema_pointer')
  for (const raw of fragment.slice(1).split('/')) {
    const key = raw.replaceAll('~1', '/').replaceAll('~0', '~')
    if (!isRecord(current) || !(key in current)) {
      throw new Error('unknown_schema_pointer')
    }
    current = current[key]
  }
  return current
}

function resolveSchemaRef(
  reference: string,
  rootSchema: JsonRecord,
): readonly [JsonRecord, JsonRecord] {
  if (reference.startsWith('#')) {
    const resolved = pointer(rootSchema, reference.slice(1))
    if (!isRecord(resolved)) throw new Error('invalid_schema_reference')
    return [resolved, rootSchema]
  }
  const hashIndex = reference.indexOf('#')
  const uri = hashIndex === -1 ? reference : reference.slice(0, hashIndex)
  const fragment = hashIndex === -1 ? '' : reference.slice(hashIndex + 1)
  const targetRoot = CONTRACT_SCHEMAS[uri]
  if (!isRecord(targetRoot)) throw new Error('unknown_schema_reference')
  const resolved = pointer(targetRoot, fragment)
  if (!isRecord(resolved)) throw new Error('invalid_schema_reference')
  return [resolved, targetRoot]
}

function matchesType(value: unknown, schemaType: string): boolean {
  if (schemaType === 'object') return isRecord(value)
  if (schemaType === 'array') return Array.isArray(value)
  if (schemaType === 'string') return typeof value === 'string'
  if (schemaType === 'integer') return Number.isSafeInteger(value)
  if (schemaType === 'number') {
    return typeof value === 'number' && Number.isFinite(value)
  }
  if (schemaType === 'boolean') return typeof value === 'boolean'
  if (schemaType === 'null') return value === null
  return true
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(item => canonicalJson(item)).join(',')}]`
  }
  if (isRecord(value)) {
    return `{${Object.keys(value)
      .sort()
      .map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(',')}}`
  }
  return JSON.stringify(value)
}

function collectViolations(
  value: unknown,
  schema: JsonRecord,
  rootSchema: JsonRecord,
  path: string,
  violations: Array<{ path: string; code: string }>,
  depth = 0,
): void {
  if (depth > 80) {
    violations.push({ path, code: 'schema_depth_exceeded' })
    return
  }

  const reference = schema.$ref
  if (typeof reference === 'string') {
    const [resolved, resolvedRoot] = resolveSchemaRef(reference, rootSchema)
    collectViolations(
      value,
      resolved,
      resolvedRoot,
      path,
      violations,
      depth + 1,
    )
    return
  }

  if ('const' in schema && !Object.is(value, schema.const)) {
    violations.push({ path, code: 'const' })
  }
  if (
    Array.isArray(schema.enum) &&
    !schema.enum.some(item => Object.is(value, item))
  ) {
    violations.push({ path, code: 'enum' })
  }

  if (Array.isArray(schema.oneOf)) {
    let matches = 0
    for (const option of schema.oneOf) {
      if (!isRecord(option)) continue
      const candidate: Array<{ path: string; code: string }> = []
      collectViolations(
        value,
        option,
        rootSchema,
        path,
        candidate,
        depth + 1,
      )
      if (candidate.length === 0) matches += 1
    }
    if (matches !== 1) violations.push({ path, code: 'oneOf' })
  }

  const schemaType = schema.type
  if (Array.isArray(schemaType)) {
    const allowedTypes = schemaType.filter(
      (item): item is string => typeof item === 'string',
    )
    if (!allowedTypes.some(item => matchesType(value, item))) {
      violations.push({ path, code: 'type' })
      return
    }
  } else if (
    typeof schemaType === 'string' &&
    !matchesType(value, schemaType)
  ) {
    violations.push({ path, code: 'type' })
    return
  }

  if (isRecord(value)) {
    const properties = isRecord(schema.properties) ? schema.properties : {}
    const required = Array.isArray(schema.required)
      ? schema.required.filter(
          (item): item is string => typeof item === 'string',
        )
      : []
    for (const key of required) {
      if (!(key in value)) {
        violations.push({ path: childPath(path, key), code: 'required' })
      }
    }
    if (schema.additionalProperties === false) {
      for (const key of Object.keys(value)) {
        if (!(key in properties)) {
          violations.push({
            path: childPath(path, key),
            code: 'additionalProperties',
          })
        }
      }
    } else if (isRecord(schema.additionalProperties)) {
      for (const [key, item] of Object.entries(value)) {
        if (!(key in properties)) {
          collectViolations(
            item,
            schema.additionalProperties,
            rootSchema,
            childPath(path, key),
            violations,
            depth + 1,
          )
        }
      }
    }
    for (const [key, child] of Object.entries(properties)) {
      if (key in value && isRecord(child)) {
        collectViolations(
          value[key],
          child,
          rootSchema,
          childPath(path, key),
          violations,
          depth + 1,
        )
      }
    }
  }

  if (Array.isArray(value)) {
    if (
      typeof schema.minItems === 'number' &&
      value.length < schema.minItems
    ) {
      violations.push({ path, code: 'minItems' })
    }
    if (
      typeof schema.maxItems === 'number' &&
      value.length > schema.maxItems
    ) {
      violations.push({ path, code: 'maxItems' })
    }
    if (schema.uniqueItems === true) {
      const encoded = value.map(item => canonicalJson(item))
      if (new Set(encoded).size !== encoded.length) {
        violations.push({ path, code: 'uniqueItems' })
      }
    }
    if (isRecord(schema.items)) {
      value.forEach((item, index) => {
        collectViolations(
          item,
          schema.items as JsonRecord,
          rootSchema,
          childPath(path, index),
          violations,
          depth + 1,
        )
      })
    }
  }

  if (typeof value === 'string') {
    if (
      typeof schema.minLength === 'number' &&
      value.length < schema.minLength
    ) {
      violations.push({ path, code: 'minLength' })
    }
    if (
      typeof schema.maxLength === 'number' &&
      value.length > schema.maxLength
    ) {
      violations.push({ path, code: 'maxLength' })
    }
    if (
      typeof schema.pattern === 'string' &&
      !new RegExp(schema.pattern).test(value)
    ) {
      violations.push({ path, code: 'pattern' })
    }
    if (
      schema.format === 'date-time' &&
      !isRfc3339DateTime(value)
    ) {
      violations.push({ path, code: 'format' })
    }
  }

  if (typeof value === 'number' && Number.isFinite(value)) {
    if (typeof schema.minimum === 'number' && value < schema.minimum) {
      violations.push({ path, code: 'minimum' })
    }
    if (typeof schema.maximum === 'number' && value > schema.maximum) {
      violations.push({ path, code: 'maximum' })
    }
  }

  if (Array.isArray(schema.allOf)) {
    for (const clause of schema.allOf) {
      if (isRecord(clause)) {
        collectViolations(
          value,
          clause,
          rootSchema,
          path,
          violations,
          depth + 1,
        )
      }
    }
  }

  if (isRecord(schema.if)) {
    const conditionViolations: Array<{ path: string; code: string }> = []
    collectViolations(
      value,
      schema.if,
      rootSchema,
      path,
      conditionViolations,
      depth + 1,
    )
    const branch = conditionViolations.length === 0 ? schema.then : schema.else
    if (isRecord(branch)) {
      collectViolations(
        value,
        branch,
        rootSchema,
        path,
        violations,
        depth + 1,
      )
    }
  }
}

export function validateContract(
  value: unknown,
  expectedSchemaId?: KolibriContractSchemaId,
): ContractValidationResult {
  const topLevel = validateContractTopLevel(value, expectedSchemaId)
  if (!topLevel.ok) return topLevel
  const record = value as Readonly<Record<string, unknown>>
  const schemaId = record.schema_id as keyof typeof CONTRACT_SPECS
  const spec = CONTRACT_SPECS[schemaId]
  const rootSchema = CONTRACT_SCHEMAS[spec.schema_uri]
  if (!isRecord(rootSchema)) {
    return {
      ok: false,
      code: 'unsupported_schema',
      violations: [{ path: '/schema_id', code: 'unsupported_schema' }],
    }
  }
  const violations: Array<{ path: string; code: string }> = []
  collectViolations(value, rootSchema, rootSchema, '/', violations)
  return {
    ok: violations.length === 0,
    code: violations.length === 0 ? null : 'invalid_contract',
    violations,
  }
}

export function parseContract(
  value: unknown,
  expectedSchemaId?: KolibriContractSchemaId,
): KolibriContractV1 {
  const result = validateContract(value, expectedSchemaId)
  if (!result.ok) {
    const error = new Error(result.code ?? 'contract_validation_failed')
    Object.assign(error, { contractValidation: result })
    throw error
  }
  return JSON.parse(JSON.stringify(value)) as KolibriContractV1
}

export class ContractBoundaryClient {
  readonly authorityRole: ContractAuthorityRole

  constructor(authorityRole: ContractAuthorityRole) {
    this.authorityRole = authorityRole
  }

  validateInbound(
    value: unknown,
    expectedSchemaId?: KolibriContractSchemaId,
  ): ContractValidationResult {
    return validateContract(value, expectedSchemaId)
  }

  prepareOutbound(
    value: unknown,
    expectedSchemaId?: KolibriContractSchemaId,
  ): KolibriContractV1 {
    return parseContract(value, expectedSchemaId)
  }
}
