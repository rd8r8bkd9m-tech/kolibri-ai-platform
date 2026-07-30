use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::os::unix::fs::symlink;
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

use crate::{
    CleanupCategory, Clock, Command, CommandResult, DockerEvidencePolicy, Engine,
    EvidenceFilePolicy, FileEvidencePolicy, GuardEvidencePolicy, GuardPolicy, Limits,
    OperationKind, OperationStatus, Policy, ProtectionScope, RootKind, RootPolicy, SignedPolicy,
    VerifiedPolicy,
};
use ed25519_dalek::{Signer, SigningKey};
use rusqlite::Connection;
use sha2::{Digest, Sha256};
use tempfile::TempDir;

const RETENTION: u64 = 7 * 24 * 60 * 60;

struct ManualClock(AtomicU64);

impl ManualClock {
    fn new(now: u64) -> Self {
        Self(AtomicU64::new(now))
    }

    fn advance(&self, seconds: u64) {
        self.0.fetch_add(seconds, Ordering::SeqCst);
    }
}

impl Clock for ManualClock {
    fn now(&self) -> u64 {
        self.0.load(Ordering::SeqCst)
    }
}

struct Fixture {
    _temp: TempDir,
    cache: PathBuf,
    projects: PathBuf,
    quarantine: PathBuf,
    engine: Engine,
    clock: Arc<ManualClock>,
    state_db: PathBuf,
}

impl Fixture {
    fn new(execute_enabled: bool) -> Self {
        Self::build(execute_enabled, None, true)
    }

    fn new_with_guard_evidence(
        execute_enabled: bool,
        guard_evidence: Option<GuardEvidencePolicy>,
    ) -> Self {
        Self::build(execute_enabled, guard_evidence, false)
    }

    fn new_without_test_execution(execute_enabled: bool) -> Self {
        Self::build(execute_enabled, None, false)
    }

    fn build(
        execute_enabled: bool,
        guard_evidence: Option<GuardEvidencePolicy>,
        test_execution: bool,
    ) -> Self {
        let temp = TempDir::new().unwrap();
        let base = fs::canonicalize(temp.path()).unwrap();
        let cache = base.join("cache");
        let projects = base.join("projects");
        let quarantine = base.join("quarantine");
        fs::create_dir(&cache).unwrap();
        fs::create_dir(&projects).unwrap();
        fs::create_dir(&quarantine).unwrap();
        for root in [&cache, &projects, &quarantine] {
            let trash = root.join(".kolibri-storage-trash");
            fs::create_dir(&trash).unwrap();
            fs::set_permissions(&trash, fs::Permissions::from_mode(0o700)).unwrap();
        }
        let policy = Policy {
            policy_version: "policy-test-1".into(),
            protocol_version: "v1".into(),
            node_id: "primary".into(),
            execute_enabled,
            preview_ttl_seconds: 900,
            quarantine_retention_seconds: RETENTION,
            limits: Limits {
                max_candidates: 100,
                max_bytes_per_operation: 100 * 1024 * 1024,
                max_scan_entries: 10_000,
                max_scan_depth: 32,
                max_request_bytes: 64 * 1024,
            },
            capacity_topology: None,
            guard_evidence,
            roots: vec![
                RootPolicy {
                    root_id: "cache-main".into(),
                    kind: RootKind::Cache,
                    path: cache.clone(),
                    minimum_age_seconds: 0,
                },
                RootPolicy {
                    root_id: "project-source".into(),
                    kind: RootKind::ProjectSource,
                    path: projects.clone(),
                    minimum_age_seconds: 0,
                },
                RootPolicy {
                    root_id: "project-quarantine".into(),
                    kind: RootKind::ProjectQuarantine,
                    path: quarantine.clone(),
                    minimum_age_seconds: 0,
                },
            ],
            guards: [
                ProtectionScope::ActiveRelease,
                ProtectionScope::CurrentSymlink,
                ProtectionScope::PrimaryDatabase,
                ProtectionScope::DurableVolumes,
                ProtectionScope::AgentRuntimeState,
            ]
            .into_iter()
            .map(|scope| GuardPolicy {
                scope,
                paths: {
                    let path = base.join(format!("protected-{scope:?}"));
                    fs::create_dir(&path).unwrap();
                    vec![path]
                },
            })
            .collect(),
        };
        let signing_key = SigningKey::from_bytes(&[17_u8; 32]);
        let signature = signing_key.sign(&serde_json::to_vec(&policy).unwrap());
        let verified = VerifiedPolicy::verify(
            SignedPolicy {
                policy,
                signature_hex: hex::encode(signature.to_bytes()),
            },
            &hex::encode(signing_key.verifying_key().to_bytes()),
        )
        .unwrap();
        let clock = Arc::new(ManualClock::new(1_800_000_000));
        let state_db = temp.path().join("executor.db");
        let engine = if test_execution {
            Engine::new_for_test(verified, &state_db, clock.clone()).unwrap()
        } else {
            Engine::new(verified, &state_db, clock.clone()).unwrap()
        };
        Self {
            _temp: temp,
            cache,
            projects,
            quarantine,
            engine,
            clock,
            state_db,
        }
    }

