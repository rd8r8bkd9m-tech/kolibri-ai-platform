use std::fs::File;
use std::io::Read;
use std::path::Path;
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::error::{ExecutorError, Result};
use crate::filesystem::{
    ScanSnapshot, capacity, capacity_segments, category_inventory, current_manifest,
    manifest_content_matches, manifest_for_entry, manifest_matches, remove_candidate,
    rename_candidate, root_entry_exists, scan,
};
use crate::guard_evidence::GuardEvidenceAssessment;
use crate::model::{
    CandidateManifest, CategoryInventory, CleanupCategory, Command, CommandResult, InventoryResult,
    OperationKind, OperationResult, OperationStatus, PreviewManifest, PreviewResult,
    QuarantineStatus, RootKind,
};
use crate::policy::{
    VerifiedPolicy, valid_opaque, valid_operation_id, valid_project_id, valid_quarantine_id,
};
use crate::store::{
    OperationClaim, PreviewRecord, QuarantineRecord, QuarantineTransition, StateStore,
};

pub trait Clock: Send + Sync {
    fn now(&self) -> u64;
}

#[derive(Debug, Default)]
pub struct SystemClock;

impl Clock for SystemClock {
    fn now(&self) -> u64 {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs()
    }
}

pub struct Engine {
    policy: VerifiedPolicy,
    store: StateStore,
    clock: Arc<dyn Clock>,
}

impl Engine {
    pub fn new(
        policy: VerifiedPolicy,
        state_db_path: &Path,
        clock: Arc<dyn Clock>,
    ) -> Result<Self> {
        Ok(Self {
            policy,
            store: StateStore::open(state_db_path)?,
            clock,
        })
    }

    pub fn with_system_clock(policy: VerifiedPolicy, state_db_path: &Path) -> Result<Self> {
        Self::new(policy, state_db_path, Arc::new(SystemClock))
    }

    #[cfg(test)]
    pub(crate) fn new_for_test(
        mut policy: VerifiedPolicy,
        state_db_path: &Path,
        clock: Arc<dyn Clock>,
    ) -> Result<Self> {
        policy.enable_test_execution();
        Self::new(policy, state_db_path, clock)
    }

    pub fn max_request_bytes(&self) -> u64 {
        self.policy.policy.limits.max_request_bytes
    }

    pub fn handle(&self, request_id: &str, command: &Command) -> Result<CommandResult> {
        if !valid_opaque(request_id, 3, 128) {
            return Err(ExecutorError::rejected(
                "request_id_invalid",
                "The request ID is invalid.",
            ));
        }
        match command {
            Command::Inventory { node_id } => {
                self.validate_node(node_id)?;
                Ok(CommandResult::Inventory(self.inventory()?))
            }
            Command::Preview {
                node_id,
                category,
                operation_kind,
                project_id,
                quarantine_id,
            } => {
                self.validate_node(node_id)?;
                Ok(CommandResult::Preview(self.preview(
                    request_id,
                    *category,
                    *operation_kind,
                    project_id.as_deref(),
                    quarantine_id.as_deref(),
                    command,
                )?))
            }
            Command::Execute {
                operation_id,
                preview_ref,
                node_generation,
                project_id,
                quarantine_id,
            } => Ok(CommandResult::Operation(self.execute(
                operation_id,
                preview_ref,
                node_generation,
                project_id.as_deref(),
                quarantine_id.as_deref(),
                command,
            )?)),
            Command::Status { operation_id } => {
                if !valid_operation_id(operation_id) {
                    return Err(ExecutorError::rejected(
                        "operation_id_invalid",
                        "The operation ID is invalid.",
                    ));
                }
                let mut operation = self.store.operation(operation_id)?.ok_or_else(|| {
                    ExecutorError::rejected(
                        "operation_not_found",
                        "The storage operation was not found.",
                    )
                })?;
                operation.replayed = true;
                Ok(CommandResult::Operation(operation))
            }
        }
    }

    fn validate_node(&self, node_id: &str) -> Result<()> {
        if node_id != self.policy.policy.node_id {
            return Err(ExecutorError::rejected(
                "node_mismatch",
                "The request targets another storage node.",
            ));
        }
        Ok(())
    }

