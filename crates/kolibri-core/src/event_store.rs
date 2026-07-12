use crate::events::{
    EventAuthorityStatus, EventDraft, EventEnvelope, EventEnvelopeError, IdentifierError,
    validate_identifier,
};
use chrono::Utc;
use fs2::FileExt;
use hmac::{Hmac, Mac};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use thiserror::Error;
use zeroize::Zeroize;

type HmacSha256 = Hmac<Sha256>;

const HOME_SOURCE: &str = "control-plane/home";
const AUTH_CHALLENGE: &[u8] = b"kolibri.home.authoritative-append.v1";
const HEAD_CHALLENGE: &[u8] = b"kolibri.home.event-log-head.v1";
const EVENT_LOG_HEAD_VERSION: u32 = 1;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
struct EventLogHead {
    version: u32,
    record_count: u64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    last_record_hmac_sha256: Option<String>,
    head_hmac_sha256: String,
}

/// Runtime-held credentials for the one canonical Home append authority.
///
/// The token is intentionally omitted from `Debug`, serialization and every
/// error. Production should construct this value from a secret provider.
#[derive(Clone)]
pub struct HomeAuthorityConfig {
    node_id: String,
    token: Vec<u8>,
}

impl Drop for HomeAuthorityConfig {
    fn drop(&mut self) {
        self.token.zeroize();
    }
}

impl std::fmt::Debug for HomeAuthorityConfig {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("HomeAuthorityConfig")
            .field("node_id", &self.node_id)
            .field("token", &"***")
            .finish()
    }
}

impl HomeAuthorityConfig {
    pub fn new(
        node_id: impl Into<String>,
        token: impl AsRef<[u8]>,
    ) -> Result<Self, EventStoreError> {
        let node_id = node_id.into();
        validate_identifier(&node_id).map_err(EventStoreError::InvalidNodeId)?;
        let token = token.as_ref();
        if token.len() < 32 {
            return Err(EventStoreError::WeakAuthorityToken);
        }
        Ok(Self {
            node_id,
            token: token.to_vec(),
        })
    }

    pub fn node_id(&self) -> &str {
        &self.node_id
    }

    fn authenticate(&self, credential: &HomeAppendCredential) -> Result<(), EventStoreError> {
        let mut expected = HmacSha256::new_from_slice(&self.token)
            .map_err(|_| EventStoreError::InvalidAuthorityKey)?;
        expected.update(AUTH_CHALLENGE);
        let expected_tag = expected.finalize().into_bytes();

        let mut presented = HmacSha256::new_from_slice(&credential.token)
            .map_err(|_| EventStoreError::InvalidAuthorityKey)?;
        presented.update(AUTH_CHALLENGE);
        presented
            .verify_slice(expected_tag.as_slice())
            .map_err(|_| EventStoreError::AuthenticationFailed)
    }
}

/// Per-call proof presented to the authoritative append boundary.
pub struct HomeAppendCredential {
    token: Vec<u8>,
}

impl Drop for HomeAppendCredential {
    fn drop(&mut self) {
        self.token.zeroize();
    }
}

impl std::fmt::Debug for HomeAppendCredential {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("HomeAppendCredential")
            .field("token", &"***")
            .finish()
    }
}

impl HomeAppendCredential {
    pub fn new(token: impl AsRef<[u8]>) -> Self {
        Self {
            token: token.as_ref().to_vec(),
        }
    }
}

/// A minimal durable JSONL event store for the bootstrap release.
///
/// Allocation and append happen under an OS file lock, and the log itself is
/// fsynced before success is returned. The log is the sequence source of truth,
/// so restart and concurrent processes cannot reset counters to `1`.
pub struct DurableHomeEventStore {
    directory: PathBuf,
    log_path: PathBuf,
    lock_path: PathBuf,
    head_path: PathBuf,
    authority: HomeAuthorityConfig,
}

/// An envelope whose Home source, sequence, node binding and HMAC were
/// verified by the authoritative store. The private field prevents callers
/// from turning a deserialized source claim into trusted evidence.
#[derive(Debug, Clone, serde::Serialize, PartialEq)]
#[serde(transparent)]
pub struct VerifiedEventEnvelope(EventEnvelope);

impl VerifiedEventEnvelope {
    pub fn envelope(&self) -> &EventEnvelope {
        &self.0
    }

    pub fn into_envelope(self) -> EventEnvelope {
        self.0
    }

    pub fn source(&self) -> &str {
        &self.0.source
    }

    pub fn sequence(&self) -> u64 {
        self.0.sequence
    }

    pub fn idempotency_key(&self) -> &str {
        &self.0.idempotency_key
    }
}

impl std::fmt::Debug for DurableHomeEventStore {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("DurableHomeEventStore")
            .field("directory", &self.directory)
            .field("log_path", &self.log_path)
            .field("lock_path", &self.lock_path)
            .field("head_path", &self.head_path)
            .field("authority", &self.authority)
            .finish()
    }
}

