use std::fs::{File, OpenOptions};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::time::Duration;

use rusqlite::{Connection, OpenFlags, OptionalExtension, TransactionBehavior, params};

use crate::error::{ExecutorError, Result};
use crate::model::{
    OperationResult, OperationStatus, ProtectionScope, QuarantineStatus, QuarantineView,
};

const SCHEMA_VERSION: i64 = 1;

#[derive(Debug, Clone)]
pub(crate) struct PreviewRecord {
    pub preview_ref: String,
    pub request_id: String,
    pub request_hash: String,
    pub node_generation: String,
    pub policy_digest: String,
    pub expires_at: u64,
    pub manifest_json: String,
    pub created_at: u64,
}

#[derive(Debug, Clone)]
pub(crate) struct QuarantineRecord {
    pub quarantine_id: String,
    pub project_id: String,
    pub source_root_id: String,
    pub quarantine_root_id: String,
    pub size_bytes: u64,
    pub quarantined_at: u64,
    pub purge_eligible_at: u64,
    pub status: QuarantineStatus,
}

#[derive(Debug, Clone)]
pub(crate) struct QuarantineTransition {
    pub quarantine_id: String,
    pub expected: QuarantineStatus,
    pub target: QuarantineStatus,
}

#[derive(Debug, Clone)]
pub(crate) struct StateStore {
    path: PathBuf,
    parent: PathBuf,
    parent_device: u64,
    parent_inode: u64,
}

pub(crate) enum OperationClaim {
    New(OperationResult),
    Existing(OperationResult),
}

pub(crate) struct ExecutionLock(File);

impl Drop for ExecutionLock {
    fn drop(&mut self) {
        // SAFETY: the descriptor is valid for the lifetime of the guard.
        unsafe {
            libc::flock(self.0.as_raw_fd(), libc::LOCK_UN);
        }
    }
}

impl StateStore {
    pub fn open(path: &Path) -> Result<Self> {
        if let Ok(metadata) = std::fs::symlink_metadata(path) {
            if !metadata.is_file() || metadata.file_type().is_symlink() {
                return Err(ExecutorError::rejected(
                    "state_store_invalid",
                    "The executor state store is invalid.",
                ));
            }
        }
        let parent = path.parent().ok_or_else(|| {
            ExecutorError::rejected(
                "state_store_invalid",
                "The executor state store path is invalid.",
            )
        })?;
        let parent_metadata = std::fs::symlink_metadata(parent).map_err(|_| {
            ExecutorError::rejected(
                "state_store_invalid",
                "The executor state store directory is unavailable.",
            )
        })?;
        if !parent_metadata.is_dir()
            || parent_metadata.file_type().is_symlink()
            || parent_metadata.uid() != unsafe { libc::geteuid() }
            || parent_metadata.mode() & 0o022 != 0
        {
            return Err(ExecutorError::rejected(
                "state_store_invalid",
                "The executor state directory must be private and executor-owned.",
            ));
        }
        let store = Self {
            path: path.to_path_buf(),
            parent: parent.to_path_buf(),
            parent_device: parent_metadata.dev(),
            parent_inode: parent_metadata.ino(),
        };
        store.prepare_database_file()?;
        store.initialize()?;
        Ok(store)
    }

    fn connect(&self) -> Result<Connection> {
        self.assert_private_parent()?;
        self.assert_private_file(&self.path)?;
        let connection = Connection::open_with_flags(
            &self.path,
            OpenFlags::SQLITE_OPEN_READ_WRITE
                | OpenFlags::SQLITE_OPEN_CREATE
                | OpenFlags::SQLITE_OPEN_NO_MUTEX,
        )?;
        connection.busy_timeout(Duration::from_secs(10))?;
        connection.execute_batch(
            "PRAGMA foreign_keys = ON;
             PRAGMA trusted_schema = OFF;
             PRAGMA synchronous = FULL;",
        )?;
        self.assert_private_parent()?;
        self.assert_private_file(&self.path)?;
        Ok(connection)
    }