    fn inventory(&self) -> Result<InventoryResult> {
        let now = self.clock.now();
        let (capacity_bytes, used_bytes, free_bytes) = capacity(&self.policy)?;
        let segments = capacity_segments(&self.policy)?;
        if self.policy.policy.node_id == "home" && segments.len() != 2 {
            return Err(ExecutorError::rejected(
                "capacity_topology_invalid",
                "Home requires live root-LV and VG-reserve segments.",
            ));
        }
        let evidence = self.policy.guard_evidence(now);
        if !evidence.authorizes_actions() {
            return Ok(InventoryResult {
                node_id: self.policy.policy.node_id.clone(),
                execute_enabled: false,
                capacity_bytes,
                used_bytes,
                free_bytes,
                scanned_at: now,
                generation: guard_unavailable_generation(&self.policy.digest),
                policy_digest: self.policy.digest.clone(),
                capacity_segments: segments,
                categories: empty_category_inventory(),
                project_candidates: Vec::new(),
                quarantines: self.store.quarantines()?,
                blocked_item_count: 0,
                guarded_scopes: Vec::new(),
            });
        }
        let snapshot = scan(&self.policy, &evidence, now)?;
        let categories = category_inventory(&snapshot);
        let blocked_item_count = snapshot.protected_item_count;
        Ok(InventoryResult {
            node_id: self.policy.policy.node_id.clone(),
            execute_enabled: self.policy.execution_authorized(),
            capacity_bytes,
            used_bytes,
            free_bytes,
            scanned_at: now,
            generation: snapshot.generation,
            policy_digest: self.policy.digest.clone(),
            capacity_segments: segments,
            categories,
            project_candidates: snapshot.projects,
            quarantines: self.store.quarantines()?,
            blocked_item_count,
            guarded_scopes: evidence.guarded_scopes(),
        })
    }

    #[allow(clippy::too_many_arguments)]
    fn preview(
        &self,
        request_id: &str,
        category: Option<CleanupCategory>,
        operation_kind: OperationKind,
        project_id: Option<&str>,
        quarantine_id: Option<&str>,
        command: &Command,
    ) -> Result<PreviewResult> {
        validate_preview_shape(operation_kind, category, project_id, quarantine_id)?;
        let evidence = self.action_guard_evidence(self.clock.now())?;
        let request_hash = digest_json(command)?;
        if let Some(existing) = self.store.preview_by_request(request_id)? {
            if existing.request_hash != request_hash {
                return Err(ExecutorError::rejected(
                    "preview_idempotency_conflict",
                    "The request ID was already used for another preview.",
                ));
            }
            return self.preview_result(&existing, &evidence, true);
        }

        let now = self.clock.now();
        let snapshot = scan(&self.policy, &evidence, now)?;
        let (manifest, node_generation) = self.build_preview_manifest(
            snapshot,
            operation_kind,
            category,
            project_id,
            quarantine_id,
            now,
        )?;
        enforce_manifest_limits(&self.policy, &manifest)?;
        let preview_ref = new_opaque("spx")?;
        let record = PreviewRecord {
            preview_ref,
            request_id: request_id.to_owned(),
            request_hash,
            node_generation,
            policy_digest: self.policy.digest.clone(),
            expires_at: now + self.policy.policy.preview_ttl_seconds,
            manifest_json: serde_json::to_string(&manifest)?,
            created_at: now,
        };
        self.store.insert_preview(&record)?;
        self.preview_result(&record, &evidence, false)
    }