impl DurableHomeEventStore {
    pub fn open(
        directory: impl AsRef<Path>,
        authority: HomeAuthorityConfig,
    ) -> Result<Self, EventStoreError> {
        let directory = directory.as_ref();
        prepare_private_directory(directory)?;
        let log_path = directory.join("events.v1.jsonl");
        let lock_path = directory.join("events.v1.lock");
        let head_path = directory.join("events.v1.head.json");
        create_private_file(&log_path)?;
        create_private_file(&lock_path)?;
        sync_directory(directory)?;
        let store = Self {
            directory: directory.to_path_buf(),
            log_path,
            lock_path,
            head_path,
            authority,
        };
        let lock = open_private_file(&store.lock_path, false)?;
        lock.lock_exclusive()?;
        let result = (|| {
            store.recover_partial_tail_unlocked()?;
            let events = store.read_verified_unlocked()?;
            store.reconcile_head_unlocked(&events)
        })();
        let unlock_result = FileExt::unlock(&lock);
        match (result, unlock_result) {
            (Ok(()), Ok(())) => Ok(store),
            (Err(error), _) => Err(error),
            (Ok(()), Err(error)) => Err(EventStoreError::Io(error)),
        }
    }

    pub fn append(
        &self,
        draft: EventDraft,
        credential: &HomeAppendCredential,
    ) -> Result<VerifiedEventEnvelope, EventStoreError> {
        draft.validate()?;
        self.authority.authenticate(credential)?;
        let draft_sha256 = encode_hex(Sha256::digest(serde_json::to_vec(&draft)?).as_slice());
        let lock = open_private_file(&self.lock_path, false)?;
        lock.lock_exclusive()?;

        let result = (|| {
            self.recover_partial_tail_unlocked()?;
            let mut events = self.read_verified_unlocked()?;
            self.reconcile_head_unlocked(&events)?;
            if let Some(existing) = events
                .iter()
                .find(|event| event.idempotency_key() == draft.idempotency_key)
            {
                if existing.envelope().authority.draft_sha256.as_deref()
                    == Some(draft_sha256.as_str())
                {
                    return Ok(existing.clone());
                }
                return Err(EventStoreError::IdempotencyConflict);
            }

            let sequence = events
                .iter()
                .filter(|event| event.envelope().subject == draft.subject)
                .map(VerifiedEventEnvelope::sequence)
                .max()
                .unwrap_or(0)
                .checked_add(1)
                .ok_or(EventStoreError::SequenceOverflow)?;
            let previous_record_hmac_sha256 = events
                .last()
                .and_then(|event| event.envelope().authority.record_hmac_sha256.clone());
            let authenticated_at = Utc::now();
            let mut event = EventEnvelope::from_authoritative_draft(
                draft,
                sequence,
                self.authority.node_id.clone(),
                authenticated_at,
                draft_sha256,
                previous_record_hmac_sha256,
            );
            let signature = self.sign(&event)?;
            event.set_record_hmac_sha256(signature);
            self.verify_event(&event)?;

            let mut serialized = serde_json::to_vec(&event)?;
            serialized.push(b'\n');
            let mut log = open_private_append_file(&self.log_path)?;
            log.write_all(&serialized)?;
            log.flush()?;
            log.sync_all()?;
            let verified = VerifiedEventEnvelope(event);
            events.push(verified.clone());
            self.write_head_unlocked(&events)?;
            Ok(verified)
        })();

        let unlock_result = FileExt::unlock(&lock);
        match (result, unlock_result) {
            (Ok(value), Ok(())) => Ok(value),
            (Err(error), _) => Err(error),
            (Ok(_), Err(error)) => Err(EventStoreError::Io(error)),
        }
    }

    pub fn read_verified(&self) -> Result<Vec<VerifiedEventEnvelope>, EventStoreError> {
        let lock = open_private_file(&self.lock_path, false)?;
        FileExt::lock_shared(&lock)?;
        let result = (|| {
            let events = self.read_verified_unlocked()?;
            self.verify_head_exact_unlocked(&events)?;
            Ok(events)
        })();
        let unlock_result = FileExt::unlock(&lock);
        match (result, unlock_result) {
            (Ok(value), Ok(())) => Ok(value),
            (Err(error), _) => Err(error),
            (Ok(_), Err(error)) => Err(EventStoreError::Io(error)),
        }
    }

