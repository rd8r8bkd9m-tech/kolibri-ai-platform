use std::collections::HashSet;
use std::fs;
use std::fs::OpenOptions;
use std::io::Read;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Component, Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::policy::valid_opaque;

const MAX_EVIDENCE_FILE_BYTES: u64 = 1024 * 1024;
const MAX_EVIDENCE_TOTAL_BYTES: u64 = 8 * 1024 * 1024;
const MAX_EVIDENCE_FILES: usize = 128;
const MAX_DOCKER_SNAPSHOT_AGE_SECONDS: u64 = 15 * 60;
const MAX_CLOCK_SKEW_SECONDS: u64 = 60;
const MAX_REFERENCED_PATHS: usize = 4096;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct GuardEvidencePolicy {
    pub max_file_bytes: u64,
    pub max_total_bytes: u64,
    pub docker_snapshot_max_age_seconds: u64,
    pub systemd: FileEvidencePolicy,
    pub nginx: FileEvidencePolicy,
    pub cron: FileEvidencePolicy,
    pub compose: FileEvidencePolicy,
    pub docker: DockerEvidencePolicy,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct FileEvidencePolicy {
    pub generation: String,
    pub files: Vec<EvidenceFilePolicy>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct EvidenceFilePolicy {
    pub path: PathBuf,
    pub sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct DockerEvidencePolicy {
    pub generation: String,
    pub daemon_identity: String,
    pub metadata: EvidenceFilePolicy,
}

#[derive(Debug, Clone)]
pub(crate) enum GuardEvidenceAssessment {
    NonAuthorizing,
    #[cfg(test)]
    TestOnly,
}

impl GuardEvidenceAssessment {
    pub(crate) fn disabled() -> Self {
        Self::NonAuthorizing
    }

    pub(crate) fn incomplete() -> Self {
        Self::NonAuthorizing
    }

    #[cfg(test)]
    pub(crate) fn test_only() -> Self {
        Self::TestOnly
    }

    pub(crate) fn authorizes_actions(&self) -> bool {
        #[cfg(test)]
        if matches!(self, Self::TestOnly) {
            return true;
        }
        false
    }

    pub(crate) fn guarded_scopes(&self) -> Vec<crate::model::ProtectionScope> {
        Vec::new()
    }

    pub(crate) fn path_is_guarded(&self, candidate: &Path) -> bool {
        let _ = candidate;
        !self.authorizes_actions()
    }
}

pub(crate) fn validate_policy(policy: &GuardEvidencePolicy) -> bool {
    if policy.max_file_bytes == 0
        || policy.max_file_bytes > MAX_EVIDENCE_FILE_BYTES
        || policy.max_total_bytes < policy.max_file_bytes
        || policy.max_total_bytes > MAX_EVIDENCE_TOTAL_BYTES
        || policy.docker_snapshot_max_age_seconds == 0
        || policy.docker_snapshot_max_age_seconds > MAX_DOCKER_SNAPSHOT_AGE_SECONDS
    {
        return false;
    }
    let providers = [
        &policy.systemd,
        &policy.nginx,
        &policy.cron,
        &policy.compose,
    ];
    if providers
        .iter()
        .any(|provider| !valid_file_provider(provider))
        || !valid_opaque(&policy.docker.generation, 1, 128)
        || !valid_opaque(&policy.docker.daemon_identity, 1, 256)
        || !valid_evidence_file(&policy.docker.metadata)
    {
        return false;
    }
    let total_files = providers
        .iter()
        .map(|provider| provider.files.len())
        .sum::<usize>()
        + 1;
    total_files <= MAX_EVIDENCE_FILES
}

pub(crate) fn policy_file_paths(policy: &GuardEvidencePolicy) -> Vec<&Path> {
    policy
        .systemd
        .files
        .iter()
        .chain(&policy.nginx.files)
        .chain(&policy.cron.files)
        .chain(&policy.compose.files)
        .map(|file| file.path.as_path())
        .chain(std::iter::once(policy.docker.metadata.path.as_path()))
        .collect()
}

fn valid_file_provider(provider: &FileEvidencePolicy) -> bool {
    if !valid_opaque(&provider.generation, 1, 128)
        || provider.files.is_empty()
        || provider.files.len() > MAX_EVIDENCE_FILES
    {
        return false;
    }
    let mut paths = HashSet::new();
    provider
        .files
        .iter()
        .all(|file| valid_evidence_file(file) && paths.insert(&file.path))
}

fn valid_evidence_file(file: &EvidenceFilePolicy) -> bool {
    literal_absolute(&file.path)
        && file.sha256.len() == 64
        && file.sha256.bytes().all(|byte| byte.is_ascii_hexdigit())
}

pub(crate) fn assess(policy: &GuardEvidencePolicy, now: u64) -> GuardEvidenceAssessment {
    // Enumerated files are parser groundwork, not an exhaustive live
    // configuration/daemon-generation attestation. Inspection deliberately
    // never grants authority.
    let _ = inspect_enumerated_evidence(policy, now);
    GuardEvidenceAssessment::incomplete()
}

fn inspect_enumerated_evidence(policy: &GuardEvidencePolicy, now: u64) -> Option<()> {
    let mut budget = ReadBudget {
        maximum_file: policy.max_file_bytes,
        maximum_total: policy.max_total_bytes,
        total: 0,
    };
    let systemd = inspect_files(&policy.systemd, &mut budget, parse_systemd)?;
    let nginx = inspect_files(&policy.nginx, &mut budget, parse_nginx)?;
    let cron = inspect_files(&policy.cron, &mut budget, parse_cron)?;
    let compose = inspect_files(&policy.compose, &mut budget, parse_compose)?;
    let compose_digest = aggregate_digest(&policy.compose.files);
    let docker = inspect_docker(
        &policy.docker,
        &policy.compose,
        &compose_digest,
        now,
        policy.docker_snapshot_max_age_seconds,
        &mut budget,
    )?;

    let mut paths = Vec::new();
    for provider_paths in [systemd, nginx, cron, compose, docker] {
        paths.extend(provider_paths);
    }
    let mut resolved_paths = Vec::with_capacity(paths.len());
    for path in &paths {
        resolved_paths.push(fs::canonicalize(path).ok()?);
    }
    paths.extend(resolved_paths);
    paths.sort();
    paths.dedup();
    if paths.len() > MAX_REFERENCED_PATHS {
        return None;
    }
    Some(())
}

struct ReadBudget {
    maximum_file: u64,
    maximum_total: u64,
    total: u64,
}

fn inspect_files(
    provider: &FileEvidencePolicy,
    budget: &mut ReadBudget,
    parser: fn(&str) -> Option<Vec<PathBuf>>,
) -> Option<Vec<PathBuf>> {
    let mut paths = Vec::new();
    for file in &provider.files {
        let bytes = read_owned_evidence_file(file, budget)?;
        let text = std::str::from_utf8(&bytes).ok()?;
        paths.extend(parser(text)?);
        if paths.len() > MAX_REFERENCED_PATHS {
            return None;
        }
    }
    Some(paths)
}

fn read_owned_evidence_file(file: &EvidenceFilePolicy, budget: &mut ReadBudget) -> Option<Vec<u8>> {
    if !literal_absolute(&file.path) || path_has_symlink_component(&file.path) {
        return None;
    }
    let opened = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
        .open(&file.path)
        .ok()?;
    let metadata = opened.metadata().ok()?;
    if !secure_evidence_metadata(&metadata, budget.maximum_file) {
        return None;
    }
    budget.total = budget.total.checked_add(metadata.len())?;
    if budget.total > budget.maximum_total {
        return None;
    }
    let mut bytes = Vec::with_capacity(metadata.len() as usize);
    opened
        .take(budget.maximum_file.saturating_add(1))
        .read_to_end(&mut bytes)
        .ok()?;
    if bytes.len() as u64 != metadata.len()
        || hex::encode(Sha256::digest(&bytes)).to_lowercase() != file.sha256.to_lowercase()
    {
        return None;
    }
    Some(bytes)
}

fn secure_evidence_metadata(metadata: &fs::Metadata, maximum_file: u64) -> bool {
    let mode = metadata.permissions().mode();
    metadata.is_file()
        && !metadata.file_type().is_symlink()
        && metadata.uid() == 0
        && mode & 0o022 == 0
        && mode & 0o7111 == 0
        && metadata.len() > 0
        && metadata.len() <= maximum_file
}

fn parse_systemd(text: &str) -> Option<Vec<PathBuf>> {
    let mut paths = Vec::new();
    for raw in text.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') || line.starts_with(';') {
            continue;
        }
        if line.ends_with('\\') || line.contains('\0') {
            return None;
        }
        if line.starts_with('[') {
            if !line.ends_with(']') {
                return None;
            }
            continue;
        }
        let (key, value) = line.split_once('=')?;
        if key.trim().is_empty() {
            return None;
        }
        let key = key.trim();
        if path_bearing_systemd_key(key) {
            paths.extend(extract_literal_paths(value)?);
        } else if let Some(prefix) = systemd_managed_directory_prefix(key) {
            for name in value.split_whitespace() {
                if name.starts_with('/') || name.contains(['$', '%', '/', '\\']) {
                    return None;
                }
                paths.push(prefix.join(name));
            }
        } else if unknown_path_bearing_directive(key, value) {
            return None;
        }
    }
    Some(paths)
}

fn path_bearing_systemd_key(key: &str) -> bool {
    matches!(
        key,
        "ExecStart"
            | "ExecStartPre"
            | "ExecStartPost"
            | "ExecReload"
            | "ExecStop"
            | "ExecStopPost"
            | "WorkingDirectory"
            | "RootDirectory"
            | "RootImage"
            | "ReadWritePaths"
            | "ReadOnlyPaths"
            | "InaccessiblePaths"
            | "BindPaths"
            | "BindReadOnlyPaths"
            | "EnvironmentFile"
            | "ExecSearchPath"
            | "StandardInput"
            | "StandardOutput"
            | "StandardError"
            | "LoadCredential"
            | "LoadCredentialEncrypted"
            | "SetCredential"
            | "SetCredentialEncrypted"
            | "TemporaryFileSystem"
            | "MountImages"
            | "ExtensionImages"
    )
}

fn systemd_managed_directory_prefix(key: &str) -> Option<&'static Path> {
    match key {
        "StateDirectory" => Some(Path::new("/var/lib")),
        "CacheDirectory" => Some(Path::new("/var/cache")),
        "LogsDirectory" => Some(Path::new("/var/log")),
        "RuntimeDirectory" => Some(Path::new("/run")),
        "ConfigurationDirectory" => Some(Path::new("/etc")),
        _ => None,
    }
}

