use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Component, Path, PathBuf};

use ed25519_dalek::{Signature, VerifyingKey};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
#[cfg(unix)]
use std::os::unix::fs::MetadataExt;

use crate::error::{ExecutorError, Result};
use crate::guard_evidence::{self, GuardEvidenceAssessment, GuardEvidencePolicy};
use crate::model::{ProtectionScope, REQUIRED_PROTECTION_SCOPES, RootKind};

const MAX_POLICY_BYTES: u64 = 256 * 1024;
const MIN_PREVIEW_TTL_SECONDS: u64 = 60;
const MAX_PREVIEW_TTL_SECONDS: u64 = 15 * 60;
const MIN_QUARANTINE_RETENTION_SECONDS: u64 = 7 * 24 * 60 * 60;
const MAX_CANDIDATES: u64 = 10_000;
const MAX_BYTES_PER_OPERATION: u64 = 10 * 1024 * 1024 * 1024 * 1024;
const MAX_SCAN_ENTRIES: u64 = 1_000_000;
const MAX_SCAN_DEPTH: u32 = 64;
const MAX_REQUEST_BYTES: u64 = 256 * 1024;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SignedPolicy {
    pub policy: Policy,
    pub signature_hex: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Policy {
    pub policy_version: String,
    pub protocol_version: String,
    pub node_id: String,
    pub execute_enabled: bool,
    pub preview_ttl_seconds: u64,
    pub quarantine_retention_seconds: u64,
    pub limits: Limits,
    pub capacity_topology: Option<CapacityTopologyPolicy>,
    #[serde(default)]
    pub guard_evidence: Option<GuardEvidencePolicy>,
    pub roots: Vec<RootPolicy>,
    pub guards: Vec<GuardPolicy>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CapacityTopologyPolicy {
    pub lvm_backup_path: PathBuf,
    pub root_lv_name: String,
    pub root_display_name: String,
    pub reserve_display_name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Limits {
    pub max_candidates: u64,
    pub max_bytes_per_operation: u64,
    pub max_scan_entries: u64,
    pub max_scan_depth: u32,
    pub max_request_bytes: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RootPolicy {
    pub root_id: String,
    pub kind: RootKind,
    pub path: PathBuf,
    pub minimum_age_seconds: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct GuardPolicy {
    pub scope: ProtectionScope,
    pub paths: Vec<PathBuf>,
}

#[derive(Debug, Clone)]
pub struct VerifiedPolicy {
    pub policy: Policy,
    pub digest: String,
    root_index: HashMap<String, usize>,
    root_identities: HashMap<String, RootIdentity>,
    test_execution_authority: bool,
}

#[derive(Debug, Clone, Copy)]
struct RootIdentity {
    device: u64,
    inode: u64,
}

impl VerifiedPolicy {
    pub fn load(path: &Path, public_key_hex: &str) -> Result<Self> {
        let metadata = fs::symlink_metadata(path).map_err(|_| {
            ExecutorError::rejected(
                "policy_unavailable",
                "The signed storage policy is unavailable.",
            )
        })?;
        if !metadata.is_file()
            || metadata.file_type().is_symlink()
            || metadata.len() > MAX_POLICY_BYTES
        {
            return Err(ExecutorError::rejected(
                "policy_invalid",
                "The signed storage policy is invalid.",
            ));
        }
        let body = fs::read(path)?;
        let signed: SignedPolicy = serde_json::from_slice(&body).map_err(|_| {
            ExecutorError::rejected("policy_invalid", "The signed storage policy is invalid.")
        })?;
        Self::verify(signed, public_key_hex)
    }

    pub fn verify(signed: SignedPolicy, public_key_hex: &str) -> Result<Self> {
        let public_key_bytes = decode_fixed_hex::<32>(public_key_hex, "policy_public_key_invalid")?;
        let signature_bytes =
            decode_fixed_hex::<64>(&signed.signature_hex, "policy_signature_invalid")?;
        let verifying_key = VerifyingKey::from_bytes(&public_key_bytes).map_err(|_| {
            ExecutorError::rejected(
                "policy_public_key_invalid",
                "The policy verification key is invalid.",
            )
        })?;
        let signature = Signature::from_bytes(&signature_bytes);
        let canonical = serde_json::to_vec(&signed.policy)?;
        verifying_key
            .verify_strict(&canonical, &signature)
            .map_err(|_| {
                ExecutorError::rejected(
                    "policy_signature_invalid",
                    "The storage policy signature is invalid.",
                )
            })?;
        validate_policy(&signed.policy)?;
        let digest = hex::encode(Sha256::digest(&canonical));
        let root_index = signed
            .policy
            .roots
            .iter()
            .enumerate()
            .map(|(index, root)| (root.root_id.clone(), index))
            .collect();
        let root_identities = signed
            .policy
            .roots
            .iter()
            .map(|root| {
                let metadata = fs::metadata(&root.path)?;
                Ok((
                    root.root_id.clone(),
                    RootIdentity {
                        #[cfg(unix)]
                        device: metadata.dev(),
                        #[cfg(unix)]
                        inode: metadata.ino(),
                        #[cfg(not(unix))]
                        device: 0,
                        #[cfg(not(unix))]
                        inode: 0,
                    },
                ))
            })
            .collect::<std::io::Result<HashMap<_, _>>>()?;
        Ok(Self {
            policy: signed.policy,
            digest,
            root_index,
            root_identities,
            test_execution_authority: false,
        })
    }

    pub fn root(&self, root_id: &str) -> Result<&RootPolicy> {
        self.root_index
            .get(root_id)
            .and_then(|index| self.policy.roots.get(*index))
            .ok_or_else(|| {
                ExecutorError::rejected(
                    "root_not_allowlisted",
                    "The requested storage root is not allowlisted.",
                )
            })
    }

    pub fn roots_of_kind(&self, kind: RootKind) -> impl Iterator<Item = &RootPolicy> {
        self.policy
            .roots
            .iter()
            .filter(move |root| root.kind == kind)
    }

    pub(crate) fn guard_evidence(&self, now: u64) -> GuardEvidenceAssessment {
        #[cfg(test)]
        if self.test_execution_authority {
            return GuardEvidenceAssessment::test_only();
        }
        self.policy
            .guard_evidence
            .as_ref()
            .map_or_else(GuardEvidenceAssessment::disabled, |policy| {
                guard_evidence::assess(policy, now)
            })
    }

    pub fn execution_authorized(&self) -> bool {
        self.test_execution_authority && self.policy.execute_enabled
    }

    #[cfg(test)]
    pub(crate) fn enable_test_execution(&mut self) {
        self.test_execution_authority = true;
    }

    pub(crate) fn path_is_guarded(
        &self,
        evidence: &GuardEvidenceAssessment,
        candidate: &Path,
    ) -> Result<bool> {
        let candidate_resolved = fs::canonicalize(candidate).map_err(|_| {
            ExecutorError::rejected(
                "guard_evidence_unavailable",
                "A storage candidate could not be resolved for guard checks.",
            )
        })?;
        for guard in &self.policy.guards {
            for guarded in &guard.paths {
                let guarded_resolved = fs::canonicalize(guarded).map_err(|_| {
                    ExecutorError::rejected(
                        "guard_evidence_unavailable",
                        "A required protected path is missing or stale.",
                    )
                })?;
                if candidate == guarded
                    || candidate.starts_with(guarded)
                    || guarded.starts_with(candidate)
                    || candidate_resolved == guarded_resolved
                    || candidate_resolved.starts_with(&guarded_resolved)
                    || guarded_resolved.starts_with(&candidate_resolved)
                {
                    return Ok(true);
                }
            }
        }
        Ok(evidence.path_is_guarded(&candidate_resolved))
    }

    pub(crate) fn assert_root_identity(&self, root: &RootPolicy) -> Result<()> {
        let expected = self
            .root_identities
            .get(&root.root_id)
            .ok_or_else(policy_invalid)?;
        let metadata = fs::symlink_metadata(&root.path).map_err(|_| {
            ExecutorError::rejected(
                "root_changed",
                "An allowlisted storage root changed identity.",
            )
        })?;
        #[cfg(unix)]
        let matches = metadata.is_dir()
            && !metadata.file_type().is_symlink()
            && metadata.dev() == expected.device
            && metadata.ino() == expected.inode;
        #[cfg(not(unix))]
        let matches = false;
        if !matches {
            return Err(ExecutorError::rejected(
                "root_changed",
                "An allowlisted storage root changed identity.",
            ));
        }
        Ok(())
    }
}

fn decode_fixed_hex<const N: usize>(value: &str, code: &'static str) -> Result<[u8; N]> {
    let bytes = hex::decode(value)
        .map_err(|_| ExecutorError::rejected(code, "A cryptographic policy field is invalid."))?;
    bytes
        .try_into()
        .map_err(|_| ExecutorError::rejected(code, "A cryptographic policy field is invalid."))
}

fn validate_policy(policy: &Policy) -> Result<()> {
    if !valid_opaque(&policy.policy_version, 3, 64)
        || policy.protocol_version != crate::model::PROTOCOL_V1
        || !matches!(policy.node_id.as_str(), "home" | "primary")
    {
        return Err(policy_invalid());
    }
    match (&*policy.node_id, &policy.capacity_topology) {
        ("home", Some(topology)) => {
            if !literal_absolute(&topology.lvm_backup_path)
                || !valid_opaque(&topology.root_lv_name, 1, 64)
                || !safe_display_name(&topology.root_display_name)
                || !safe_display_name(&topology.reserve_display_name)
            {
                return Err(policy_invalid());
            }
        }
        ("primary", None) => {}
        _ => return Err(policy_invalid()),
    }
    if !(MIN_PREVIEW_TTL_SECONDS..=MAX_PREVIEW_TTL_SECONDS).contains(&policy.preview_ttl_seconds)
        || policy.quarantine_retention_seconds < MIN_QUARANTINE_RETENTION_SECONDS
        || policy.limits.max_candidates == 0
        || policy.limits.max_candidates > MAX_CANDIDATES
        || policy.limits.max_bytes_per_operation == 0
        || policy.limits.max_bytes_per_operation > MAX_BYTES_PER_OPERATION
        || policy.limits.max_scan_entries == 0
        || policy.limits.max_scan_entries > MAX_SCAN_ENTRIES
        || policy.limits.max_scan_depth == 0
        || policy.limits.max_scan_depth > MAX_SCAN_DEPTH
        || policy.limits.max_request_bytes < 1024
        || policy.limits.max_request_bytes > MAX_REQUEST_BYTES
    {
        return Err(policy_invalid());
    }
    if policy
        .guard_evidence
        .as_ref()
        .is_some_and(|evidence| !guard_evidence::validate_policy(evidence))
    {
        return Err(policy_invalid());
    }
    if policy.roots.is_empty() || policy.roots.len() > 64 {
        return Err(policy_invalid());
    }

    let mut ids = HashSet::new();
    let mut paths: Vec<&Path> = Vec::new();
    let mut project_source_count = 0;
    let mut quarantine_count = 0;
    for root in &policy.roots {
        if !valid_opaque(&root.root_id, 3, 64)
            || !ids.insert(root.root_id.as_str())
            || !literal_absolute(&root.path)
        {
            return Err(policy_invalid());
        }
        if root.kind == RootKind::ProjectSource {
            project_source_count += 1;
        }
        if root.kind == RootKind::ProjectQuarantine {
            quarantine_count += 1;
        }
        let metadata = fs::symlink_metadata(&root.path).map_err(|_| policy_invalid())?;
        if !metadata.is_dir()
            || metadata.file_type().is_symlink()
            || path_has_symlink_component(&root.path)
        {
            return Err(policy_invalid());
        }
        if paths
            .iter()
            .any(|other| root.path.starts_with(other) || other.starts_with(&root.path))
        {
            return Err(policy_invalid());
        }
        paths.push(&root.path);
    }
    if project_source_count > 1
        || quarantine_count > 1
        || (project_source_count == 0) != (quarantine_count == 0)
    {
        return Err(policy_invalid());
    }
    if policy.guard_evidence.as_ref().is_some_and(|evidence| {
        guard_evidence::policy_file_paths(evidence)
            .iter()
            .any(|path| {
                policy
                    .roots
                    .iter()
                    .any(|root| path.starts_with(&root.path) || root.path.starts_with(path))
            })
    }) {
        return Err(policy_invalid());
    }

    let mut scopes = HashSet::new();
    if policy.guards.len() != REQUIRED_PROTECTION_SCOPES.len() {
        return Err(policy_invalid());
    }
    for guard in &policy.guards {
        if !scopes.insert(guard.scope) || guard.paths.is_empty() || guard.paths.len() > 64 {
            return Err(policy_invalid());
        }
        for path in &guard.paths {
            if !literal_absolute(path) {
                return Err(policy_invalid());
            }
        }
    }
    if REQUIRED_PROTECTION_SCOPES
        .iter()
        .any(|required| !scopes.contains(required))
    {
        return Err(policy_invalid());
    }

    if project_source_count == 1 {
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt;
            let source = policy
                .roots
                .iter()
                .find(|root| root.kind == RootKind::ProjectSource)
                .ok_or_else(policy_invalid)?;
            let quarantine = policy
                .roots
                .iter()
                .find(|root| root.kind == RootKind::ProjectQuarantine)
                .ok_or_else(policy_invalid)?;
            if fs::metadata(&source.path)?.dev() != fs::metadata(&quarantine.path)?.dev() {
                return Err(ExecutorError::rejected(
                    "quarantine_cross_filesystem",
                    "Project quarantine must use the same filesystem.",
                ));
            }
        }
        #[cfg(not(unix))]
        {
            return Err(ExecutorError::rejected(
                "platform_unsupported",
                "The storage executor requires a Unix node.",
            ));
        }
    }
    Ok(())
}

fn literal_absolute(path: &Path) -> bool {
    path.is_absolute()
        && path
            .components()
            .all(|component| matches!(component, Component::RootDir | Component::Normal(_)))
}

fn path_has_symlink_component(path: &Path) -> bool {
    let mut current = PathBuf::new();
    for component in path.components() {
        current.push(component.as_os_str());
        if component == Component::RootDir {
            continue;
        }
        match fs::symlink_metadata(&current) {
            Ok(metadata) if metadata.file_type().is_symlink() => return true,
            Ok(_) => {}
            Err(_) => return true,
        }
    }
    false
}

pub(crate) fn valid_opaque(value: &str, minimum: usize, maximum: usize) -> bool {
    let bytes = value.as_bytes();
    (minimum..=maximum).contains(&bytes.len())
        && bytes[0].is_ascii_alphanumeric()
        && bytes
            .iter()
            .all(|byte| byte.is_ascii_alphanumeric() || b"._:-~".contains(byte))
}

pub(crate) fn valid_project_id(value: &str) -> bool {
    valid_opaque(value, 3, 160) && !value.contains(':')
}

pub(crate) fn valid_operation_id(value: &str) -> bool {
    value
        .strip_prefix("sop_")
        .is_some_and(|suffix| suffix.len() == 32 && suffix.bytes().all(lowercase_hex))
}

fn safe_display_name(value: &str) -> bool {
    let trimmed = value.trim();
    !trimmed.is_empty()
        && trimmed.len() <= 64
        && !trimmed.contains('/')
        && !trimmed.contains('\\')
        && trimmed.chars().all(|character| !character.is_control())
}

pub(crate) fn valid_quarantine_id(value: &str) -> bool {
    value
        .strip_prefix("sqn_")
        .is_some_and(|suffix| suffix.len() == 32 && suffix.bytes().all(lowercase_hex))
}

fn lowercase_hex(byte: u8) -> bool {
    byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)
}

fn policy_invalid() -> ExecutorError {
    ExecutorError::rejected("policy_invalid", "The signed storage policy is invalid.")
}

#[cfg(test)]
mod tests {
    use std::fs;

    use ed25519_dalek::{Signer, SigningKey};
    use tempfile::TempDir;

    use super::*;

    fn policy(temp: &TempDir) -> Policy {
        let cache = temp.path().join("cache");
        fs::create_dir(&cache).unwrap();
        Policy {
            policy_version: "policy-1".into(),
            protocol_version: "v1".into(),
            node_id: "home".into(),
            execute_enabled: false,
            preview_ttl_seconds: 300,
            quarantine_retention_seconds: MIN_QUARANTINE_RETENTION_SECONDS,
            limits: Limits {
                max_candidates: 100,
                max_bytes_per_operation: 1_000_000,
                max_scan_entries: 1_000,
                max_scan_depth: 16,
                max_request_bytes: 65_536,
            },
            capacity_topology: None,
            guard_evidence: None,
            roots: vec![RootPolicy {
                root_id: "cache-main".into(),
                kind: RootKind::Cache,
                path: cache,
                minimum_age_seconds: 0,
            }],
            guards: REQUIRED_PROTECTION_SCOPES
                .into_iter()
                .map(|scope| GuardPolicy {
                    scope,
                    paths: vec![temp.path().join(format!("guard-{scope:?}"))],
                })
                .collect(),
        }
    }

    #[test]
    fn detects_policy_tampering() {
        let temp = TempDir::new().unwrap();
        let signing_key = SigningKey::from_bytes(&[7_u8; 32]);
        let mut signed = SignedPolicy {
            policy: policy(&temp),
            signature_hex: String::new(),
        };
        signed.signature_hex = hex::encode(
            signing_key
                .sign(&serde_json::to_vec(&signed.policy).unwrap())
                .to_bytes(),
        );
        signed.policy.execute_enabled = true;

        let error =
            VerifiedPolicy::verify(signed, &hex::encode(signing_key.verifying_key().to_bytes()))
                .unwrap_err();
        assert_eq!(error.code(), "policy_signature_invalid");
    }

    #[test]
    fn rejects_non_literal_root() {
        let temp = TempDir::new().unwrap();
        let signing_key = SigningKey::from_bytes(&[8_u8; 32]);
        let mut raw = policy(&temp);
        raw.roots[0].path = temp.path().join("cache").join("..").join("cache");
        let signature = signing_key.sign(&serde_json::to_vec(&raw).unwrap());
        let signed = SignedPolicy {
            policy: raw,
            signature_hex: hex::encode(signature.to_bytes()),
        };
        assert_eq!(
            VerifiedPolicy::verify(signed, &hex::encode(signing_key.verifying_key().to_bytes()))
                .unwrap_err()
                .code(),
            "policy_invalid"
        );
    }

    #[test]
    fn opaque_ids_require_lowercase_hex() {
        assert!(valid_operation_id(&format!("sop_{}", "a1".repeat(16))));
        assert!(valid_quarantine_id(&format!("sqn_{}", "b2".repeat(16))));
        assert!(!valid_operation_id(&format!("sop_{}", "A1".repeat(16))));
        assert!(!valid_quarantine_id(&format!("sqn_{}", "B2".repeat(16))));
    }
}