    fn build_preview_manifest(
        &self,
        snapshot: ScanSnapshot,
        operation_kind: OperationKind,
        category: Option<CleanupCategory>,
        project_id: Option<&str>,
        quarantine_id: Option<&str>,
        now: u64,
    ) -> Result<(PreviewManifest, String)> {
        match operation_kind {
            OperationKind::Cleanup => {
                let category = category.expect("preview shape validated");
                let candidates = snapshot
                    .candidates
                    .get(&category)
                    .cloned()
                    .unwrap_or_default();
                Ok((
                    PreviewManifest {
                        operation_kind,
                        category: Some(category),
                        project_id: None,
                        quarantine_id: None,
                        candidates,
                        protected_item_count: 0,
                    },
                    snapshot.generation,
                ))
            }
            OperationKind::Quarantine => {
                let project_id = project_id.expect("preview shape validated");
                let candidate = snapshot
                    .project_manifests
                    .get(project_id)
                    .cloned()
                    .ok_or_else(|| {
                        ExecutorError::rejected(
                            "project_not_actionable",
                            "The project is not an actionable allowlisted candidate.",
                        )
                    })?;
                let quarantine_root = self.single_root(RootKind::ProjectQuarantine)?;
                if root_entry_exists(&self.policy, &quarantine_root.root_id, project_id)? {
                    return Err(ExecutorError::rejected(
                        "quarantine_target_conflict",
                        "The quarantine destination already exists.",
                    ));
                }
                Ok((
                    PreviewManifest {
                        operation_kind,
                        category: None,
                        project_id: Some(project_id.to_owned()),
                        quarantine_id: None,
                        candidates: vec![candidate],
                        protected_item_count: 0,
                    },
                    snapshot.generation,
                ))
            }
            OperationKind::Restore | OperationKind::Purge => {
                let quarantine_id = quarantine_id.expect("preview shape validated");
                let record = self.store.quarantine(quarantine_id)?.ok_or_else(|| {
                    ExecutorError::rejected(
                        "quarantine_not_found",
                        "The quarantine record was not found.",
                    )
                })?;
                if record.status != QuarantineStatus::Retained {
                    return Err(ExecutorError::rejected(
                        "quarantine_state_conflict",
                        "The quarantine is not retained.",
                    ));
                }
                if operation_kind == OperationKind::Purge && now < record.purge_eligible_at {
                    return Err(ExecutorError::rejected(
                        "quarantine_retention_active",
                        "The quarantine retention period has not elapsed.",
                    ));
                }
                let candidate =
                    manifest_for_entry(&self.policy, &record.quarantine_root_id, quarantine_id)?
                        .ok_or_else(|| {
                            ExecutorError::rejected(
                                "quarantine_content_missing",
                                "The quarantined project is missing.",
                            )
                        })?;
                if operation_kind == OperationKind::Restore
                    && root_entry_exists(&self.policy, &record.source_root_id, &record.project_id)?
                {
                    return Err(ExecutorError::rejected(
                        "restore_target_conflict",
                        "The original project destination already exists.",
                    ));
                }
                let generation = generation_with_candidate(&snapshot.generation, &candidate);
                Ok((
                    PreviewManifest {
                        operation_kind,
                        category: None,
                        project_id: Some(record.project_id),
                        quarantine_id: Some(quarantine_id.to_owned()),
                        candidates: vec![candidate],
                        protected_item_count: 0,
                    },
                    generation,
                ))
            }
        }
    }

    fn preview_result(
        &self,
        record: &PreviewRecord,
        evidence: &GuardEvidenceAssessment,
        replayed: bool,
    ) -> Result<PreviewResult> {
        let manifest: PreviewManifest = serde_json::from_str(&record.manifest_json)?;
        Ok(PreviewResult {
            executor_preview_ref: record.preview_ref.clone(),
            node_generation: record.node_generation.clone(),
            candidate_count: manifest.candidates.len() as u64,
            reclaimable_bytes: manifest
                .candidates
                .iter()
                .map(|candidate| candidate.size_bytes)
                .sum(),
            protected_item_count: manifest.protected_item_count,
            guarded_scopes: evidence.guarded_scopes(),
            confirmation: manifest.operation_kind.confirmation(),
            expires_at: record.expires_at,
            replayed,
        })
    }