    fn read_verified_unlocked(&self) -> Result<Vec<VerifiedEventEnvelope>, EventStoreError> {
        let mut file = open_private_file(&self.log_path, false)?;
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes)?;
        if !bytes.is_empty() && bytes.last() != Some(&b'\n') {
            return Err(EventStoreError::IncompleteTail);
        }
        let mut events = Vec::new();
        let mut previous_record_hmac_sha256: Option<String> = None;
        let mut subject_sequences: BTreeMap<String, u64> = BTreeMap::new();
        let mut event_ids = BTreeSet::new();
        let mut idempotency_keys = BTreeSet::new();
        for (index, line) in bytes.split(|byte| *byte == b'\n').enumerate() {
            if line.iter().all(u8::is_ascii_whitespace) {
                continue;
            }
            let event: EventEnvelope =
                serde_json::from_slice(line).map_err(|source| EventStoreError::CorruptRecord {
                    line: index + 1,
                    reason: source.to_string(),
                })?;
            self.verify_event(&event)
                .map_err(|source| EventStoreError::CorruptRecord {
                    line: index + 1,
                    reason: source.to_string(),
                })?;
            if event.authority.previous_record_hmac_sha256 != previous_record_hmac_sha256 {
                return Err(EventStoreError::CorruptRecord {
                    line: index + 1,
                    reason: "record hash chain mismatch".to_string(),
                });
            }
            let expected_sequence = subject_sequences
                .get(&event.subject)
                .copied()
                .unwrap_or(0)
                .checked_add(1)
                .ok_or(EventStoreError::SequenceOverflow)?;
            if event.sequence != expected_sequence {
                return Err(EventStoreError::CorruptRecord {
                    line: index + 1,
                    reason: format!(
                        "subject sequence mismatch: expected {expected_sequence}, got {}",
                        event.sequence
                    ),
                });
            }
            if !event_ids.insert(event.id) {
                return Err(EventStoreError::CorruptRecord {
                    line: index + 1,
                    reason: "duplicate event id".to_string(),
                });
            }
            if event.idempotency_key.trim().is_empty()
                || !idempotency_keys.insert(event.idempotency_key.clone())
            {
                return Err(EventStoreError::CorruptRecord {
                    line: index + 1,
                    reason: "missing or duplicate idempotency key".to_string(),
                });
            }
            subject_sequences.insert(event.subject.clone(), event.sequence);
            previous_record_hmac_sha256 = event.authority.record_hmac_sha256.clone();
            events.push(VerifiedEventEnvelope(event));
        }
        Ok(events)
    }

    fn verify_event(&self, event: &EventEnvelope) -> Result<(), EventStoreError> {
        event.validate_contract()?;
        if event.source != HOME_SOURCE {
            return Err(EventStoreError::InvalidAuthoritativeSource(
                event.source.clone(),
            ));
        }
        if event.authority.status != EventAuthorityStatus::Authoritative {
            return Err(EventStoreError::UntrustedRecord);
        }
        if event.authority.node_id.as_deref() != Some(self.authority.node_id())
            || event.provenance.node_id.as_deref() != Some(self.authority.node_id())
        {
            return Err(EventStoreError::AuthorityNodeMismatch);
        }
        let draft_sha256 = event
            .authority
            .draft_sha256
            .as_deref()
            .ok_or(EventStoreError::MissingDraftFingerprint)?;
        decode_hex_32(draft_sha256)?;
        if let Some(previous) = event.authority.previous_record_hmac_sha256.as_deref() {
            decode_hex_32(previous)?;
        }
        let signature = event
            .authority
            .record_hmac_sha256
            .as_deref()
            .ok_or(EventStoreError::MissingRecordSignature)?;
        let signature = decode_hex_32(signature)?;
        let mut mac = HmacSha256::new_from_slice(&self.authority.token)
            .map_err(|_| EventStoreError::InvalidAuthorityKey)?;
        mac.update(&self.signing_bytes(event)?);
        mac.verify_slice(&signature)
            .map_err(|_| EventStoreError::InvalidRecordSignature)
    }

    fn sign(&self, event: &EventEnvelope) -> Result<String, EventStoreError> {
        let mut mac = HmacSha256::new_from_slice(&self.authority.token)
            .map_err(|_| EventStoreError::InvalidAuthorityKey)?;
        mac.update(&self.signing_bytes(event)?);
        Ok(encode_hex(mac.finalize().into_bytes().as_slice()))
    }

    fn signing_bytes(&self, event: &EventEnvelope) -> Result<Vec<u8>, EventStoreError> {
        let mut unsigned = event.clone();
        unsigned.clear_record_hmac_sha256();
        Ok(serde_json::to_vec(&unsigned)?)
    }

    fn recover_partial_tail_unlocked(&self) -> Result<(), EventStoreError> {
        let mut log = open_private_file(&self.log_path, false)?;
        let mut bytes = Vec::new();
        log.read_to_end(&mut bytes)?;
        if bytes.is_empty() || bytes.last() == Some(&b'\n') {
            return Ok(());
        }
        let truncate_to = bytes
            .iter()
            .rposition(|byte| *byte == b'\n')
            .map_or(0, |index| index + 1);
        log.set_len(u64::try_from(truncate_to).map_err(|_| EventStoreError::LogTooLarge)?)?;
        log.sync_all()?;
        Ok(())
    }

    fn reconcile_head_unlocked(
        &self,
        events: &[VerifiedEventEnvelope],
    ) -> Result<(), EventStoreError> {
        let actual = self.head_for_events(events)?;
        let Some(stored) = self.read_head_unlocked()? else {
            return self.write_signed_head_unlocked(actual);
        };
        self.verify_head_signature(&stored)?;
        if stored == actual {
            return Ok(());
        }
        if stored.record_count > actual.record_count {
            return Err(EventStoreError::LogRollbackDetected);
        }
        if stored.record_count == actual.record_count {
            return Err(EventStoreError::LogHeadMismatch);
        }
        let prefix_hmac = if stored.record_count == 0 {
            None
        } else {
            let index = usize::try_from(stored.record_count - 1)
                .map_err(|_| EventStoreError::LogTooLarge)?;
            events
                .get(index)
                .and_then(|event| event.envelope().authority.record_hmac_sha256.clone())
        };
        if prefix_hmac != stored.last_record_hmac_sha256 {
            return Err(EventStoreError::LogRollbackDetected);
        }
        self.write_signed_head_unlocked(actual)
    }

    fn verify_head_exact_unlocked(
        &self,
        events: &[VerifiedEventEnvelope],
    ) -> Result<(), EventStoreError> {
        let stored = self
            .read_head_unlocked()?
            .ok_or(EventStoreError::MissingLogHead)?;
        self.verify_head_signature(&stored)?;
        if stored != self.head_for_events(events)? {
            return Err(EventStoreError::LogHeadMismatch);
        }
        Ok(())
    }

    fn head_for_events(
        &self,
        events: &[VerifiedEventEnvelope],
    ) -> Result<EventLogHead, EventStoreError> {
        let mut head = EventLogHead {
            version: EVENT_LOG_HEAD_VERSION,
            record_count: u64::try_from(events.len()).map_err(|_| EventStoreError::LogTooLarge)?,
            last_record_hmac_sha256: events
                .last()
                .and_then(|event| event.envelope().authority.record_hmac_sha256.clone()),
            head_hmac_sha256: String::new(),
        };
        head.head_hmac_sha256 = self.sign_head(&head)?;
        Ok(head)
    }

    fn read_head_unlocked(&self) -> Result<Option<EventLogHead>, EventStoreError> {
        let metadata = match fs::symlink_metadata(&self.head_path) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(EventStoreError::Io(error)),
        };
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(EventStoreError::UnsafePath(self.head_path.clone()));
        }
        let mut file = open_private_file(&self.head_path, false)?;
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes)?;
        if bytes.is_empty() {
            return Err(EventStoreError::CorruptLogHead);
        }
        serde_json::from_slice(&bytes)
            .map(Some)
            .map_err(|_| EventStoreError::CorruptLogHead)
    }

    fn write_head_unlocked(&self, events: &[VerifiedEventEnvelope]) -> Result<(), EventStoreError> {
        self.write_signed_head_unlocked(self.head_for_events(events)?)
    }

    fn write_signed_head_unlocked(&self, head: EventLogHead) -> Result<(), EventStoreError> {
        match fs::symlink_metadata(&self.head_path) {
            Ok(_) => {
                let _ = open_private_file(&self.head_path, false)?;
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(EventStoreError::Io(error)),
        }
        let temp_path = self.directory.join(format!(
            ".events.v1.head.{}.{}.tmp",
            std::process::id(),
            uuid::Uuid::new_v4()
        ));
        let result = (|| {
            let mut temp = create_new_private_file(&temp_path)?;
            temp.write_all(&serde_json::to_vec(&head)?)?;
            temp.flush()?;
            temp.sync_all()?;
            fs::rename(&temp_path, &self.head_path)?;
            sync_directory(&self.directory)
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temp_path);
        }
        result
    }

    fn sign_head(&self, head: &EventLogHead) -> Result<String, EventStoreError> {
        let mut unsigned = head.clone();
        unsigned.head_hmac_sha256.clear();
        let mut mac = HmacSha256::new_from_slice(&self.authority.token)
            .map_err(|_| EventStoreError::InvalidAuthorityKey)?;
        mac.update(HEAD_CHALLENGE);
        mac.update(&serde_json::to_vec(&unsigned)?);
        Ok(encode_hex(mac.finalize().into_bytes().as_slice()))
    }

    fn verify_head_signature(&self, head: &EventLogHead) -> Result<(), EventStoreError> {
        if head.version != EVENT_LOG_HEAD_VERSION {
            return Err(EventStoreError::CorruptLogHead);
        }
        let signature =
            decode_hex_32(&head.head_hmac_sha256).map_err(|_| EventStoreError::CorruptLogHead)?;
        let mut unsigned = head.clone();
        unsigned.head_hmac_sha256.clear();
        let mut mac = HmacSha256::new_from_slice(&self.authority.token)
            .map_err(|_| EventStoreError::InvalidAuthorityKey)?;
        mac.update(HEAD_CHALLENGE);
        mac.update(&serde_json::to_vec(&unsigned)?);
        mac.verify_slice(&signature)
            .map_err(|_| EventStoreError::CorruptLogHead)
    }
}