    fn prepare_database_file(&self) -> Result<()> {
        if !self.path.exists() {
            OpenOptions::new()
                .read(true)
                .write(true)
                .create_new(true)
                .mode(0o600)
                .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(&self.path)?;
        }
        self.assert_private_file(&self.path)
    }

    fn assert_private_parent(&self) -> Result<()> {
        let metadata = std::fs::symlink_metadata(&self.parent)?;
        if !metadata.is_dir()
            || metadata.file_type().is_symlink()
            || metadata.dev() != self.parent_device
            || metadata.ino() != self.parent_inode
            || metadata.uid() != unsafe { libc::geteuid() }
            || metadata.mode() & 0o022 != 0
        {
            return Err(ExecutorError::rejected(
                "state_store_invalid",
                "The executor state directory changed or is not private.",
            ));
        }
        Ok(())
    }

    fn assert_private_file(&self, path: &Path) -> Result<()> {
        let metadata = std::fs::symlink_metadata(path)?;
        if !metadata.is_file()
            || metadata.file_type().is_symlink()
            || metadata.uid() != unsafe { libc::geteuid() }
            || metadata.mode() & 0o077 != 0
        {
            return Err(ExecutorError::rejected(
                "state_store_invalid",
                "An executor state file is not private and executor-owned.",
            ));
        }
        Ok(())
    }

    fn initialize(&self) -> Result<()> {
        let connection = self.connect()?;
        connection.execute_batch(
            "PRAGMA journal_mode = WAL;
             CREATE TABLE IF NOT EXISTS executor_meta (
                 schema_version INTEGER NOT NULL
             ) STRICT;
             CREATE TABLE IF NOT EXISTS previews (
                 preview_ref TEXT PRIMARY KEY,
                 request_id TEXT NOT NULL UNIQUE,
                 request_hash TEXT NOT NULL,
                 node_generation TEXT NOT NULL,
                 policy_digest TEXT NOT NULL,
                 expires_at INTEGER NOT NULL CHECK (expires_at >= 0),
                 manifest_json TEXT NOT NULL CHECK (json_valid(manifest_json)),
                 created_at INTEGER NOT NULL CHECK (created_at >= 0)
             ) STRICT;
             CREATE TABLE IF NOT EXISTS operations (
                 operation_id TEXT PRIMARY KEY,
                 preview_ref TEXT NOT NULL REFERENCES previews(preview_ref),
                 request_hash TEXT NOT NULL,
                 status TEXT NOT NULL CHECK (status IN ('applying', 'succeeded', 'failed')),
                 affected_item_count INTEGER NOT NULL DEFAULT 0
                     CHECK (affected_item_count >= 0),
                 reclaimed_bytes INTEGER NOT NULL DEFAULT 0
                     CHECK (reclaimed_bytes >= 0),
                 quarantine_id TEXT,
                 error_code TEXT,
                 node_generation TEXT,
                 response_json TEXT CHECK (
                     response_json IS NULL OR json_valid(response_json)
                 ),
                 created_at INTEGER NOT NULL CHECK (created_at >= 0),
                 completed_at INTEGER CHECK (completed_at IS NULL OR completed_at >= 0)
             ) STRICT;
             CREATE TABLE IF NOT EXISTS quarantines (
                 quarantine_id TEXT PRIMARY KEY,
                 project_id TEXT NOT NULL,
                 source_root_id TEXT NOT NULL,
                 quarantine_root_id TEXT NOT NULL,
                 size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
                 quarantined_at INTEGER NOT NULL CHECK (quarantined_at >= 0),
                 purge_eligible_at INTEGER NOT NULL CHECK (purge_eligible_at >= quarantined_at),
                 status TEXT NOT NULL CHECK (status IN ('retained', 'restored', 'purged'))
             ) STRICT;
             CREATE TABLE IF NOT EXISTS audit (
                 sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                 created_at INTEGER NOT NULL,
                 operation_id TEXT,
                 event TEXT NOT NULL,
                 details_digest TEXT NOT NULL
             ) STRICT;",
        )?;
        let count: i64 =
            connection.query_row("SELECT COUNT(*) FROM executor_meta", [], |row| row.get(0))?;
        if count == 0 {
            connection.execute(
                "INSERT INTO executor_meta (schema_version) VALUES (?)",
                [SCHEMA_VERSION],
            )?;
        }
        let version: i64 = connection.query_row(
            "SELECT schema_version FROM executor_meta LIMIT 1",
            [],
            |row| row.get(0),
        )?;
        if version != SCHEMA_VERSION {
            return Err(ExecutorError::rejected(
                "state_schema_unsupported",
                "The executor state schema is unsupported.",
            ));
        }
        Ok(())
    }