    fn preview_cleanup(&self, request_id: &str) -> crate::PreviewResult {
        match self
            .engine
            .handle(
                request_id,
                &Command::Preview {
                    node_id: "primary".into(),
                    category: Some(CleanupCategory::Cache),
                    operation_kind: OperationKind::Cleanup,
                    project_id: None,
                    quarantine_id: None,
                },
            )
            .unwrap()
        {
            CommandResult::Preview(result) => result,
            _ => panic!("expected preview"),
        }
    }

    fn quarantine_project(
        &self,
        project_id: &str,
        request_suffix: &str,
        operation_hex: char,
        quarantine_hex: char,
    ) -> String {
        let preview = match self
            .engine
            .handle(
                &format!("preview-quarantine-{request_suffix}"),
                &Command::Preview {
                    node_id: "primary".into(),
                    category: None,
                    operation_kind: OperationKind::Quarantine,
                    project_id: Some(project_id.into()),
                    quarantine_id: None,
                },
            )
            .unwrap()
        {
            CommandResult::Preview(result) => result,
            _ => panic!("expected preview"),
        };
        let quarantine_id = format!("sqn_{}", quarantine_hex.to_string().repeat(32));
        let command = Command::Execute {
            operation_id: format!("sop_{}", operation_hex.to_string().repeat(32)),
            preview_ref: preview.executor_preview_ref,
            node_generation: preview.node_generation,
            project_id: Some(project_id.into()),
            quarantine_id: Some(quarantine_id.clone()),
        };
        let operation = match self
            .engine
            .handle(&format!("execute-quarantine-{request_suffix}"), &command)
            .unwrap()
        {
            CommandResult::Operation(result) => result,
            _ => panic!("expected operation"),
        };
        assert_eq!(operation.status, OperationStatus::Succeeded);
        quarantine_id
    }
}

fn unavailable_guard_evidence() -> GuardEvidencePolicy {
    let file = |name: &str| EvidenceFilePolicy {
        path: PathBuf::from(format!("/evidence-intentionally-unavailable/{name}")),
        sha256: "0".repeat(64),
    };
    let provider = |name: &str| FileEvidencePolicy {
        generation: format!("{name}-generation-1"),
        files: vec![file(name)],
    };
    GuardEvidencePolicy {
        max_file_bytes: 64 * 1024,
        max_total_bytes: 512 * 1024,
        docker_snapshot_max_age_seconds: 300,
        systemd: provider("systemd"),
        nginx: provider("nginx"),
        cron: provider("cron"),
        compose: provider("compose"),
        docker: DockerEvidencePolicy {
            generation: "docker-generation-1".into(),
            daemon_identity: "daemon-primary-1".into(),
            metadata: file("docker"),
        },
    }
}