fn encode_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut result = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        result.push(HEX[(byte >> 4) as usize] as char);
        result.push(HEX[(byte & 0x0f) as usize] as char);
    }
    result
}

fn decode_hex_32(value: &str) -> Result<[u8; 32], EventStoreError> {
    if value.len() != 64 {
        return Err(EventStoreError::InvalidRecordSignature);
    }
    let mut bytes = [0_u8; 32];
    for (index, pair) in value.as_bytes().chunks_exact(2).enumerate() {
        let high = decode_hex_nibble(pair[0])?;
        let low = decode_hex_nibble(pair[1])?;
        bytes[index] = (high << 4) | low;
    }
    Ok(bytes)
}

fn decode_hex_nibble(value: u8) -> Result<u8, EventStoreError> {
    match value {
        b'0'..=b'9' => Ok(value - b'0'),
        b'a'..=b'f' => Ok(value - b'a' + 10),
        _ => Err(EventStoreError::InvalidRecordSignature),
    }
}

fn create_private_file(path: &Path) -> Result<(), EventStoreError> {
    open_private_file(path, true)?.sync_all()?;
    Ok(())
}

fn create_new_private_file(path: &Path) -> Result<File, EventStoreError> {
    let mut options = OpenOptions::new();
    options.create_new(true).read(true).write(true);
    configure_private_open_options(&mut options, true);
    let file = options.open(path)?;
    validate_private_file(&file, path)?;
    Ok(file)
}