    #[allow(clippy::too_many_arguments)]
    fn execute(
        &self,
        operation_id: &str,
        preview_ref: &str,
        node_generation: &str,
        project_id: Option<&str>,
        quarantine_id: Option<&str>,
        command: &Command,
    ) -> Result<OperationResult> {
        self.action_guard_evidence(self.clock.now())?;
        if !self.policy.execution_authorized() {
            return Err(ExecutorError::rejected(
                "execution_disabled",
                "Storage execution is disabled by signed policy.",
            ));
        }
        if !valid_operation_id(operation_id)
            || !valid_opaque(preview_ref, 3, 128)
            || !valid_opaque(node_generation, 3, 128)
        {
            return Err(ExecutorError::rejected(
                "execute_request_invalid",
                "The execute request is invalid.",
            ));
        }
        let request_hash = digest_json(command)?;
        if let Some(mut existing) = self.store.operation(operation_id)? {
            let claim = self.store.claim_operation(
                operation_id,
                preview_ref,
                &request_hash,
                existing.quarantine_id.as_deref(),
                self.clock.now(),
            )?;
            existing = match claim {
                OperationClaim::Existing(operation) | OperationClaim::New(operation) => operation,
            };
            if existing.status != OperationStatus::Applying {
                existing.replayed = true;
                return Ok(existing);
            }
            return self.resume_apply(existing, project_id, quarantine_id, true);
        }

        let preview = self.store.preview_by_ref(preview_ref)?.ok_or_else(|| {
            ExecutorError::rejected("preview_not_found", "The executor preview was not found.")
        })?;
        let now = self.clock.now();
        if preview.expires_at < now {
            return Err(ExecutorError::rejected(
                "preview_expired",
                "The executor preview expired.",
            ));
        }
        if preview.policy_digest != self.policy.digest {
            return Err(ExecutorError::rejected(
                "policy_changed",
                "The signed policy changed after preview.",
            ));
        }
        if preview.node_generation != node_generation {
            return Err(ExecutorError::rejected(
                "generation_mismatch",
                "The execute generation does not match preview.",
            ));
        }
        let manifest: PreviewManifest = serde_json::from_str(&preview.manifest_json)?;
        if manifest.candidates.is_empty() {
            return Err(ExecutorError::rejected(
                "preview_empty",
                "The executor preview has no actionable candidates.",
            ));
        }
        validate_execute_ids(&manifest, project_id, quarantine_id)?;
        self.preflight_manifest(&manifest, &preview.node_generation, now)?;
        let claimed_quarantine = match manifest.operation_kind {
            OperationKind::Quarantine => quarantine_id,
            OperationKind::Restore | OperationKind::Purge => manifest.quarantine_id.as_deref(),
            OperationKind::Cleanup => None,
        };
        let operation = match self.store.claim_operation(
            operation_id,
            preview_ref,
            &request_hash,
            claimed_quarantine,
            now,
        )? {
            OperationClaim::New(operation) => operation,
            OperationClaim::Existing(mut operation) => {
                if operation.status != OperationStatus::Applying {
                    operation.replayed = true;
                    return Ok(operation);
                }
                operation
            }
        };
        self.resume_apply(operation, project_id, quarantine_id, false)
    }

    fn preflight_manifest(
        &self,
        manifest: &PreviewManifest,
        expected_generation: &str,
        now: u64,
    ) -> Result<()> {
        if manifest.operation_kind == OperationKind::Restore {
            let quarantine_id = manifest.quarantine_id.as_deref().ok_or_else(|| {
                ExecutorError::rejected("quarantine_id_missing", "The quarantine ID is missing.")
            })?;
            let record = self.store.quarantine(quarantine_id)?.ok_or_else(|| {
                ExecutorError::rejected(
                    "quarantine_not_found",
                    "The quarantine record was not found.",
                )
            })?;
            if root_entry_exists(&self.policy, &record.source_root_id, &record.project_id)? {
                return Err(ExecutorError::rejected(
                    "restore_target_conflict",
                    "The original project destination already exists.",
                ));
            }
        }
        let evidence = self.action_guard_evidence(now)?;
        let snapshot = scan(&self.policy, &evidence, now)?;
        let current_generation = match manifest.operation_kind {
            OperationKind::Restore | OperationKind::Purge => {
                let candidate = manifest.candidates.first().ok_or_else(|| {
                    ExecutorError::rejected("preview_empty", "The executor preview is empty.")
                })?;
                let current = current_manifest(&self.policy, candidate)?.ok_or_else(|| {
                    ExecutorError::rejected(
                        "candidate_missing",
                        "A preview candidate no longer exists.",
                    )
                })?;
                if !manifest_matches(candidate, &current) {
                    return Err(ExecutorError::rejected(
                        "candidate_changed",
                        "A preview candidate changed.",
                    ));
                }
                generation_with_candidate(&snapshot.generation, &current)
            }
            OperationKind::Cleanup | OperationKind::Quarantine => {
                for candidate in &manifest.candidates {
                    let current = current_manifest(&self.policy, candidate)?.ok_or_else(|| {
                        ExecutorError::rejected(
                            "candidate_missing",
                            "A preview candidate no longer exists.",
                        )
                    })?;
                    if !manifest_matches(candidate, &current) {
                        return Err(ExecutorError::rejected(
                            "candidate_changed",
                            "A preview candidate changed.",
                        ));
                    }
                }
                snapshot.generation
            }
        };
        if current_generation != expected_generation {
            return Err(ExecutorError::rejected(
                "generation_changed",
                "Node storage changed after preview.",
            ));
        }
        Ok(())
    }