    pub fn preview_by_request(&self, request_id: &str) -> Result<Option<PreviewRecord>> {
        let connection = self.connect()?;
        query_preview(
            &connection,
            "SELECT * FROM previews WHERE request_id = ?",
            request_id,
        )
    }

    pub fn preview_by_ref(&self, preview_ref: &str) -> Result<Option<PreviewRecord>> {
        let connection = self.connect()?;
        query_preview(
            &connection,
            "SELECT * FROM previews WHERE preview_ref = ?",
            preview_ref,
        )
    }

    pub fn insert_preview(&self, preview: &PreviewRecord) -> Result<()> {
        let mut connection = self.connect()?;
        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
        transaction.execute(
            "INSERT INTO previews (
                 preview_ref, request_id, request_hash, node_generation,
                 policy_digest, expires_at, manifest_json, created_at
             ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            params![
                preview.preview_ref,
                preview.request_id,
                preview.request_hash,
                preview.node_generation,
                preview.policy_digest,
                to_i64(preview.expires_at)?,
                preview.manifest_json,
                to_i64(preview.created_at)?,
            ],
        )?;
        append_audit(
            &transaction,
            preview.created_at,
            None,
            "preview.created",
            &preview.request_hash,
        )?;
        transaction.commit()?;
        Ok(())
    }