fn insert_applying_operation(fixture: &Fixture, command: &Command, quarantine_id: Option<&str>) {
    let Command::Execute {
        operation_id,
        preview_ref,
        ..
    } = command
    else {
        panic!("expected execute command");
    };
    let request_hash = hex::encode(Sha256::digest(serde_json::to_vec(command).unwrap()));
    let connection = Connection::open(&fixture.state_db).unwrap();
    connection
        .execute(
            "INSERT INTO operations (
                 operation_id, preview_ref, request_hash, status,
                 quarantine_id, created_at
             ) VALUES (?, ?, ?, 'applying', ?, ?)",
            (
                operation_id,
                preview_ref,
                &request_hash,
                quarantine_id,
                1_800_000_000_i64,
            ),
        )
        .unwrap();
}

#[test]
fn applying_quarantine_revalidates_manifest_before_crash_retry() {
    let fixture = Fixture::new(true);
    fs::create_dir(fixture.projects.join("project-crash")).unwrap();
    fs::write(fixture.projects.join("project-crash/data"), b"initial").unwrap();
    let preview = match fixture
        .engine
        .handle(
            "preview-quarantine-crash",
            &Command::Preview {
                node_id: "primary".into(),
                category: None,
                operation_kind: OperationKind::Quarantine,
                project_id: Some("project-crash".into()),
                quarantine_id: None,
            },
        )
        .unwrap()
    {
        CommandResult::Preview(result) => result,
        _ => panic!("expected preview"),
    };
    let quarantine_id = format!("sqn_{}", "c".repeat(32));
    let operation_id = format!("sop_{}", "9".repeat(32));
    let command = Command::Execute {
        operation_id: operation_id.clone(),
        preview_ref: preview.executor_preview_ref.clone(),
        node_generation: preview.node_generation,
        project_id: Some("project-crash".into()),
        quarantine_id: Some(quarantine_id.clone()),
    };
    insert_applying_operation(&fixture, &command, Some(&quarantine_id));
    fs::write(
        fixture.projects.join("project-crash/changed-after-claim"),
        b"changed",
    )
    .unwrap();

    let error = fixture
        .engine
        .handle("retry-quarantine-crash", &command)
        .unwrap_err();
    assert_eq!(error.code(), "operation_incomplete");
    assert!(fixture.projects.join("project-crash").exists());
    assert!(!fixture.quarantine.join(&quarantine_id).exists());
    let status = match fixture
        .engine
        .handle("status-quarantine-crash", &Command::Status { operation_id })
        .unwrap()
    {
        CommandResult::Operation(result) => result,
        _ => panic!("expected status"),
    };
    assert_eq!(status.status, OperationStatus::Applying);
}

#[test]
fn quarantine_id_collision_never_moves_second_project() {
    let fixture = Fixture::new(true);
    fs::create_dir(fixture.projects.join("project-first")).unwrap();
    fs::write(fixture.projects.join("project-first/data"), b"first").unwrap();
    let quarantine_id = fixture.quarantine_project("project-first", "first", 'a', 'e');
    fs::create_dir(fixture.projects.join("project-second")).unwrap();
    fs::write(fixture.projects.join("project-second/data"), b"second").unwrap();
    let preview = match fixture
        .engine
        .handle(
            "preview-quarantine-second",
            &Command::Preview {
                node_id: "primary".into(),
                category: None,
                operation_kind: OperationKind::Quarantine,
                project_id: Some("project-second".into()),
                quarantine_id: None,
            },
        )
        .unwrap()
    {
        CommandResult::Preview(result) => result,
        _ => panic!("expected preview"),
    };
    let error = fixture
        .engine
        .handle(
            "execute-quarantine-second",
            &Command::Execute {
                operation_id: format!("sop_{}", "b".repeat(32)),
                preview_ref: preview.executor_preview_ref,
                node_generation: preview.node_generation,
                project_id: Some("project-second".into()),
                quarantine_id: Some(quarantine_id.clone()),
            },
        )
        .unwrap_err();
    assert_eq!(error.code(), "operation_incomplete");
    assert!(fixture.projects.join("project-second").exists());
    assert!(fixture.quarantine.join(quarantine_id).exists());
}