    fn resume_apply(
        &self,
        operation: OperationResult,
        execute_project_id: Option<&str>,
        execute_quarantine_id: Option<&str>,
        replayed: bool,
    ) -> Result<OperationResult> {
        let _execution_lock = self.store.acquire_execution_lock()?;
        let preview = self
            .store
            .preview_by_ref(&operation.preview_ref)?
            .ok_or_else(|| {
                ExecutorError::incomplete(
                    "operation_preview_missing",
                    "The applying operation lost its durable preview.",
                )
            })?;
        let manifest: PreviewManifest = serde_json::from_str(&preview.manifest_json)?;
        let result = match manifest.operation_kind {
            OperationKind::Cleanup => self.apply_cleanup(&manifest, &operation.operation_id),
            OperationKind::Quarantine => self.apply_quarantine(
                &manifest,
                execute_project_id,
                execute_quarantine_id.or(operation.quarantine_id.as_deref()),
            ),
            OperationKind::Restore => self.apply_restore(&manifest),
            OperationKind::Purge => self.apply_purge(&manifest, &operation.operation_id),
        };
        match result {
            Ok((affected, reclaimed, quarantine_id)) => {
                let node_generation = match self
                    .action_guard_evidence(self.clock.now())
                    .and_then(|evidence| scan(&self.policy, &evidence, self.clock.now()))
                {
                    Ok(snapshot) => snapshot.generation,
                    Err(error) => {
                        self.store.record_incomplete(
                            &operation.operation_id,
                            error.code(),
                            self.clock.now(),
                        )?;
                        return Err(ExecutorError::incomplete(
                            "operation_incomplete",
                            "The operation applied but post-operation inventory is pending.",
                        ));
                    }
                };
                let transition = match manifest.operation_kind {
                    OperationKind::Restore => Some(QuarantineTransition {
                        quarantine_id: manifest
                            .quarantine_id
                            .clone()
                            .expect("restore has quarantine ID"),
                        expected: QuarantineStatus::Retained,
                        target: QuarantineStatus::Restored,
                    }),
                    OperationKind::Purge => Some(QuarantineTransition {
                        quarantine_id: manifest
                            .quarantine_id
                            .clone()
                            .expect("purge has quarantine ID"),
                        expected: QuarantineStatus::Retained,
                        target: QuarantineStatus::Purged,
                    }),
                    OperationKind::Cleanup | OperationKind::Quarantine => None,
                };
                let mut completed = self.store.complete_operation(
                    &operation.operation_id,
                    affected,
                    reclaimed,
                    quarantine_id.as_deref(),
                    transition.as_ref(),
                    &node_generation,
                    &self
                        .policy
                        .guard_evidence(self.clock.now())
                        .guarded_scopes(),
                    self.clock.now(),
                )?;
                completed.replayed = replayed;
                Ok(completed)
            }
            Err(error) => {
                self.store.record_incomplete(
                    &operation.operation_id,
                    error.code(),
                    self.clock.now(),
                )?;
                Err(ExecutorError::incomplete(
                    "operation_incomplete",
                    "The operation remains applying; retry execute or query status.",
                ))
            }
        }
    }

    fn apply_cleanup(
        &self,
        manifest: &PreviewManifest,
        operation_id: &str,
    ) -> Result<(u64, u64, Option<String>)> {
        let suffix = operation_id.strip_prefix("sop_").unwrap_or(operation_id);
        for (index, candidate) in manifest.candidates.iter().enumerate() {
            match current_manifest(&self.policy, candidate)? {
                None => {}
                Some(current) if manifest_matches(candidate, &current) => {}
                Some(_) => {
                    return Err(ExecutorError::incomplete(
                        "candidate_changed_during_apply",
                        "A candidate changed while the operation was applying.",
                    ));
                }
            }
            remove_candidate(&self.policy, candidate, &format!("del_{suffix}_{index}"))?;
        }
        Ok((
            manifest.candidates.len() as u64,
            manifest
                .candidates
                .iter()
                .map(|candidate| candidate.size_bytes)
                .sum(),
            None,
        ))
    }