    pub fn claim_operation(
        &self,
        operation_id: &str,
        preview_ref: &str,
        request_hash: &str,
        quarantine_id: Option<&str>,
        now: u64,
    ) -> Result<OperationClaim> {
        let mut connection = self.connect()?;
        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
        if let Some(existing) = query_operation(&transaction, operation_id)? {
            let stored_hash: String = transaction.query_row(
                "SELECT request_hash FROM operations WHERE operation_id = ?",
                [operation_id],
                |row| row.get(0),
            )?;
            if stored_hash != request_hash {
                return Err(ExecutorError::rejected(
                    "operation_idempotency_conflict",
                    "The operation ID was already used for another payload.",
                ));
            }
            transaction.commit()?;
            return Ok(OperationClaim::Existing(existing));
        }
        transaction.execute(
            "INSERT INTO operations (
                 operation_id, preview_ref, request_hash, status,
                 quarantine_id, created_at
             ) VALUES (?, ?, ?, 'applying', ?, ?)",
            params![
                operation_id,
                preview_ref,
                request_hash,
                quarantine_id,
                to_i64(now)?,
            ],
        )?;
        append_audit(
            &transaction,
            now,
            Some(operation_id),
            "operation.claimed",
            request_hash,
        )?;
        let operation = query_operation(&transaction, operation_id)?.ok_or_else(|| {
            ExecutorError::rejected(
                "operation_journal_failed",
                "The operation journal could not be created.",
            )
        })?;
        transaction.commit()?;
        Ok(OperationClaim::New(operation))
    }

    pub fn operation(&self, operation_id: &str) -> Result<Option<OperationResult>> {
        let connection = self.connect()?;
        query_operation(&connection, operation_id)
    }

    pub fn acquire_execution_lock(&self) -> Result<ExecutionLock> {
        let lock_path = self.path.with_extension("db.lock");
        if let Ok(metadata) = std::fs::symlink_metadata(&lock_path) {
            if !metadata.is_file() || metadata.file_type().is_symlink() {
                return Err(ExecutorError::rejected(
                    "operation_lock_invalid",
                    "The executor operation lock is invalid.",
                ));
            }
        }
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(lock_path)?;
        let metadata = file.metadata()?;
        if !metadata.is_file()
            || metadata.uid() != unsafe { libc::geteuid() }
            || metadata.mode() & 0o077 != 0
        {
            return Err(ExecutorError::rejected(
                "operation_lock_invalid",
                "The executor operation lock is not private.",
            ));
        }
        // SAFETY: file owns a valid descriptor. LOCK_NB prevents a second
        // forced-command process from mutating the same node concurrently.
        if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err(ExecutorError::incomplete(
                "operation_busy",
                "Another storage operation is currently applying.",
            ));
        }
        Ok(ExecutionLock(file))
    }

    #[allow(clippy::too_many_arguments)]
    pub fn complete_operation(
        &self,
        operation_id: &str,
        affected_item_count: u64,
        reclaimed_bytes: u64,
        quarantine_id: Option<&str>,
        quarantine_transition: Option<&QuarantineTransition>,
        node_generation: &str,
        guarded_scopes: &[ProtectionScope],
        now: u64,
    ) -> Result<OperationResult> {
        let mut connection = self.connect()?;
        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let preview_ref: String = transaction.query_row(
            "SELECT preview_ref FROM operations WHERE operation_id = ?",
            [operation_id],
            |row| row.get(0),
        )?;
        let response = OperationResult {
            operation_id: operation_id.to_owned(),
            preview_ref,
            status: OperationStatus::Succeeded,
            affected_item_count,
            reclaimed_bytes,
            protected_item_count: 0,
            guarded_scopes: guarded_scopes.to_vec(),
            node_generation: node_generation.to_owned(),
            quarantine_id: quarantine_id.map(str::to_owned),
            error_code: None,
            created_at: 0,
            completed_at: Some(now),
            replayed: false,
        };
        let response_json = serde_json::to_string(&response)?;
        if let Some(transition) = quarantine_transition {
            let current: Option<String> = transaction
                .query_row(
                    "SELECT status FROM quarantines WHERE quarantine_id = ?",
                    [&transition.quarantine_id],
                    |row| row.get(0),
                )
                .optional()?;
            let expected = quarantine_status_text(transition.expected);
            let target = quarantine_status_text(transition.target);
            match current.as_deref() {
                Some(value) if value == expected => {
                    let updated = transaction.execute(
                        "UPDATE quarantines SET status = ?
                         WHERE quarantine_id = ? AND status = ?",
                        params![target, transition.quarantine_id, expected],
                    )?;
                    if updated != 1 {
                        return Err(ExecutorError::incomplete(
                            "quarantine_transition_race",
                            "The quarantine state changed during completion.",
                        ));
                    }
                }
                Some(value) if value == target => {}
                _ => {
                    return Err(ExecutorError::incomplete(
                        "quarantine_state_conflict",
                        "The quarantine state cannot be reconciled.",
                    ));
                }
            }
        }
        transaction.execute(
            "UPDATE operations
             SET status = 'succeeded',
                 affected_item_count = ?,
                 reclaimed_bytes = ?,
                 quarantine_id = COALESCE(?, quarantine_id),
                 error_code = NULL,
                 node_generation = ?,
                 response_json = ?,
                 completed_at = ?
             WHERE operation_id = ? AND status = 'applying'",
            params![
                to_i64(affected_item_count)?,
                to_i64(reclaimed_bytes)?,
                quarantine_id,
                node_generation,
                response_json,
                to_i64(now)?,
                operation_id,
            ],
        )?;
        append_audit(
            &transaction,
            now,
            Some(operation_id),
            "operation.succeeded",
            &format!("{affected_item_count}:{reclaimed_bytes}"),
        )?;
        let result = query_operation(&transaction, operation_id)?.ok_or_else(|| {
            ExecutorError::rejected(
                "operation_not_found",
                "The storage operation was not found.",
            )
        })?;
        transaction.commit()?;
        Ok(result)
    }

    pub fn record_incomplete(&self, operation_id: &str, error_code: &str, now: u64) -> Result<()> {
        let mut connection = self.connect()?;
        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
        append_audit(
            &transaction,
            now,
            Some(operation_id),
            "operation.incomplete",
            error_code,
        )?;
        transaction.commit()?;
        Ok(())
    }

    pub fn put_quarantine(&self, record: &QuarantineRecord) -> Result<()> {
        let mut connection = self.connect()?;
        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let existing = transaction
            .query_row(
                "SELECT * FROM quarantines WHERE quarantine_id = ?",
                [&record.quarantine_id],
                quarantine_from_row,
            )
            .optional()?;
        if let Some(existing) = existing {
            if existing.project_id != record.project_id
                || existing.source_root_id != record.source_root_id
                || existing.quarantine_root_id != record.quarantine_root_id
                || existing.size_bytes != record.size_bytes
                || existing.status != QuarantineStatus::Retained
            {
                return Err(ExecutorError::incomplete(
                    "quarantine_id_collision",
                    "The quarantine ID is already bound to another record.",
                ));
            }
            transaction.commit()?;
            return Ok(());
        }
        transaction.execute(
            "INSERT INTO quarantines (
                 quarantine_id, project_id, source_root_id,
                 quarantine_root_id, size_bytes, quarantined_at,
                 purge_eligible_at, status
             ) VALUES (?, ?, ?, ?, ?, ?, ?, 'retained')",
            params![
                record.quarantine_id,
                record.project_id,
                record.source_root_id,
                record.quarantine_root_id,
                to_i64(record.size_bytes)?,
                to_i64(record.quarantined_at)?,
                to_i64(record.purge_eligible_at)?,
            ],
        )?;
        transaction.commit()?;
        Ok(())
    }

    pub fn quarantine(&self, quarantine_id: &str) -> Result<Option<QuarantineRecord>> {
        let connection = self.connect()?;
        connection
            .query_row(
                "SELECT * FROM quarantines WHERE quarantine_id = ?",
                [quarantine_id],
                quarantine_from_row,
            )
            .optional()
            .map_err(Into::into)
    }

    pub fn quarantines(&self) -> Result<Vec<QuarantineView>> {
        let connection = self.connect()?;
        let mut statement = connection.prepare(
            "SELECT * FROM quarantines
             WHERE status = 'retained'
             ORDER BY quarantined_at, quarantine_id",
        )?;
        let rows = statement.query_map([], quarantine_from_row)?;
        let mut result = Vec::new();
        for row in rows {
            let record = row?;
            result.push(QuarantineView {
                quarantine_id: record.quarantine_id,
                project_id: record.project_id,
                status: record.status,
                size_bytes: record.size_bytes,
                quarantined_at: record.quarantined_at,
                purge_eligible_at: record.purge_eligible_at,
            });
        }
        Ok(result)
    }
}