#[test]
fn applying_cleanup_resumes_partially_deleted_private_stage() {
    let fixture = Fixture::new(true);
    let candidate = fixture.cache.join("partial-cleanup");
    fs::create_dir(&candidate).unwrap();
    fs::write(candidate.join("first"), b"first").unwrap();
    fs::write(candidate.join("second"), b"second").unwrap();
    let preview = fixture.preview_cleanup("preview-partial-cleanup");
    let operation_id = format!("sop_{}", "e".repeat(32));
    let command = Command::Execute {
        operation_id: operation_id.clone(),
        preview_ref: preview.executor_preview_ref,
        node_generation: preview.node_generation,
        project_id: None,
        quarantine_id: None,
    };
    insert_applying_operation(&fixture, &command, None);
    let staged = fixture
        .cache
        .join(".kolibri-storage-trash")
        .join(format!("del_{}_0", "e".repeat(32)));
    fs::rename(&candidate, &staged).unwrap();
    fs::remove_file(staged.join("first")).unwrap();

    let operation = match fixture
        .engine
        .handle("retry-partial-cleanup", &command)
        .unwrap()
    {
        CommandResult::Operation(result) => result,
        _ => panic!("expected operation"),
    };
    assert_eq!(operation.status, OperationStatus::Succeeded);
    assert!(!candidate.exists());
    assert!(!staged.exists());
}

#[test]
fn restore_reconciles_crash_after_filesystem_and_status_transition() {
    let fixture = Fixture::new(true);
    fs::create_dir(fixture.projects.join("project-restore-crash")).unwrap();
    fs::write(
        fixture.projects.join("project-restore-crash/data"),
        b"restore",
    )
    .unwrap();
    let quarantine_id =
        fixture.quarantine_project("project-restore-crash", "restore-crash", 'c', 'f');
    let preview = match fixture
        .engine
        .handle(
            "preview-restore-crash",
            &Command::Preview {
                node_id: "primary".into(),
                category: None,
                operation_kind: OperationKind::Restore,
                project_id: None,
                quarantine_id: Some(quarantine_id.clone()),
            },
        )
        .unwrap()
    {
        CommandResult::Preview(result) => result,
        _ => panic!("expected preview"),
    };
    let command = Command::Execute {
        operation_id: format!("sop_{}", "d".repeat(32)),
        preview_ref: preview.executor_preview_ref,
        node_generation: preview.node_generation,
        project_id: None,
        quarantine_id: Some(quarantine_id.clone()),
    };
    insert_applying_operation(&fixture, &command, Some(&quarantine_id));
    fs::rename(
        fixture.quarantine.join(&quarantine_id),
        fixture.projects.join("project-restore-crash"),
    )
    .unwrap();
    Connection::open(&fixture.state_db)
        .unwrap()
        .execute(
            "UPDATE quarantines SET status = 'restored' WHERE quarantine_id = ?",
            [&quarantine_id],
        )
        .unwrap();

    let operation = match fixture
        .engine
        .handle("retry-restore-crash", &command)
        .unwrap()
    {
        CommandResult::Operation(result) => result,
        _ => panic!("expected operation"),
    };
    assert_eq!(operation.status, OperationStatus::Succeeded);
    assert!(fixture.projects.join("project-restore-crash").exists());
    assert!(!fixture.quarantine.join(&quarantine_id).exists());
}

#[test]
fn replaced_allowlisted_root_fails_closed() {
    let fixture = Fixture::new(true);
    fs::create_dir(fixture.cache.join("candidate")).unwrap();
    fs::write(fixture.cache.join("candidate/data"), b"approved").unwrap();
    let preview = fixture.preview_cleanup("preview-root-replacement");
    let original = fixture._temp.path().join("original-cache");
    fs::rename(&fixture.cache, &original).unwrap();
    fs::create_dir(&fixture.cache).unwrap();
    let trash = fixture.cache.join(".kolibri-storage-trash");
    fs::create_dir(&trash).unwrap();
    fs::set_permissions(&trash, fs::Permissions::from_mode(0o700)).unwrap();
    fs::create_dir(fixture.cache.join("candidate")).unwrap();
    fs::write(fixture.cache.join("candidate/data"), b"replacement").unwrap();

    let error = fixture
        .engine
        .handle(
            "execute-root-replacement",
            &Command::Execute {
                operation_id: format!("sop_{}", "d".repeat(32)),
                preview_ref: preview.executor_preview_ref,
                node_generation: preview.node_generation,
                project_id: None,
                quarantine_id: None,
            },
        )
        .unwrap_err();
    assert_eq!(error.code(), "root_changed");
    assert!(fixture.cache.join("candidate").exists());
    assert!(original.join("candidate").exists());
}