fn open_private_file(path: &Path, create: bool) -> Result<File, EventStoreError> {
    reject_symlink(path)?;
    let mut options = OpenOptions::new();
    options.read(true).write(true).create(create);
    configure_private_open_options(&mut options, create);
    let file = options.open(path)?;
    validate_private_file(&file, path)?;
    Ok(file)
}

fn open_private_append_file(path: &Path) -> Result<File, EventStoreError> {
    reject_symlink(path)?;
    let mut options = OpenOptions::new();
    options.read(true).append(true);
    configure_private_open_options(&mut options, false);
    let file = options.open(path)?;
    validate_private_file(&file, path)?;
    Ok(file)
}

fn configure_private_open_options(options: &mut OpenOptions, creating: bool) {
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        if creating {
            options.mode(0o600);
        }
        options.custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW);
    }
}

fn prepare_private_directory(path: &Path) -> Result<(), EventStoreError> {
    match fs::symlink_metadata(path) {
        Ok(metadata) => {
            if metadata.file_type().is_symlink() || !metadata.is_dir() {
                return Err(EventStoreError::UnsafePath(path.to_path_buf()));
            }
            validate_owner(&metadata, path)?;
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            fs::create_dir_all(path)?;
            let metadata = fs::symlink_metadata(path)?;
            if metadata.file_type().is_symlink() || !metadata.is_dir() {
                return Err(EventStoreError::UnsafePath(path.to_path_buf()));
            }
            validate_owner(&metadata, path)?;
        }
        Err(error) => return Err(EventStoreError::Io(error)),
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
    }
    Ok(())
}

fn reject_symlink(path: &Path) -> Result<(), EventStoreError> {
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_symlink() => {
            Err(EventStoreError::UnsafePath(path.to_path_buf()))
        }
        Ok(_) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(EventStoreError::Io(error)),
    }
}

fn validate_private_file(file: &File, path: &Path) -> Result<(), EventStoreError> {
    let metadata = file.metadata()?;
    if !metadata.is_file() {
        return Err(EventStoreError::UnsafePath(path.to_path_buf()));
    }
    validate_owner(&metadata, path)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        file.set_permissions(fs::Permissions::from_mode(0o600))?;
    }
    Ok(())
}

fn validate_owner(metadata: &fs::Metadata, path: &Path) -> Result<(), EventStoreError> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        // rustix exposes the effective UID through a safe, typed wrapper.
        let effective_uid = rustix::process::geteuid().as_raw();
        if metadata.uid() != effective_uid {
            return Err(EventStoreError::WrongOwner(path.to_path_buf()));
        }
    }
    Ok(())
}

fn sync_directory(path: &Path) -> Result<(), EventStoreError> {
    File::open(path)?.sync_all()?;
    Ok(())
}