fn query_preview(
    connection: &Connection,
    sql: &str,
    parameter: &str,
) -> Result<Option<PreviewRecord>> {
    connection
        .query_row(sql, [parameter], |row| {
            Ok(PreviewRecord {
                preview_ref: row.get("preview_ref")?,
                request_id: row.get("request_id")?,
                request_hash: row.get("request_hash")?,
                node_generation: row.get("node_generation")?,
                policy_digest: row.get("policy_digest")?,
                expires_at: from_i64(row.get("expires_at")?)?,
                manifest_json: row.get("manifest_json")?,
                created_at: from_i64(row.get("created_at")?)?,
            })
        })
        .optional()
        .map_err(Into::into)
}

fn query_operation(connection: &Connection, operation_id: &str) -> Result<Option<OperationResult>> {
    connection
        .query_row(
            "SELECT operation.*,
                    COALESCE(
                        operation.node_generation,
                        preview.node_generation
                    ) AS effective_node_generation
             FROM operations AS operation
             JOIN previews AS preview
               ON preview.preview_ref = operation.preview_ref
             WHERE operation.operation_id = ?",
            [operation_id],
            |row| {
                let status: String = row.get("status")?;
                let response_json: Option<String> = row.get("response_json")?;
                let guarded_scopes = match response_json {
                    Some(response_json) => {
                        serde_json::from_str::<OperationResult>(&response_json)
                            .map_err(|error| {
                                rusqlite::Error::FromSqlConversionFailure(
                                    9,
                                    rusqlite::types::Type::Text,
                                    Box::new(error),
                                )
                            })?
                            .guarded_scopes
                    }
                    None => Vec::new(),
                };
                Ok(OperationResult {
                    operation_id: row.get("operation_id")?,
                    preview_ref: row.get("preview_ref")?,
                    status: match status.as_str() {
                        "applying" => OperationStatus::Applying,
                        "succeeded" => OperationStatus::Succeeded,
                        "failed" => OperationStatus::Failed,
                        _ => {
                            return Err(rusqlite::Error::InvalidColumnType(
                                3,
                                "status".into(),
                                rusqlite::types::Type::Text,
                            ));
                        }
                    },
                    affected_item_count: from_i64(row.get("affected_item_count")?)?,
                    reclaimed_bytes: from_i64(row.get("reclaimed_bytes")?)?,
                    protected_item_count: 0,
                    guarded_scopes,
                    node_generation: row.get("effective_node_generation")?,
                    quarantine_id: row.get("quarantine_id")?,
                    error_code: row.get("error_code")?,
                    created_at: from_i64(row.get("created_at")?)?,
                    completed_at: row
                        .get::<_, Option<i64>>("completed_at")?
                        .map(from_i64)
                        .transpose()?,
                    replayed: false,
                })
            },
        )
        .optional()
        .map_err(Into::into)
}