#[test]
fn rejects_protocol_path_traversal() {
    let fixture = Fixture::new(true);
    fs::create_dir(fixture.projects.join("safe-project")).unwrap();
    let error = fixture
        .engine
        .handle(
            "preview-traversal",
            &Command::Preview {
                node_id: "primary".into(),
                category: None,
                operation_kind: OperationKind::Quarantine,
                project_id: Some("../escape".into()),
                quarantine_id: None,
            },
        )
        .unwrap_err();
    assert_eq!(error.code(), "preview_shape_invalid");
}

#[test]
fn symlinks_are_blocked_and_never_followed() {
    let fixture = Fixture::new(true);
    let outside = fixture._temp.path().join("outside");
    fs::create_dir(&outside).unwrap();
    fs::write(outside.join("keep.txt"), b"keep").unwrap();
    symlink(&outside, fixture.cache.join("linked")).unwrap();

    let preview = fixture.preview_cleanup("preview-symlink");
    assert_eq!(preview.candidate_count, 0);
    let error = fixture
        .engine
        .handle(
            "execute-symlink",
            &Command::Execute {
                operation_id: format!("sop_{}", "1".repeat(32)),
                preview_ref: preview.executor_preview_ref,
                node_generation: preview.node_generation,
                project_id: None,
                quarantine_id: None,
            },
        )
        .unwrap_err();
    assert_eq!(error.code(), "preview_empty");
    assert_eq!(fs::read(outside.join("keep.txt")).unwrap(), b"keep");
}

#[test]
fn rejects_changed_generation_before_mutation() {
    let fixture = Fixture::new(true);
    fs::create_dir(fixture.cache.join("old-build")).unwrap();
    fs::write(fixture.cache.join("old-build/data"), b"one").unwrap();
    let preview = fixture.preview_cleanup("preview-generation");
    fs::write(fixture.cache.join("old-build/changed"), b"two").unwrap();

    let error = fixture
        .engine
        .handle(
            "execute-generation",
            &Command::Execute {
                operation_id: format!("sop_{}", "2".repeat(32)),
                preview_ref: preview.executor_preview_ref,
                node_generation: preview.node_generation,
                project_id: None,
                quarantine_id: None,
            },
        )
        .unwrap_err();
    assert!(matches!(
        error.code(),
        "candidate_changed" | "generation_changed"
    ));
    assert!(fixture.cache.join("old-build").exists());
}

#[test]
fn execute_replay_is_durable_and_idempotent() {
    let fixture = Fixture::new(true);
    fs::create_dir(fixture.cache.join("cache-entry")).unwrap();
    fs::write(fixture.cache.join("cache-entry/data"), b"payload").unwrap();
    let preview = fixture.preview_cleanup("preview-idempotent");
    let command = Command::Execute {
        operation_id: format!("sop_{}", "3".repeat(32)),
        preview_ref: preview.executor_preview_ref,
        node_generation: preview.node_generation,
        project_id: None,
        quarantine_id: None,
    };
    let first = match fixture
        .engine
        .handle("execute-idempotent-1", &command)
        .unwrap()
    {
        CommandResult::Operation(result) => result,
        _ => panic!("expected operation"),
    };
    let second = match fixture
        .engine
        .handle("execute-idempotent-2", &command)
        .unwrap()
    {
        CommandResult::Operation(result) => result,
        _ => panic!("expected operation"),
    };
    assert_eq!(first.status, OperationStatus::Succeeded);
    assert_eq!(second.operation_id, first.operation_id);
    assert!(second.replayed);
    let status = match fixture
        .engine
        .handle(
            "status-idempotent",
            &Command::Status {
                operation_id: first.operation_id.clone(),
            },
        )
        .unwrap()
    {
        CommandResult::Operation(result) => result,
        _ => panic!("expected operation"),
    };
    assert_eq!(status.guarded_scopes, first.guarded_scopes);
    assert!(!fixture.cache.join("cache-entry").exists());
}