    fn apply_quarantine(
        &self,
        manifest: &PreviewManifest,
        execute_project_id: Option<&str>,
        execute_quarantine_id: Option<&str>,
    ) -> Result<(u64, u64, Option<String>)> {
        let project_id = manifest.project_id.as_deref().ok_or_else(|| {
            ExecutorError::rejected("project_id_missing", "The project ID is missing.")
        })?;
        if execute_project_id != Some(project_id) {
            return Err(ExecutorError::rejected(
                "project_id_mismatch",
                "The execute project ID does not match preview.",
            ));
        }
        let quarantine_id = execute_quarantine_id
            .filter(|value| valid_quarantine_id(value))
            .ok_or_else(|| {
                ExecutorError::rejected("quarantine_id_invalid", "The quarantine ID is invalid.")
            })?;
        let source = manifest.candidates.first().ok_or_else(|| {
            ExecutorError::rejected("preview_empty", "The executor preview is empty.")
        })?;
        let quarantine_root = self.single_root(RootKind::ProjectQuarantine)?;
        let source_exists = root_entry_exists(&self.policy, &source.root_id, project_id)?;
        let destination =
            manifest_for_entry(&self.policy, &quarantine_root.root_id, quarantine_id)?;
        let existing_record = self.store.quarantine(quarantine_id)?;
        if let Some(existing) = &existing_record {
            let exact_record = existing.project_id == project_id
                && existing.source_root_id == source.root_id
                && existing.quarantine_root_id == quarantine_root.root_id
                && existing.size_bytes == source.size_bytes
                && existing.status == QuarantineStatus::Retained;
            let exact_destination = !source_exists
                && destination
                    .as_ref()
                    .is_some_and(|item| manifest_content_matches(source, item));
            if !exact_record || !exact_destination {
                return Err(ExecutorError::incomplete(
                    "quarantine_id_collision",
                    "The quarantine ID is already bound to another record.",
                ));
            }
        }
        match (source_exists, destination.as_ref()) {
            (true, None) if existing_record.is_none() => {
                let current = current_manifest(&self.policy, source)?.ok_or_else(|| {
                    ExecutorError::incomplete(
                        "candidate_disappeared",
                        "The project candidate disappeared during apply.",
                    )
                })?;
                if !manifest_matches(source, &current) {
                    return Err(ExecutorError::incomplete(
                        "candidate_changed_during_apply",
                        "The project candidate changed during apply.",
                    ));
                }
                rename_candidate(
                    &self.policy,
                    source,
                    &quarantine_root.root_id,
                    quarantine_id,
                )?
            }
            (false, Some(destination)) if manifest_content_matches(source, destination) => {}
            (true, Some(_)) => {
                return Err(ExecutorError::rejected(
                    "quarantine_target_conflict",
                    "Both project and quarantine destinations exist.",
                ));
            }
            _ => {
                return Err(ExecutorError::incomplete(
                    "quarantine_state_ambiguous",
                    "The project quarantine state is ambiguous.",
                ));
            }
        }
        let now = self.clock.now();
        self.store.put_quarantine(&QuarantineRecord {
            quarantine_id: quarantine_id.to_owned(),
            project_id: project_id.to_owned(),
            source_root_id: source.root_id.clone(),
            quarantine_root_id: quarantine_root.root_id.clone(),
            size_bytes: source.size_bytes,
            quarantined_at: now,
            purge_eligible_at: now + self.policy.policy.quarantine_retention_seconds,
            status: QuarantineStatus::Retained,
        })?;
        Ok((1, 0, Some(quarantine_id.to_owned())))
    }