fn unknown_path_bearing_directive(key: &str, value: &str) -> bool {
    let normalized = key.to_ascii_lowercase();
    normalized.contains("path")
        || normalized.contains("directory")
        || normalized.contains("file")
        || normalized.contains("image")
        || normalized.contains("credential")
        || value
            .split_whitespace()
            .any(|token| token.contains('/') || token.starts_with('.'))
}

fn parse_nginx(text: &str) -> Option<Vec<PathBuf>> {
    if text.contains('\0') {
        return None;
    }
    let without_comments = strip_hash_comments(text)?;
    let tokens = tokenize_config(&without_comments)?;
    let mut paths = Vec::new();
    let mut directive: Vec<String> = Vec::new();
    for token in tokens {
        match token.as_str() {
            ";" | "{" | "}" => {
                if directive.first().is_some_and(|value| value == "include") {
                    // Includes must be flattened and individually digest-bound
                    // by the signed evidence policy.
                    return None;
                }
                if directive
                    .first()
                    .is_some_and(|value| nginx_path_directive(value))
                {
                    for value in directive.iter().skip(1) {
                        paths.extend(extract_literal_paths(value)?);
                    }
                } else if let Some(key) = directive.first() {
                    if nginx_unknown_path_bearing(key, &directive[1..]) {
                        return None;
                    }
                }
                directive.clear();
            }
            _ => directive.push(token),
        }
    }
    if !directive.is_empty() {
        return None;
    }
    Some(paths)
}