#[test]
fn signed_policy_defaults_can_disable_all_execution() {
    let fixture = Fixture::new(false);
    fs::create_dir(fixture.cache.join("cache-entry")).unwrap();
    let preview = fixture.preview_cleanup("preview-disabled");
    let error = fixture
        .engine
        .handle(
            "execute-disabled",
            &Command::Execute {
                operation_id: format!("sop_{}", "4".repeat(32)),
                preview_ref: preview.executor_preview_ref,
                node_generation: preview.node_generation,
                project_id: None,
                quarantine_id: None,
            },
        )
        .unwrap_err();
    assert_eq!(error.code(), "execution_disabled");
    assert!(fixture.cache.join("cache-entry").exists());
}

#[test]
fn incomplete_guard_evidence_preserves_capacity_but_blocks_actions() {
    let fixture = Fixture::new_with_guard_evidence(true, Some(unavailable_guard_evidence()));
    fs::create_dir(fixture.cache.join("must-not-be-actionable")).unwrap();
    let inventory = match fixture
        .engine
        .handle(
            "inventory-incomplete-evidence",
            &Command::Inventory {
                node_id: "primary".into(),
            },
        )
        .unwrap()
    {
        CommandResult::Inventory(result) => result,
        _ => panic!("expected inventory"),
    };
    assert!(inventory.capacity_bytes > 0);
    assert!(!inventory.execute_enabled);
    assert!(inventory.guarded_scopes.is_empty());
    assert!(inventory.project_candidates.is_empty());
    assert!(inventory.categories.iter().all(|category| {
        category.item_count == 0
            && category.reclaimable_bytes == 0
            && category.oldest_item_at.is_none()
    }));

    let preview_error = fixture
        .engine
        .handle(
            "preview-incomplete-evidence",
            &Command::Preview {
                node_id: "primary".into(),
                category: Some(CleanupCategory::Cache),
                operation_kind: OperationKind::Cleanup,
                project_id: None,
                quarantine_id: None,
            },
        )
        .unwrap_err();
    assert_eq!(preview_error.code(), "guard_evidence_unavailable");

    let execute_error = fixture
        .engine
        .handle(
            "execute-incomplete-evidence",
            &Command::Execute {
                operation_id: format!("sop_{}", "8".repeat(32)),
                preview_ref: "spx_missing".into(),
                node_generation: inventory.generation,
                project_id: None,
                quarantine_id: None,
            },
        )
        .unwrap_err();
    assert_eq!(execute_error.code(), "guard_evidence_unavailable");
    assert!(fixture.cache.join("must-not-be-actionable").exists());
}

#[test]
fn stopped_container_stays_zero_without_live_docker_attestation() {
    let fixture = Fixture::new_without_test_execution(true);
    let inventory = match fixture
        .engine
        .handle(
            "inventory-stopped-container",
            &Command::Inventory {
                node_id: "primary".into(),
            },
        )
        .unwrap()
    {
        CommandResult::Inventory(result) => result,
        _ => panic!("expected inventory"),
    };
    assert!(!inventory.execute_enabled);
    assert!(inventory.guarded_scopes.is_empty());
    assert!(inventory.project_candidates.is_empty());
    assert!(
        inventory
            .categories
            .iter()
            .all(|category| category.item_count == 0 && category.reclaimable_bytes == 0)
    );
    let stopped = inventory
        .categories
        .iter()
        .find(|category| category.category == CleanupCategory::StoppedContainer)
        .unwrap();
    assert_eq!(stopped.item_count, 0);
    assert_eq!(stopped.reclaimable_bytes, 0);
    let error = fixture
        .engine
        .handle(
            "preview-stopped-container",
            &Command::Preview {
                node_id: "primary".into(),
                category: Some(CleanupCategory::StoppedContainer),
                operation_kind: OperationKind::Cleanup,
                project_id: None,
                quarantine_id: None,
            },
        )
        .unwrap_err();
    assert_eq!(error.code(), "guard_evidence_unavailable");
}