    fn apply_restore(&self, manifest: &PreviewManifest) -> Result<(u64, u64, Option<String>)> {
        let quarantine_id = manifest.quarantine_id.as_deref().ok_or_else(|| {
            ExecutorError::rejected("quarantine_id_missing", "The quarantine ID is missing.")
        })?;
        let record = self.store.quarantine(quarantine_id)?.ok_or_else(|| {
            ExecutorError::rejected(
                "quarantine_not_found",
                "The quarantine record was not found.",
            )
        })?;
        let candidate = manifest.candidates.first().ok_or_else(|| {
            ExecutorError::rejected("preview_empty", "The executor preview is empty.")
        })?;
        let quarantined =
            manifest_for_entry(&self.policy, &record.quarantine_root_id, quarantine_id)?;
        let source = manifest_for_entry(&self.policy, &record.source_root_id, &record.project_id)?;
        if record.status == QuarantineStatus::Restored {
            return match (quarantined, source) {
                (None, Some(restored)) if manifest_content_matches(candidate, &restored) => {
                    Ok((1, 0, Some(quarantine_id.to_owned())))
                }
                _ => Err(ExecutorError::incomplete(
                    "restore_state_ambiguous",
                    "The restored project cannot be reconciled.",
                )),
            };
        }
        if record.status != QuarantineStatus::Retained {
            return Err(ExecutorError::incomplete(
                "quarantine_state_conflict",
                "The quarantine is not retained.",
            ));
        }
        match (quarantined.as_ref(), source.as_ref()) {
            (Some(quarantined), None) if manifest_matches(candidate, quarantined) => {
                rename_candidate(
                    &self.policy,
                    candidate,
                    &record.source_root_id,
                    &record.project_id,
                )?;
            }
            (None, Some(restored)) if manifest_content_matches(candidate, restored) => {}
            (Some(_), Some(_)) => {
                return Err(ExecutorError::rejected(
                    "restore_target_conflict",
                    "The original project destination already exists.",
                ));
            }
            _ => {
                return Err(ExecutorError::incomplete(
                    "restore_state_ambiguous",
                    "The project restore state is ambiguous.",
                ));
            }
        }
        Ok((1, 0, Some(quarantine_id.to_owned())))
    }

    fn apply_purge(
        &self,
        manifest: &PreviewManifest,
        operation_id: &str,
    ) -> Result<(u64, u64, Option<String>)> {
        let quarantine_id = manifest.quarantine_id.as_deref().ok_or_else(|| {
            ExecutorError::rejected("quarantine_id_missing", "The quarantine ID is missing.")
        })?;
        let record = self.store.quarantine(quarantine_id)?.ok_or_else(|| {
            ExecutorError::rejected(
                "quarantine_not_found",
                "The quarantine record was not found.",
            )
        })?;
        let candidate = manifest.candidates.first().ok_or_else(|| {
            ExecutorError::rejected("preview_empty", "The executor preview is empty.")
        })?;
        if record.status == QuarantineStatus::Purged {
            if manifest_for_entry(&self.policy, &record.quarantine_root_id, quarantine_id)?
                .is_none()
            {
                return Ok((1, candidate.size_bytes, Some(quarantine_id.to_owned())));
            }
            return Err(ExecutorError::incomplete(
                "purge_state_ambiguous",
                "The purged project still exists.",
            ));
        }
        if record.status != QuarantineStatus::Retained {
            return Err(ExecutorError::incomplete(
                "quarantine_state_conflict",
                "The quarantine is not retained.",
            ));
        }
        if self.clock.now() < record.purge_eligible_at {
            return Err(ExecutorError::incomplete(
                "quarantine_retention_active",
                "The quarantine retention period has not elapsed.",
            ));
        }
        if let Some(current) = current_manifest(&self.policy, candidate)? {
            if !manifest_matches(candidate, &current) {
                return Err(ExecutorError::incomplete(
                    "quarantine_changed_during_purge",
                    "The quarantine changed while purge was applying.",
                ));
            }
        }
        let suffix = operation_id.strip_prefix("sop_").unwrap_or(operation_id);
        remove_candidate(&self.policy, candidate, &format!("del_{suffix}_0"))?;
        Ok((1, candidate.size_bytes, Some(quarantine_id.to_owned())))
    }

    fn single_root(&self, kind: RootKind) -> Result<&crate::policy::RootPolicy> {
        let mut roots = self.policy.roots_of_kind(kind);
        let root = roots.next().ok_or_else(|| {
            ExecutorError::rejected(
                "project_roots_unavailable",
                "Project lifecycle roots are not configured.",
            )
        })?;
        if roots.next().is_some() {
            return Err(ExecutorError::rejected(
                "policy_invalid",
                "Project lifecycle roots are ambiguous.",
            ));
        }
        Ok(root)
    }