fn nginx_unknown_path_bearing(key: &str, values: &[String]) -> bool {
    let normalized = key.to_ascii_lowercase();
    normalized.ends_with("_file")
        || normalized.ends_with("_path")
        || normalized.ends_with("_certificate")
        || normalized.ends_with("_log")
        || normalized.contains("_temp_")
        || values
            .iter()
            .any(|value| value.contains('/') || value.starts_with('.'))
}

fn nginx_path_directive(value: &str) -> bool {
    matches!(
        value,
        "root"
            | "alias"
            | "access_log"
            | "error_log"
            | "pid"
            | "ssl_certificate"
            | "ssl_certificate_key"
            | "ssl_client_certificate"
            | "ssl_trusted_certificate"
            | "client_body_temp_path"
            | "proxy_temp_path"
            | "fastcgi_temp_path"
            | "uwsgi_temp_path"
            | "scgi_temp_path"
            | "auth_basic_user_file"
    )
}

fn parse_cron(text: &str) -> Option<Vec<PathBuf>> {
    let mut paths = Vec::new();
    for raw in text.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some((name, value)) = line.split_once('=') {
            if !name.contains(char::is_whitespace) {
                if value.contains('$') || value.contains('`') {
                    return None;
                }
                paths.extend(extract_literal_paths(value)?);
                continue;
            }
        }
        if line.starts_with('@') {
            return None;
        }
        let fields = line.split_whitespace().collect::<Vec<_>>();
        if fields.len() < 6 {
            return None;
        }
        let command_start = if fields[5].starts_with('/') {
            // A six-field user crontab is ambiguous once command arguments
            // are present: there is no signed owner/type metadata here.
            if fields.len() != 6 {
                return None;
            }
            5
        } else {
            if fields.len() < 7 || !valid_cron_user(fields[5]) {
                return None;
            }
            6
        };
        let command = fields[command_start..].join(" ");
        if contains_shell_ambiguity(&command) {
            return None;
        }
        paths.extend(extract_literal_paths(&command)?);
    }
    Some(paths)
}