#[test]
fn quarantine_retention_and_restore_conflict_fail_closed() {
    let fixture = Fixture::new(true);
    fs::create_dir(fixture.projects.join("project-alpha")).unwrap();
    fs::write(fixture.projects.join("project-alpha/data"), b"project").unwrap();
    let quarantine_id = fixture.quarantine_project("project-alpha", "alpha", '5', 'a');
    assert!(!fixture.projects.join("project-alpha").exists());
    assert!(fixture.quarantine.join(&quarantine_id).exists());

    let early_purge = fixture
        .engine
        .handle(
            "preview-purge-early",
            &Command::Preview {
                node_id: "primary".into(),
                category: None,
                operation_kind: OperationKind::Purge,
                project_id: None,
                quarantine_id: Some(quarantine_id.clone()),
            },
        )
        .unwrap_err();
    assert_eq!(early_purge.code(), "quarantine_retention_active");

    let restore_preview = match fixture
        .engine
        .handle(
            "preview-restore-alpha",
            &Command::Preview {
                node_id: "primary".into(),
                category: None,
                operation_kind: OperationKind::Restore,
                project_id: None,
                quarantine_id: Some(quarantine_id.clone()),
            },
        )
        .unwrap()
    {
        CommandResult::Preview(result) => result,
        _ => panic!("expected preview"),
    };
    fs::create_dir(fixture.projects.join("project-alpha")).unwrap();
    let conflict = fixture
        .engine
        .handle(
            "execute-restore-conflict",
            &Command::Execute {
                operation_id: format!("sop_{}", "6".repeat(32)),
                preview_ref: restore_preview.executor_preview_ref,
                node_generation: restore_preview.node_generation,
                project_id: None,
                quarantine_id: Some(quarantine_id.clone()),
            },
        )
        .unwrap_err();
    assert_eq!(conflict.code(), "restore_target_conflict");
    assert!(fixture.quarantine.join(&quarantine_id).exists());
}

#[test]
fn purge_requires_full_retention_and_never_runs_automatically() {
    let fixture = Fixture::new(true);
    fs::create_dir(fixture.projects.join("project-beta")).unwrap();
    fs::write(fixture.projects.join("project-beta/data"), b"project").unwrap();
    let quarantine_id = fixture.quarantine_project("project-beta", "beta", '7', 'b');
    fixture.clock.advance(RETENTION);
    assert!(fixture.quarantine.join(&quarantine_id).exists());

    let purge_preview = match fixture
        .engine
        .handle(
            "preview-purge-beta",
            &Command::Preview {
                node_id: "primary".into(),
                category: None,
                operation_kind: OperationKind::Purge,
                project_id: None,
                quarantine_id: Some(quarantine_id.clone()),
            },
        )
        .unwrap()
    {
        CommandResult::Preview(result) => result,
        _ => panic!("expected preview"),
    };
    let operation = match fixture
        .engine
        .handle(
            "execute-purge-beta",
            &Command::Execute {
                operation_id: format!("sop_{}", "8".repeat(32)),
                preview_ref: purge_preview.executor_preview_ref,
                node_generation: purge_preview.node_generation,
                project_id: None,
                quarantine_id: Some(quarantine_id.clone()),
            },
        )
        .unwrap()
    {
        CommandResult::Operation(result) => result,
        _ => panic!("expected operation"),
    };
    assert_eq!(operation.status, OperationStatus::Succeeded);
    assert!(!fixture.quarantine.join(&quarantine_id).exists());
}