    fn action_guard_evidence(&self, now: u64) -> Result<GuardEvidenceAssessment> {
        let evidence = self.policy.guard_evidence(now);
        if !evidence.authorizes_actions() {
            return Err(ExecutorError::rejected(
                "guard_evidence_unavailable",
                "Exhaustive live guard evidence is unavailable.",
            ));
        }
        Ok(evidence)
    }
}

fn empty_category_inventory() -> Vec<CategoryInventory> {
    [
        CleanupCategory::Build,
        CleanupCategory::Cache,
        CleanupCategory::Log,
        CleanupCategory::StoppedContainer,
    ]
    .into_iter()
    .map(|category| CategoryInventory {
        category,
        reclaimable_bytes: 0,
        item_count: 0,
        oldest_item_at: None,
    })
    .collect()
}

fn guard_unavailable_generation(policy_digest: &str) -> String {
    format!(
        "gen_{}",
        hex::encode(Sha256::digest(
            format!("{policy_digest}:guard-evidence-unavailable").as_bytes()
        ))
    )
}

fn validate_preview_shape(
    operation_kind: OperationKind,
    category: Option<CleanupCategory>,
    project_id: Option<&str>,
    quarantine_id: Option<&str>,
) -> Result<()> {
    let valid = match operation_kind {
        OperationKind::Cleanup => {
            category.is_some() && project_id.is_none() && quarantine_id.is_none()
        }
        OperationKind::Quarantine => {
            category.is_none()
                && project_id.is_some_and(valid_project_id)
                && quarantine_id.is_none()
        }
        OperationKind::Restore | OperationKind::Purge => {
            category.is_none()
                && project_id.is_none()
                && quarantine_id.is_some_and(valid_quarantine_id)
        }
    };
    if valid {
        Ok(())
    } else {
        Err(ExecutorError::rejected(
            "preview_shape_invalid",
            "The preview command shape is invalid.",
        ))
    }
}

fn validate_execute_ids(
    manifest: &PreviewManifest,
    project_id: Option<&str>,
    quarantine_id: Option<&str>,
) -> Result<()> {
    let valid = match manifest.operation_kind {
        OperationKind::Cleanup => project_id.is_none() && quarantine_id.is_none(),
        OperationKind::Quarantine => {
            project_id == manifest.project_id.as_deref()
                && quarantine_id.is_some_and(valid_quarantine_id)
        }
        OperationKind::Restore | OperationKind::Purge => {
            project_id.is_none() && quarantine_id == manifest.quarantine_id.as_deref()
        }
    };
    if valid {
        Ok(())
    } else {
        Err(ExecutorError::rejected(
            "execute_binding_invalid",
            "The execute IDs do not match the durable preview.",
        ))
    }
}

fn enforce_manifest_limits(policy: &VerifiedPolicy, manifest: &PreviewManifest) -> Result<()> {
    let count = manifest.candidates.len() as u64;
    let bytes = manifest
        .candidates
        .iter()
        .try_fold(0_u64, |total, item| total.checked_add(item.size_bytes))
        .ok_or_else(limit_exceeded)?;
    if count > policy.policy.limits.max_candidates
        || bytes > policy.policy.limits.max_bytes_per_operation
    {
        return Err(limit_exceeded());
    }
    Ok(())
}

fn generation_with_candidate(base: &str, candidate: &CandidateManifest) -> String {
    let mut hasher = Sha256::new();
    hasher.update(base.as_bytes());
    hasher.update(candidate.root_id.as_bytes());
    hasher.update(candidate.relative_name.as_bytes());
    hasher.update(candidate.tree_digest.as_bytes());
    format!("gen_{}", hex::encode(hasher.finalize()))
}

fn digest_json(value: &impl Serialize) -> Result<String> {
    Ok(hex::encode(Sha256::digest(serde_json::to_vec(value)?)))
}

fn new_opaque(prefix: &str) -> Result<String> {
    let mut random = [0_u8; 32];
    File::open("/dev/urandom")?.read_exact(&mut random)?;
    Ok(format!("{prefix}_{}", &hex::encode(random)[..32]))
}

fn limit_exceeded() -> ExecutorError {
    ExecutorError::rejected(
        "storage_limit_exceeded",
        "The storage operation exceeds a configured hard limit.",
    )
}