#[derive(Debug, Error)]
pub enum EventStoreError {
    #[error("event store I/O failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("event serialization failed: {0}")]
    Serialization(#[from] serde_json::Error),
    #[error("invalid event draft or envelope: {0}")]
    InvalidEnvelope(#[from] EventEnvelopeError),
    #[error("invalid Home authority node id: {0}")]
    InvalidNodeId(IdentifierError),
    #[error("Home authority token must contain at least 32 bytes")]
    WeakAuthorityToken,
    #[error("Home append authentication failed")]
    AuthenticationFailed,
    #[error("invalid Home authority key")]
    InvalidAuthorityKey,
    #[error("authoritative subject sequence overflow")]
    SequenceOverflow,
    #[error("idempotency key was already used for a different event draft")]
    IdempotencyConflict,
    #[error("event store record {line} is corrupt: {reason}")]
    CorruptRecord { line: usize, reason: String },
    #[error("authoritative event source must be control-plane/home, got {0:?}")]
    InvalidAuthoritativeSource(String),
    #[error("record does not carry authoritative append evidence")]
    UntrustedRecord,
    #[error("event authority node does not match configured Home node")]
    AuthorityNodeMismatch,
    #[error("authoritative record signature is missing")]
    MissingRecordSignature,
    #[error("authoritative record draft fingerprint is missing")]
    MissingDraftFingerprint,
    #[error("authoritative record signature is invalid")]
    InvalidRecordSignature,
    #[error("event log has an incomplete tail and must be recovered under an exclusive lock")]
    IncompleteTail,
    #[error("event log head is missing")]
    MissingLogHead,
    #[error("event log head is corrupt or unauthenticated")]
    CorruptLogHead,
    #[error("event log and durable head disagree")]
    LogHeadMismatch,
    #[error("event log rollback or truncation was detected")]
    LogRollbackDetected,
    #[error("event log is too large for this platform")]
    LogTooLarge,
    #[error("unsafe event-store path: {0}")]
    UnsafePath(PathBuf),
    #[error("event-store path is not owned by the current service user: {0}")]
    WrongOwner(PathBuf),
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::events::{EventProvenance, KolibriEvent};
    use serde_json::json;
    use std::process::Command;
    use std::sync::Arc;
    use std::thread;
    use uuid::Uuid;

    const TOKEN: &[u8] = b"0123456789abcdef0123456789abcdef";

    fn test_directory() -> PathBuf {
        std::env::temp_dir().join(format!("kolibri-event-store-{}", Uuid::new_v4()))
    }

    fn draft(idempotency_key: &str) -> EventDraft {
        let mut draft = EventDraft::new(
            KolibriEvent::TaskCreated.as_str(),
            "task:task-001",
            format!("trace:{}", Uuid::new_v4()),
            json!({"task_id":"task-001"}),
            EventProvenance::v1("gateway", "v1"),
            Utc::now(),
        );
        draft.idempotency_key = idempotency_key.to_string();
        draft
    }

    #[test]
    fn append_is_authenticated_home_only_and_durable() {
        let directory = test_directory();
        let authority = HomeAuthorityConfig::new("home-control-plane", TOKEN).unwrap();
        let store = DurableHomeEventStore::open(&directory, authority.clone()).unwrap();
        let credential = HomeAppendCredential::new(TOKEN);

        assert!(matches!(
            store.append(
                draft("task:create:bad"),
                &HomeAppendCredential::new(b"wrong")
            ),
            Err(EventStoreError::AuthenticationFailed)
        ));
        let first = store.append(draft("task:create:1"), &credential).unwrap();
        let second = store.append(draft("task:create:2"), &credential).unwrap();
        assert_eq!(first.source(), HOME_SOURCE);
        assert_eq!(first.sequence(), 1);
        assert_eq!(second.sequence(), 2);
        assert_eq!(
            first.envelope().provenance.node_id.as_deref(),
            Some("home-control-plane")
        );

        let reopened = DurableHomeEventStore::open(&directory, authority).unwrap();
        let third = reopened
            .append(draft("task:create:3"), &credential)
            .unwrap();
        assert_eq!(third.sequence(), 3);
        assert_eq!(reopened.read_verified().unwrap().len(), 3);
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn append_is_idempotent_and_concurrency_safe() {
        let directory = test_directory();
        let authority = HomeAuthorityConfig::new("home-control-plane", TOKEN).unwrap();
        let store = Arc::new(DurableHomeEventStore::open(&directory, authority).unwrap());
        let mut handles = Vec::new();
        for index in 0..12 {
            let store = Arc::clone(&store);
            handles.push(thread::spawn(move || {
                store
                    .append(
                        draft(&format!("task:create:{index}")),
                        &HomeAppendCredential::new(TOKEN),
                    )
                    .unwrap()
                    .sequence()
            }));
        }
        let mut sequences: Vec<u64> = handles
            .into_iter()
            .map(|handle| handle.join().unwrap())
            .collect();
        sequences.sort_unstable();
        assert_eq!(sequences, (1..=12).collect::<Vec<_>>());

        let repeated_draft = draft("task:create:repeat");
        let original = store
            .append(repeated_draft.clone(), &HomeAppendCredential::new(TOKEN))
            .unwrap();
        let repeated = store
            .append(repeated_draft, &HomeAppendCredential::new(TOKEN))
            .unwrap();
        assert_eq!(original, repeated);
        assert_eq!(store.read_verified().unwrap().len(), 13);
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn append_rejects_missing_or_conflicting_idempotency() {
        let directory = test_directory();
        let authority = HomeAuthorityConfig::new("home-control-plane", TOKEN).unwrap();
        let store = DurableHomeEventStore::open(&directory, authority).unwrap();
        let credential = HomeAppendCredential::new(TOKEN);

        let mut missing = draft("");
        missing.idempotency_key.clear();
        assert!(matches!(
            store.append(missing, &credential),
            Err(EventStoreError::InvalidEnvelope(
                EventEnvelopeError::MissingIdempotencyKey
            ))
        ));

        let mut colliding_provenance = draft("task:create:reserved-provenance");
        colliding_provenance
            .provenance
            .extensions
            .insert("node_id".to_string(), json!("forged-home"));
        assert!(matches!(
            store.append(colliding_provenance, &credential),
            Err(EventStoreError::InvalidEnvelope(
                EventEnvelopeError::ReservedProvenanceExtension(_)
            ))
        ));

        let original = draft("task:create:collision");
        store.append(original, &credential).unwrap();
        let mut conflicting = draft("task:create:collision");
        conflicting.subject = "task:other-task".to_string();
        conflicting.payload_json = json!({"task_id":"other-task"});
        assert!(matches!(
            store.append(conflicting, &credential),
            Err(EventStoreError::IdempotencyConflict)
        ));
        assert_eq!(store.read_verified().unwrap().len(), 1);
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn claimed_source_or_tampered_record_never_becomes_verified() {
        let directory = test_directory();
        let authority = HomeAuthorityConfig::new("home-control-plane", TOKEN).unwrap();
        let store = DurableHomeEventStore::open(&directory, authority).unwrap();
        store
            .append(
                draft("task:create:tamper"),
                &HomeAppendCredential::new(TOKEN),
            )
            .unwrap();

        let original = fs::read_to_string(&store.log_path).unwrap();
        let tampered = original.replace("control-plane/home", "control-plane/main");
        fs::write(&store.log_path, tampered).unwrap();
        assert!(matches!(
            store.read_verified(),
            Err(EventStoreError::CorruptRecord { .. })
        ));
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn partial_tail_is_removed_before_restart_continues_sequence() {
        let directory = test_directory();
        let authority = HomeAuthorityConfig::new("home-control-plane", TOKEN).unwrap();
        let store = DurableHomeEventStore::open(&directory, authority.clone()).unwrap();
        let credential = HomeAppendCredential::new(TOKEN);
        store.append(draft("task:create:1"), &credential).unwrap();
        store.append(draft("task:create:2"), &credential).unwrap();
        let mut log = open_private_append_file(&store.log_path).unwrap();
        log.write_all(b"{\"crash\":\"partial").unwrap();
        log.sync_all().unwrap();
        drop(log);
        drop(store);

        let reopened = DurableHomeEventStore::open(&directory, authority).unwrap();
        assert_eq!(reopened.read_verified().unwrap().len(), 2);
        let third = reopened
            .append(draft("task:create:3"), &credential)
            .unwrap();
        assert_eq!(third.sequence(), 3);
        let bytes = fs::read(&reopened.log_path).unwrap();
        assert_eq!(bytes.last(), Some(&b'\n'));
        assert!(!String::from_utf8_lossy(&bytes).contains("crash"));
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn hash_chain_sequence_and_head_detect_reorder_and_truncation() {
        let directory = test_directory();
        let authority = HomeAuthorityConfig::new("home-control-plane", TOKEN).unwrap();
        let store = DurableHomeEventStore::open(&directory, authority.clone()).unwrap();
        let credential = HomeAppendCredential::new(TOKEN);
        for index in 1..=3 {
            store
                .append(draft(&format!("task:create:{index}")), &credential)
                .unwrap();
        }
        let original = fs::read_to_string(&store.log_path).unwrap();
        let lines: Vec<&str> = original.lines().collect();

        fs::write(
            &store.log_path,
            format!("{}\n{}\n{}\n", lines[1], lines[0], lines[2]),
        )
        .unwrap();
        assert!(matches!(
            store.read_verified(),
            Err(EventStoreError::CorruptRecord { .. })
        ));

        fs::write(&store.log_path, format!("{}\n{}\n", lines[0], lines[1])).unwrap();
        assert!(matches!(
            store.read_verified(),
            Err(EventStoreError::LogHeadMismatch)
        ));
        assert!(matches!(
            DurableHomeEventStore::open(&directory, authority),
            Err(EventStoreError::LogRollbackDetected)
        ));
        fs::remove_dir_all(directory).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn existing_permissions_are_repaired_and_symlinks_are_rejected() {
        use std::os::unix::fs::{PermissionsExt, symlink};

        let directory = test_directory();
        fs::create_dir_all(&directory).unwrap();
        fs::write(directory.join("events.v1.jsonl"), b"").unwrap();
        fs::write(directory.join("events.v1.lock"), b"").unwrap();
        fs::set_permissions(&directory, fs::Permissions::from_mode(0o755)).unwrap();
        fs::set_permissions(
            directory.join("events.v1.jsonl"),
            fs::Permissions::from_mode(0o644),
        )
        .unwrap();
        fs::set_permissions(
            directory.join("events.v1.lock"),
            fs::Permissions::from_mode(0o644),
        )
        .unwrap();
        let store = DurableHomeEventStore::open(
            &directory,
            HomeAuthorityConfig::new("home-control-plane", TOKEN).unwrap(),
        )
        .unwrap();
        assert_eq!(
            fs::metadata(&directory).unwrap().permissions().mode() & 0o777,
            0o700
        );
        for path in [&store.log_path, &store.lock_path, &store.head_path] {
            assert_eq!(
                fs::metadata(path).unwrap().permissions().mode() & 0o777,
                0o600
            );
        }
        fs::remove_dir_all(&directory).unwrap();

        let symlink_directory = test_directory();
        fs::create_dir_all(&symlink_directory).unwrap();
        let target = symlink_directory.join("target");
        fs::write(&target, b"").unwrap();
        symlink(&target, symlink_directory.join("events.v1.jsonl")).unwrap();
        assert!(matches!(
            DurableHomeEventStore::open(
                &symlink_directory,
                HomeAuthorityConfig::new("home-control-plane", TOKEN).unwrap()
            ),
            Err(EventStoreError::UnsafePath(_))
        ));
        fs::remove_dir_all(symlink_directory).unwrap();
    }

    #[test]
    fn authority_credentials_never_appear_in_debug() {
        let directory = test_directory();
        let authority = HomeAuthorityConfig::new("home-control-plane", TOKEN).unwrap();
        let credential = HomeAppendCredential::new(TOKEN);
        let store = DurableHomeEventStore::open(&directory, authority.clone()).unwrap();
        let raw_token = String::from_utf8_lossy(TOKEN);
        assert!(!format!("{authority:?}").contains(raw_token.as_ref()));
        assert!(!format!("{credential:?}").contains(raw_token.as_ref()));
        assert!(!format!("{store:?}").contains(raw_token.as_ref()));
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    #[ignore = "helper executed by process_locking_is_cross_process"]
    fn process_append_helper() {
        let Some(directory) = std::env::var_os("KOLIBRI_EVENT_STORE_CHILD_DIR") else {
            return;
        };
        let key = std::env::var("KOLIBRI_EVENT_STORE_CHILD_KEY").unwrap();
        let store = DurableHomeEventStore::open(
            directory,
            HomeAuthorityConfig::new("home-control-plane", TOKEN).unwrap(),
        )
        .unwrap();
        store
            .append(draft(&key), &HomeAppendCredential::new(TOKEN))
            .unwrap();
    }

    #[test]
    fn process_locking_is_cross_process() {
        let directory = test_directory();
        let mut children = Vec::new();
        for index in 0..6 {
            children.push(
                Command::new(std::env::current_exe().unwrap())
                    .args([
                        "--ignored",
                        "--exact",
                        "event_store::tests::process_append_helper",
                        "--nocapture",
                    ])
                    .env("KOLIBRI_EVENT_STORE_CHILD_DIR", &directory)
                    .env(
                        "KOLIBRI_EVENT_STORE_CHILD_KEY",
                        format!("task:process:{index}"),
                    )
                    .spawn()
                    .unwrap(),
            );
        }
        for mut child in children {
            assert!(child.wait().unwrap().success());
        }
        let store = DurableHomeEventStore::open(
            &directory,
            HomeAuthorityConfig::new("home-control-plane", TOKEN).unwrap(),
        )
        .unwrap();
        let events = store.read_verified().unwrap();
        assert_eq!(events.len(), 6);
        let mut sequences: Vec<_> = events.iter().map(VerifiedEventEnvelope::sequence).collect();
        sequences.sort_unstable();
        assert_eq!(sequences, (1..=6).collect::<Vec<_>>());
        fs::remove_dir_all(directory).unwrap();
    }
}