fn valid_cron_user(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 32
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-'))
}

fn parse_compose(text: &str) -> Option<Vec<PathBuf>> {
    if text.contains('\0')
        || text.contains("${")
        || text.lines().any(|line| {
            let trimmed = line.trim_start();
            trimmed.starts_with("include:")
                || trimmed.starts_with("extends:")
                || trimmed.contains("<<:")
                || trimmed.contains("!include")
                || trimmed.contains('&')
                || trimmed.contains('*')
        })
    {
        return None;
    }
    let without_comments = strip_hash_comments(text)?;
    for raw in without_comments.lines() {
        let line = raw.trim();
        if line.is_empty() {
            continue;
        }
        if line.contains("./") || line.contains("../") {
            return None;
        }
        if let Some((key, raw_value)) = line.split_once(':') {
            let key = key
                .trim()
                .trim_start_matches("- ")
                .trim_matches(['\'', '"']);
            let value = raw_value.trim().trim_matches(['\'', '"']);
            if matches!(
                key,
                "env_file" | "build" | "context" | "dockerfile" | "file"
            ) && (value.is_empty() || !value.starts_with('/'))
            {
                return None;
            }
            if key == "source" && !value.starts_with('/') {
                return None;
            }
        }
        if let Some(value) = line.strip_prefix("- ") {
            let value = value.trim_matches(['\'', '"']);
            if let Some((source, _)) = value.split_once(':') {
                if (source.starts_with('.') || source.contains('/')) && !source.starts_with('/') {
                    return None;
                }
            }
        }
    }
    extract_literal_paths(&without_comments)
}

fn contains_shell_ambiguity(value: &str) -> bool {
    value
        .bytes()
        .any(|byte| b"|;&><$`(){}[]*?~\n\r".contains(&byte))
}

fn extract_literal_paths(value: &str) -> Option<Vec<PathBuf>> {
    if value.contains('\0')
        || value.contains('$')
        || value.contains('%')
        || value.contains('`')
        || value.contains('*')
        || value.contains('?')
    {
        return None;
    }
    let mut paths = Vec::new();
    for raw in value.split(|character: char| {
        character.is_whitespace()
            || matches!(
                character,
                '\'' | '"' | ',' | ';' | '(' | ')' | '[' | ']' | '{' | '}'
            )
    }) {
        let token = raw
            .trim_start_matches(['-', '+', '!', ':'])
            .split_once('=')
            .map_or(raw, |(_, suffix)| suffix);
        for part in token.split(':') {
            let candidate = part.trim_end_matches(['\\', ':']);
            if candidate.starts_with('/') {
                let path = PathBuf::from(candidate);
                if !literal_absolute(&path) {
                    return None;
                }
                paths.push(path);
            }
        }
    }
    Some(paths)
}