fn quarantine_from_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<QuarantineRecord> {
    let status: String = row.get("status")?;
    Ok(QuarantineRecord {
        quarantine_id: row.get("quarantine_id")?,
        project_id: row.get("project_id")?,
        source_root_id: row.get("source_root_id")?,
        quarantine_root_id: row.get("quarantine_root_id")?,
        size_bytes: from_i64(row.get("size_bytes")?)?,
        quarantined_at: from_i64(row.get("quarantined_at")?)?,
        purge_eligible_at: from_i64(row.get("purge_eligible_at")?)?,
        status: match status.as_str() {
            "retained" => QuarantineStatus::Retained,
            "restored" => QuarantineStatus::Restored,
            "purged" => QuarantineStatus::Purged,
            _ => {
                return Err(rusqlite::Error::InvalidColumnType(
                    7,
                    "status".into(),
                    rusqlite::types::Type::Text,
                ));
            }
        },
    })
}

fn append_audit(
    connection: &Connection,
    now: u64,
    operation_id: Option<&str>,
    event: &str,
    details: &str,
) -> Result<()> {
    use sha2::{Digest, Sha256};
    connection.execute(
        "INSERT INTO audit (created_at, operation_id, event, details_digest)
         VALUES (?, ?, ?, ?)",
        params![
            to_i64(now)?,
            operation_id,
            event,
            hex::encode(Sha256::digest(details.as_bytes())),
        ],
    )?;
    Ok(())
}

fn quarantine_status_text(status: QuarantineStatus) -> &'static str {
    match status {
        QuarantineStatus::Retained => "retained",
        QuarantineStatus::Restored => "restored",
        QuarantineStatus::Purged => "purged",
    }
}

fn to_i64(value: u64) -> Result<i64> {
    i64::try_from(value).map_err(|_| {
        ExecutorError::rejected(
            "numeric_limit_exceeded",
            "A storage value exceeds the supported range.",
        )
    })
}

fn from_i64(value: i64) -> rusqlite::Result<u64> {
    u64::try_from(value).map_err(|_| rusqlite::Error::IntegralValueOutOfRange(0, value))
}