fn strip_hash_comments(text: &str) -> Option<String> {
    let mut output = String::with_capacity(text.len());
    for line in text.lines() {
        let mut quote = None;
        for character in line.chars() {
            match (quote, character) {
                (None, '\'' | '"') => quote = Some(character),
                (Some(open), close) if open == close => quote = None,
                (None, '#') => break,
                _ => output.push(character),
            }
        }
        if quote.is_some() {
            return None;
        }
        output.push('\n');
    }
    Some(output)
}

fn tokenize_config(text: &str) -> Option<Vec<String>> {
    let mut tokens = Vec::new();
    let mut current = String::new();
    let mut quote = None;
    for character in text.chars() {
        match (quote, character) {
            (None, '\'' | '"') => quote = Some(character),
            (Some(open), close) if open == close => quote = None,
            (None, ';' | '{' | '}') => {
                if !current.is_empty() {
                    tokens.push(std::mem::take(&mut current));
                }
                tokens.push(character.to_string());
            }
            (None, character) if character.is_whitespace() => {
                if !current.is_empty() {
                    tokens.push(std::mem::take(&mut current));
                }
            }
            _ => current.push(character),
        }
    }
    if quote.is_some() {
        return None;
    }
    if !current.is_empty() {
        tokens.push(current);
    }
    Some(tokens)
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct DockerSnapshot {
    schema_version: String,
    generated_at: u64,
    daemon_identity: String,
    inventory_generation: String,
    inventory_sha256: String,
    compose_evidence_sha256: String,
    containers: Vec<DockerContainer>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct DockerContainer {
    id: String,
    state: DockerContainerState,
    restart_policy: String,
    mounts: Vec<DockerMount>,
    compose_files: Vec<PathBuf>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "kebab-case")]
enum DockerContainerState {
    Created,
    Running,
    Paused,
    Restarting,
    Removing,
    Exited,
    Dead,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct DockerMount {
    source: PathBuf,
    destination: PathBuf,
    mount_type: DockerMountType,
    read_only: bool,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "kebab-case")]
enum DockerMountType {
    Bind,
    Volume,
    Tmpfs,
}

fn inspect_docker(
    policy: &DockerEvidencePolicy,
    compose_policy: &FileEvidencePolicy,
    compose_digest: &str,
    now: u64,
    maximum_age: u64,
    budget: &mut ReadBudget,
) -> Option<Vec<PathBuf>> {
    let bytes = read_owned_evidence_file(&policy.metadata, budget)?;
    let snapshot: DockerSnapshot = serde_json::from_slice(&bytes).ok()?;
    let paths = validate_docker_snapshot(
        &snapshot,
        policy,
        compose_policy,
        compose_digest,
        now,
        maximum_age,
    )?;
    Some(paths)
}

fn validate_docker_snapshot(
    snapshot: &DockerSnapshot,
    policy: &DockerEvidencePolicy,
    compose_policy: &FileEvidencePolicy,
    compose_digest: &str,
    now: u64,
    maximum_age: u64,
) -> Option<Vec<PathBuf>> {
    if snapshot.schema_version != "v1"
        || snapshot.daemon_identity != policy.daemon_identity
        || snapshot.inventory_generation != policy.generation
        || snapshot.compose_evidence_sha256.to_lowercase() != compose_digest.to_lowercase()
        || snapshot.generated_at > now.saturating_add(MAX_CLOCK_SKEW_SECONDS)
        || now.saturating_sub(snapshot.generated_at) > maximum_age
        || snapshot.containers.len() > MAX_REFERENCED_PATHS
    {
        return None;
    }
    let inventory_bytes = serde_json::to_vec(&snapshot.containers).ok()?;
    if hex::encode(Sha256::digest(&inventory_bytes)).to_lowercase()
        != snapshot.inventory_sha256.to_lowercase()
    {
        return None;
    }
    let mut ids = HashSet::new();
    let configured_compose_files = compose_policy
        .files
        .iter()
        .map(|file| file.path.as_path())
        .collect::<HashSet<_>>();
    let mut paths = Vec::new();
    for container in &snapshot.containers {
        if !valid_opaque(&container.id, 12, 128)
            || !ids.insert(&container.id)
            || !valid_opaque(&container.restart_policy, 2, 64)
        {
            return None;
        }
        for mount in &container.mounts {
            if !literal_absolute(&mount.source) || !literal_absolute(&mount.destination) {
                return None;
            }
            paths.push(mount.source.clone());
        }
        for compose_file in &container.compose_files {
            if !literal_absolute(compose_file)
                || !configured_compose_files.contains(compose_file.as_path())
            {
                return None;
            }
            paths.push(compose_file.clone());
        }
    }
    Some(paths)
}

fn aggregate_digest(files: &[EvidenceFilePolicy]) -> String {
    let mut entries = files
        .iter()
        .map(|file| {
            let mut entry = file.path.as_os_str().as_bytes().to_vec();
            entry.push(0);
            entry.extend_from_slice(file.sha256.to_lowercase().as_bytes());
            entry
        })
        .collect::<Vec<_>>();
    entries.sort();
    let mut hasher = Sha256::new();
    for entry in entries {
        hasher.update((entry.len() as u64).to_le_bytes());
        hasher.update(entry);
    }
    hex::encode(hasher.finalize())
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

#[cfg(test)]
mod tests {
    use std::io::Write;

    use tempfile::NamedTempFile;

    use super::*;

    fn docker_fixture() -> (
        DockerSnapshot,
        DockerEvidencePolicy,
        FileEvidencePolicy,
        String,
    ) {
        let compose_file = EvidenceFilePolicy {
            path: PathBuf::from("/etc/kolibri/compose.yml"),
            sha256: "a".repeat(64),
        };
        let compose = FileEvidencePolicy {
            generation: "compose-1".into(),
            files: vec![compose_file],
        };
        let compose_digest = aggregate_digest(&compose.files);
        let containers = vec![DockerContainer {
            id: "0123456789abcdef".into(),
            state: DockerContainerState::Running,
            restart_policy: "unless-stopped".into(),
            mounts: vec![DockerMount {
                source: PathBuf::from("/srv/kolibri/data"),
                destination: PathBuf::from("/app/data"),
                mount_type: DockerMountType::Bind,
                read_only: false,
            }],
            compose_files: vec![PathBuf::from("/etc/kolibri/compose.yml")],
        }];
        let inventory_sha256 =
            hex::encode(Sha256::digest(serde_json::to_vec(&containers).unwrap()));
        (
            DockerSnapshot {
                schema_version: "v1".into(),
                generated_at: 1_900_000_000,
                daemon_identity: "daemon-primary-1".into(),
                inventory_generation: "docker-1".into(),
                inventory_sha256,
                compose_evidence_sha256: compose_digest.clone(),
                containers,
            },
            DockerEvidencePolicy {
                generation: "docker-1".into(),
                daemon_identity: "daemon-primary-1".into(),
                metadata: EvidenceFilePolicy {
                    path: PathBuf::from("/etc/kolibri/docker-evidence.json"),
                    sha256: "b".repeat(64),
                },
            },
            compose,
            compose_digest,
        )
    }

    #[test]
    fn systemd_rejects_specifier_and_extracts_literal_paths() {
        assert!(parse_systemd("[Service]\nExecStart=/usr/bin/app %i\n").is_none());
        assert!(parse_systemd("[Service]\nVendorDataLocation=/srv/private\n").is_none());
        assert_eq!(
            parse_systemd(
                "[Service]\nExecStart=/usr/bin/app --config=/etc/kolibri/app.json\nWorkingDirectory=/srv/kolibri\n"
            )
            .unwrap(),
            [
                PathBuf::from("/usr/bin/app"),
                PathBuf::from("/etc/kolibri/app.json"),
                PathBuf::from("/srv/kolibri")
            ]
        );
    }

    #[test]
    fn nginx_rejects_unbound_include_and_variables() {
        assert!(parse_nginx("include /etc/nginx/conf.d/*.conf;").is_none());
        assert!(parse_nginx("root /srv/$tenant;").is_none());
        assert!(parse_nginx("vendor_asset_file /srv/private/index;\n").is_none());
        assert_eq!(
            parse_nginx("server { root /srv/kolibri/public; }").unwrap(),
            [PathBuf::from("/srv/kolibri/public")]
        );
    }

    #[test]
    fn cron_rejects_shell_expansion() {
        assert!(parse_cron("* * * * * root /usr/bin/find /tmp | /usr/bin/xargs rm").is_none());
        assert!(parse_cron("* * * * * /usr/bin/find /srv/private").is_none());
        assert_eq!(
            parse_cron("0 2 * * * root /usr/local/bin/backup /srv/kolibri\n").unwrap(),
            [
                PathBuf::from("/usr/local/bin/backup"),
                PathBuf::from("/srv/kolibri")
            ]
        );
    }

    #[test]
    fn compose_rejects_interpolation_anchors_and_includes() {
        assert!(parse_compose("services:\n  app:\n    volumes: [\"${DATA}:/data\"]").is_none());
        assert!(parse_compose("include:\n  - other.yml").is_none());
        assert!(parse_compose("x-base: &base\n  image: app").is_none());
        assert!(parse_compose("services:\n  app:\n    volumes:\n      - ./data:/data").is_none());
        assert!(parse_compose("services:\n  app:\n    env_file: production.env").is_none());
        assert!(parse_compose("services:\n  app:\n    build: app").is_none());
        assert!(parse_compose("configs:\n  app:\n    file: config.json").is_none());
        assert!(parse_compose("secrets:\n  token:\n    file: secrets/token").is_none());
    }

    #[test]
    fn incomplete_assessment_guards_every_candidate() {
        let assessment = GuardEvidenceAssessment::incomplete();
        assert!(assessment.path_is_guarded(Path::new("/any/candidate")));
        assert!(assessment.guarded_scopes().is_empty());
        assert!(!assessment.authorizes_actions());
    }

    #[test]
    fn writable_or_non_root_evidence_metadata_is_rejected() {
        let mut file = NamedTempFile::new().unwrap();
        file.write_all(b"evidence").unwrap();
        let mut permissions = file.as_file().metadata().unwrap().permissions();
        permissions.set_mode(0o664);
        file.as_file().set_permissions(permissions).unwrap();
        assert!(!secure_evidence_metadata(
            &file.as_file().metadata().unwrap(),
            1024
        ));

        let mut permissions = file.as_file().metadata().unwrap().permissions();
        permissions.set_mode(0o644);
        file.as_file().set_permissions(permissions).unwrap();
        let accepted = secure_evidence_metadata(&file.as_file().metadata().unwrap(), 1024);
        assert_eq!(accepted, unsafe { libc::geteuid() } == 0);
    }

    #[test]
    fn docker_marker_binds_identity_inventory_and_compose_digest() {
        let (snapshot, policy, compose, compose_digest) = docker_fixture();
        assert!(
            validate_docker_snapshot(
                &snapshot,
                &policy,
                &compose,
                &compose_digest,
                1_900_000_030,
                300
            )
            .is_some()
        );

        let mut wrong_identity = snapshot;
        wrong_identity.daemon_identity = "daemon-other-1".into();
        assert!(
            validate_docker_snapshot(
                &wrong_identity,
                &policy,
                &compose,
                &compose_digest,
                1_900_000_030,
                300
            )
            .is_none()
        );
    }

    #[test]
    fn docker_marker_rejects_stale_or_tampered_inventory() {
        let (mut snapshot, policy, compose, compose_digest) = docker_fixture();
        assert!(
            validate_docker_snapshot(
                &snapshot,
                &policy,
                &compose,
                &compose_digest,
                1_900_000_301,
                300
            )
            .is_none()
        );
        snapshot.generated_at = 1_900_000_000;
        snapshot.inventory_sha256 = "0".repeat(64);
        assert!(
            validate_docker_snapshot(
                &snapshot,
                &policy,
                &compose,
                &compose_digest,
                1_900_000_030,
                300
            )
            .is_none()
        );
    }
}
