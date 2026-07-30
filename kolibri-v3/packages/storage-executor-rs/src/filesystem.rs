use std::collections::HashMap;
use std::ffi::{CStr, CString};
use std::fs;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::MetadataExt;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use sha2::{Digest, Sha256};

use crate::error::{ExecutorError, Result};
use crate::guard_evidence::GuardEvidenceAssessment;
use crate::model::{
    CandidateManifest, CapacitySegment, CapacitySegmentKind, CategoryInventory, CleanupCategory,
    ProjectCandidateView, RootKind,
};
use crate::policy::{RootPolicy, VerifiedPolicy, valid_project_id};

const TRASH_NAME: &str = ".kolibri-storage-trash";

#[derive(Debug, Clone)]
pub(crate) struct ScanSnapshot {
    pub generation: String,
    pub candidates: HashMap<CleanupCategory, Vec<CandidateManifest>>,
    pub projects: Vec<ProjectCandidateView>,
    pub project_manifests: HashMap<String, CandidateManifest>,
    pub protected_item_count: u64,
}

#[derive(Debug)]
struct TreeFacts {
    size_bytes: u64,
    modified_at: u64,
    device: u64,
    inode: u64,
    digest: String,
    safe: bool,
    entry_count: u64,
}

#[derive(Debug)]
struct ScanBudget {
    entries: u64,
    maximum: u64,
    maximum_depth: u32,
}

pub(crate) fn scan(
    policy: &VerifiedPolicy,
    evidence: &GuardEvidenceAssessment,
    now: u64,
) -> Result<ScanSnapshot> {
    require_action_authority(evidence)?;
    let mut budget = ScanBudget {
        entries: 0,
        maximum: policy.policy.limits.max_scan_entries,
        maximum_depth: policy.policy.limits.max_scan_depth,
    };
    let mut candidates: HashMap<CleanupCategory, Vec<CandidateManifest>> = HashMap::new();
    let mut projects = Vec::new();
    let mut project_manifests = HashMap::new();
    let mut protected_item_count = 0_u64;
    let mut generation_entries = Vec::new();

    for root in &policy.policy.roots {
        ensure_root_still_safe(policy, root)?;
        if matches!(
            root.kind,
            RootKind::ProjectQuarantine | RootKind::StoppedContainer
        ) {
            generation_entries.push(format!("{}:reserved", root.root_id));
            continue;
        }
        let root_device = fs::metadata(&root.path)?.dev();
        let mut children = fs::read_dir(&root.path)?.collect::<std::io::Result<Vec<_>>>()?;
        children.sort_by_key(|entry| entry.file_name());
        for child in children {
            budget.entries = budget.entries.checked_add(1).ok_or_else(limit_exceeded)?;
            if budget.entries > budget.maximum {
                return Err(limit_exceeded());
            }
            let name = match child.file_name().to_str() {
                Some(value) if valid_single_name(value) => value.to_owned(),
                _ => {
                    protected_item_count = protected_item_count.saturating_add(1);
                    generation_entries.push(format!("{}:non-utf8", root.root_id));
                    continue;
                }
            };
            if name == TRASH_NAME {
                generation_entries.push(format!("{}:executor-trash", root.root_id));
                continue;
            }
            let absolute = root.path.join(&name);
            if policy.path_is_guarded(evidence, &absolute)? || has_live_reference(&absolute) {
                protected_item_count = protected_item_count.saturating_add(1);
                generation_entries.push(format!("{}:{name}:guarded", root.root_id));
                continue;
            }
            let facts = inspect_tree(&absolute, root_device, 0, &mut budget)?;
            generation_entries.push(format!(
                "{}:{}:{}:{}:{}",
                root.root_id, name, facts.device, facts.inode, facts.digest
            ));
            if !facts.safe {
                protected_item_count = protected_item_count.saturating_add(1);
                continue;
            }
            let manifest = CandidateManifest {
                root_id: root.root_id.clone(),
                relative_name: name.clone(),
                size_bytes: facts.size_bytes,
                modified_at: facts.modified_at,
                device: facts.device,
                inode: facts.inode,
                tree_digest: facts.digest,
            };
            let old_enough = now.saturating_sub(manifest.modified_at) >= root.minimum_age_seconds;
            match root.kind {
                RootKind::ProjectSource if old_enough && valid_project_id(&name) => {
                    projects.push(ProjectCandidateView {
                        project_id: name.clone(),
                        display_name: name.clone(),
                        size_bytes: manifest.size_bytes,
                        last_modified_at: manifest.modified_at,
                    });
                    project_manifests.insert(name, manifest);
                }
                kind if old_enough && kind.cleanup_category().is_some() => {
                    let category = kind.cleanup_category().expect("category checked");
                    candidates.entry(category).or_default().push(manifest);
                }
                _ => {}
            }
        }
    }

    for items in candidates.values_mut() {
        items.sort_by(|left, right| {
            left.root_id
                .cmp(&right.root_id)
                .then(left.relative_name.cmp(&right.relative_name))
        });
    }
    projects.sort_by(|left, right| left.project_id.cmp(&right.project_id));
    generation_entries.sort();
    let generation = format!(
        "gen_{}",
        hex::encode(Sha256::digest(generation_entries.join("\n").as_bytes()))
    );
    Ok(ScanSnapshot {
        generation,
        candidates,
        projects,
        project_manifests,
        protected_item_count,
    })
}

pub(crate) fn category_inventory(snapshot: &ScanSnapshot) -> Vec<CategoryInventory> {
    [
        CleanupCategory::Build,
        CleanupCategory::Cache,
        CleanupCategory::Log,
        CleanupCategory::StoppedContainer,
    ]
    .into_iter()
    .map(|category| {
        let items = snapshot
            .candidates
            .get(&category)
            .map(Vec::as_slice)
            .unwrap_or_default();
        CategoryInventory {
            category,
            reclaimable_bytes: items.iter().map(|item| item.size_bytes).sum(),
            item_count: items.len() as u64,
            oldest_item_at: items.iter().map(|item| item.modified_at).min(),
        }
    })
    .collect()
}

fn inspect_tree(
    path: &Path,
    root_device: u64,
    depth: u32,
    budget: &mut ScanBudget,
) -> Result<TreeFacts> {
    if depth > budget.maximum_depth {
        return Err(limit_exceeded());
    }
    let metadata = fs::symlink_metadata(path)?;
    let file_type = metadata.file_type();
    let mut hasher = Sha256::new();
    if depth > 0 {
        hasher.update(path.file_name().unwrap_or_default().as_bytes());
    }
    hasher.update(metadata.dev().to_le_bytes());
    hasher.update(metadata.ino().to_le_bytes());
    hasher.update(metadata.mode().to_le_bytes());
    hasher.update(metadata.size().to_le_bytes());
    hasher.update(metadata.mtime().to_le_bytes());
    let mut result = TreeFacts {
        size_bytes: if metadata.is_file() {
            metadata.len()
        } else {
            0
        },
        modified_at: u64::try_from(metadata.mtime()).unwrap_or(0),
        device: metadata.dev(),
        inode: metadata.ino(),
        digest: String::new(),
        safe: metadata.dev() == root_device && !file_type.is_symlink(),
        entry_count: 1,
    };
    if metadata.is_dir() && result.safe {
        let mut children = fs::read_dir(path)?.collect::<std::io::Result<Vec<_>>>()?;
        children.sort_by_key(|entry| entry.file_name());
        for child in children {
            budget.entries = budget.entries.checked_add(1).ok_or_else(limit_exceeded)?;
            if budget.entries > budget.maximum {
                return Err(limit_exceeded());
            }
            let facts = inspect_tree(&child.path(), root_device, depth + 1, budget)?;
            result.size_bytes = result
                .size_bytes
                .checked_add(facts.size_bytes)
                .ok_or_else(limit_exceeded)?;
            result.modified_at = result.modified_at.max(facts.modified_at);
            result.entry_count = result
                .entry_count
                .checked_add(facts.entry_count)
                .ok_or_else(limit_exceeded)?;
            result.safe &= facts.safe;
            hasher.update(facts.digest.as_bytes());
        }
    }
    result.digest = hex::encode(hasher.finalize());
    Ok(result)
}

pub(crate) fn current_manifest(
    policy: &VerifiedPolicy,
    expected: &CandidateManifest,
) -> Result<Option<CandidateManifest>> {
    current_manifest_with_probe(policy, expected, &has_live_reference)
}

fn current_manifest_with_probe(
    policy: &VerifiedPolicy,
    expected: &CandidateManifest,
    live_reference_probe: &dyn Fn(&Path) -> bool,
) -> Result<Option<CandidateManifest>> {
    let evidence = current_evidence(policy)?;
    let root = policy.root(&expected.root_id)?;
    ensure_root_still_safe(policy, root)?;
    if !valid_single_name(&expected.relative_name) {
        return Err(ExecutorError::rejected(
            "candidate_invalid",
            "The preview candidate is invalid.",
        ));
    }
    let path = root.path.join(&expected.relative_name);
    if !path.exists() {
        return Ok(None);
    }
    if policy.path_is_guarded(&evidence, &path)? || live_reference_probe(&path) {
        return Err(ExecutorError::rejected(
            "candidate_became_protected",
            "A preview candidate is now protected.",
        ));
    }
    let mut budget = ScanBudget {
        entries: 0,
        maximum: policy.policy.limits.max_scan_entries,
        maximum_depth: policy.policy.limits.max_scan_depth,
    };
    let facts = inspect_tree(&path, fs::metadata(&root.path)?.dev(), 0, &mut budget)?;
    if !facts.safe {
        return Err(ExecutorError::rejected(
            "candidate_became_unsafe",
            "A preview candidate is no longer safe.",
        ));
    }
    Ok(Some(CandidateManifest {
        root_id: expected.root_id.clone(),
        relative_name: expected.relative_name.clone(),
        size_bytes: facts.size_bytes,
        modified_at: facts.modified_at,
        device: facts.device,
        inode: facts.inode,
        tree_digest: facts.digest,
    }))
}

fn current_evidence(policy: &VerifiedPolicy) -> Result<GuardEvidenceAssessment> {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    let evidence = policy.guard_evidence(now);
    require_action_authority(&evidence)?;
    Ok(evidence)
}

fn require_action_authority(evidence: &GuardEvidenceAssessment) -> Result<()> {
    if !evidence.authorizes_actions() {
        return Err(ExecutorError::rejected(
            "guard_evidence_unavailable",
            "Exhaustive live guard evidence is unavailable.",
        ));
    }
    Ok(())
}

pub(crate) fn manifest_for_entry(
    policy: &VerifiedPolicy,
    root_id: &str,
    name: &str,
) -> Result<Option<CandidateManifest>> {
    let probe = CandidateManifest {
        root_id: root_id.to_owned(),
        relative_name: name.to_owned(),
        size_bytes: 0,
        modified_at: 0,
        device: 0,
        inode: 0,
        tree_digest: String::new(),
    };
    current_manifest(policy, &probe)
}

pub(crate) fn manifest_matches(left: &CandidateManifest, right: &CandidateManifest) -> bool {
    left.root_id == right.root_id
        && left.relative_name == right.relative_name
        && left.size_bytes == right.size_bytes
        && left.modified_at == right.modified_at
        && left.device == right.device
        && left.inode == right.inode
        && left.tree_digest == right.tree_digest
}

pub(crate) fn manifest_content_matches(
    left: &CandidateManifest,
    right: &CandidateManifest,
) -> bool {
    left.size_bytes == right.size_bytes
        && left.modified_at == right.modified_at
        && left.device == right.device
        && left.inode == right.inode
        && left.tree_digest == right.tree_digest
}

pub(crate) fn remove_candidate(
    policy: &VerifiedPolicy,
    candidate: &CandidateManifest,
    staging_name: &str,
) -> Result<()> {
    remove_candidate_inner(policy, candidate, staging_name, None, &has_live_reference)
}

#[cfg(test)]
fn remove_candidate_with_test_hook(
    policy: &VerifiedPolicy,
    candidate: &CandidateManifest,
    staging_name: &str,
    after_staging: &mut dyn FnMut(&Path),
    live_reference_probe: &dyn Fn(&Path) -> bool,
) -> Result<()> {
    remove_candidate_inner(
        policy,
        candidate,
        staging_name,
        Some(after_staging),
        live_reference_probe,
    )
}

fn remove_candidate_inner(
    policy: &VerifiedPolicy,
    candidate: &CandidateManifest,
    staging_name: &str,
    mut after_staging: Option<&mut dyn FnMut(&Path)>,
    live_reference_probe: &dyn Fn(&Path) -> bool,
) -> Result<()> {
    let root = policy.root(&candidate.root_id)?;
    if !valid_single_name(&candidate.relative_name)
        || !valid_single_name(staging_name)
        || !staging_name.starts_with("del_")
    {
        return Err(ExecutorError::rejected(
            "candidate_invalid",
            "The preview candidate is invalid.",
        ));
    }
    let root_fd = open_policy_root(policy, root)?;
    let name = cstring_name(&candidate.relative_name)?;
    let trash_name = cstring_name(TRASH_NAME)?;
    let trash_fd = open_private_child(root_fd.as_raw_fd(), &trash_name)?;
    let staged_name = cstring_name(staging_name)?;
    let source = stat_at(root_fd.as_raw_fd(), &name)?;
    let staged = stat_at(trash_fd.as_raw_fd(), &staged_name)?;
    let mut moved_now = false;
    match (source, staged) {
        (None, None) => return Ok(()),
        (Some(_), Some(_)) => {
            return Err(ExecutorError::incomplete(
                "cleanup_state_ambiguous",
                "Both cleanup source and staged entries exist.",
            ));
        }
        (Some(metadata), None) => {
            let current = current_manifest_with_probe(policy, candidate, live_reference_probe)?
                .ok_or_else(|| {
                    ExecutorError::incomplete(
                        "candidate_disappeared",
                        "A cleanup candidate disappeared during apply.",
                    )
                })?;
            if !manifest_matches(candidate, &current)
                || metadata.st_dev as u64 != candidate.device
                || metadata.st_ino != candidate.inode
            {
                return Err(ExecutorError::incomplete(
                    "candidate_changed_during_apply",
                    "A cleanup candidate changed during apply.",
                ));
            }
            // SAFETY: both descriptors are pinned directories and both names
            // are single components. The destination is proven absent.
            if unsafe {
                libc::renameat(
                    root_fd.as_raw_fd(),
                    name.as_ptr(),
                    trash_fd.as_raw_fd(),
                    staged_name.as_ptr(),
                )
            } != 0
            {
                return Err(std::io::Error::last_os_error().into());
            }
            fsync_fd(root_fd.as_raw_fd())?;
            fsync_fd(trash_fd.as_raw_fd())?;
            moved_now = true;
        }
        (None, Some(_)) => {}
    }
    let staged = stat_at(trash_fd.as_raw_fd(), &staged_name)?.ok_or_else(|| {
        ExecutorError::incomplete(
            "cleanup_stage_missing",
            "The staged cleanup entry is missing.",
        )
    })?;
    if staged.st_dev as u64 != candidate.device || staged.st_ino as u64 != candidate.inode {
        rollback_rename(
            trash_fd.as_raw_fd(),
            &staged_name,
            root_fd.as_raw_fd(),
            &name,
        )?;
        return Err(ExecutorError::incomplete(
            "cleanup_stage_identity_mismatch",
            "A rename race was detected and rolled back.",
        ));
    }
    let staged_path = root.path.join(TRASH_NAME).join(staging_name);
    let mut budget = ScanBudget {
        entries: 0,
        maximum: policy.policy.limits.max_scan_entries,
        maximum_depth: policy.policy.limits.max_scan_depth,
    };
    let facts = inspect_tree(&staged_path, candidate.device, 0, &mut budget)?;
    let staged_manifest = CandidateManifest {
        root_id: candidate.root_id.clone(),
        relative_name: candidate.relative_name.clone(),
        size_bytes: facts.size_bytes,
        modified_at: facts.modified_at,
        device: facts.device,
        inode: facts.inode,
        tree_digest: facts.digest,
    };
    if !facts.safe {
        rollback_rename(
            trash_fd.as_raw_fd(),
            &staged_name,
            root_fd.as_raw_fd(),
            &name,
        )?;
        return Err(ExecutorError::incomplete(
            "cleanup_stage_manifest_mismatch",
            "The staged cleanup crossed a filesystem boundary and was rolled back.",
        ));
    }
    if moved_now && !manifest_matches(candidate, &staged_manifest) {
        rollback_rename(
            trash_fd.as_raw_fd(),
            &staged_name,
            root_fd.as_raw_fd(),
            &name,
        )?;
        return Err(ExecutorError::incomplete(
            "cleanup_stage_manifest_mismatch",
            "The newly staged cleanup manifest changed and was rolled back.",
        ));
    }
    if let Some(hook) = after_staging.as_mut() {
        hook(&staged_path);
    }
    if live_reference_probe(&staged_path) {
        if moved_now {
            rollback_rename(
                trash_fd.as_raw_fd(),
                &staged_name,
                root_fd.as_raw_fd(),
                &name,
            )?;
        }
        return Err(ExecutorError::incomplete(
            "cleanup_stage_became_referenced",
            "The staged cleanup entry gained a live reference and was retained.",
        ));
    }
    // If the entry was already staged before this invocation, a smaller tree
    // with the same pinned top-level inode is a recoverable mid-delete state.
    // It stays isolated in the executor-owned trash and deletion resumes; it
    // is never restored to its original location after deletion has begun.
    remove_at(trash_fd.as_raw_fd(), &staged_name, candidate.device)?;
    fsync_fd(trash_fd.as_raw_fd())?;
    Ok(())
}

pub(crate) fn rename_candidate(
    policy: &VerifiedPolicy,
    source: &CandidateManifest,
    destination_root_id: &str,
    destination_name: &str,
) -> Result<()> {
    let source_root = policy.root(&source.root_id)?;
    let destination_root = policy.root(destination_root_id)?;
    if !valid_single_name(&source.relative_name) || !valid_single_name(destination_name) {
        return Err(ExecutorError::rejected(
            "rename_target_invalid",
            "The project rename target is invalid.",
        ));
    }
    let source_fd = open_policy_root(policy, source_root)?;
    let destination_fd = open_policy_root(policy, destination_root)?;
    let source_stat = fstat_fd(source_fd.as_raw_fd())?;
    let destination_stat = fstat_fd(destination_fd.as_raw_fd())?;
    if source_stat.st_dev != destination_stat.st_dev {
        return Err(ExecutorError::rejected(
            "quarantine_cross_filesystem",
            "Project quarantine must use the same filesystem.",
        ));
    }
    let source_name = cstring_name(&source.relative_name)?;
    let destination_name = cstring_name(destination_name)?;
    if stat_at(destination_fd.as_raw_fd(), &destination_name)?.is_some() {
        return Err(ExecutorError::rejected(
            "restore_target_conflict",
            "The project destination already exists.",
        ));
    }
    let current = stat_at(source_fd.as_raw_fd(), &source_name)?.ok_or_else(|| {
        ExecutorError::rejected(
            "candidate_missing",
            "The preview candidate no longer exists.",
        )
    })?;
    if current.st_dev as u64 != source.device || current.st_ino as u64 != source.inode {
        return Err(ExecutorError::rejected(
            "candidate_identity_changed",
            "A preview candidate changed identity.",
        ));
    }
    // SAFETY: both descriptors are open O_NOFOLLOW directories and both names
    // are validated single path components with no NUL.
    let result = unsafe {
        libc::renameat(
            source_fd.as_raw_fd(),
            source_name.as_ptr(),
            destination_fd.as_raw_fd(),
            destination_name.as_ptr(),
        )
    };
    if result != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    fsync_fd(source_fd.as_raw_fd())?;
    fsync_fd(destination_fd.as_raw_fd())?;
    let moved = stat_at(destination_fd.as_raw_fd(), &destination_name)?.ok_or_else(|| {
        ExecutorError::incomplete(
            "rename_destination_missing",
            "The renamed project destination is missing.",
        )
    })?;
    if moved.st_dev as u64 != source.device || moved.st_ino as u64 != source.inode {
        rollback_rename(
            destination_fd.as_raw_fd(),
            &destination_name,
            source_fd.as_raw_fd(),
            &source_name,
        )?;
        return Err(ExecutorError::incomplete(
            "rename_identity_mismatch",
            "A project rename race was detected and rolled back.",
        ));
    }
    let moved_manifest = manifest_for_entry(
        policy,
        destination_root_id,
        destination_name.to_str().map_err(|_| {
            ExecutorError::incomplete(
                "rename_destination_invalid",
                "The renamed project destination is invalid.",
            )
        })?,
    )?
    .ok_or_else(|| {
        ExecutorError::incomplete(
            "rename_destination_missing",
            "The renamed project destination is missing.",
        )
    })?;
    if !manifest_content_matches(source, &moved_manifest) {
        rollback_rename(
            destination_fd.as_raw_fd(),
            &destination_name,
            source_fd.as_raw_fd(),
            &source_name,
        )?;
        return Err(ExecutorError::incomplete(
            "rename_manifest_mismatch",
            "A project rename changed the approved manifest and was rolled back.",
        ));
    }
    Ok(())
}

pub(crate) fn root_entry_exists(
    policy: &VerifiedPolicy,
    root_id: &str,
    name: &str,
) -> Result<bool> {
    if !valid_single_name(name) {
        return Err(ExecutorError::rejected(
            "candidate_invalid",
            "The storage entry identifier is invalid.",
        ));
    }
    let root = policy.root(root_id)?;
    let fd = open_policy_root(policy, root)?;
    Ok(stat_at(fd.as_raw_fd(), &cstring_name(name)?)?.is_some())
}

pub(crate) fn capacity(policy: &VerifiedPolicy) -> Result<(u64, u64, u64)> {
    let path = policy
        .policy
        .roots
        .first()
        .map(|root| root.path.as_path())
        .ok_or_else(|| {
            ExecutorError::rejected("policy_invalid", "The storage policy has no roots.")
        })?;
    let path = CString::new(path.as_os_str().as_bytes()).map_err(|_| {
        ExecutorError::rejected(
            "capacity_unavailable",
            "Filesystem capacity is unavailable.",
        )
    })?;
    let mut stat: libc::statvfs = unsafe { std::mem::zeroed() };
    // SAFETY: path is a valid NUL-terminated absolute path and stat points to
    // writable initialized memory.
    if unsafe { libc::statvfs(path.as_ptr(), &mut stat) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let block_size = stat.f_frsize;
    let capacity = (stat.f_blocks as u64).saturating_mul(block_size);
    let free = (stat.f_bavail as u64).saturating_mul(block_size);
    Ok((capacity, capacity.saturating_sub(free), free))
}

pub(crate) fn capacity_segments(policy: &VerifiedPolicy) -> Result<Vec<CapacitySegment>> {
    let Some(topology) = &policy.policy.capacity_topology else {
        return Ok(Vec::new());
    };
    let metadata = fs::symlink_metadata(&topology.lvm_backup_path).map_err(|_| {
        ExecutorError::rejected(
            "capacity_topology_unavailable",
            "Live LVM capacity topology is unavailable.",
        )
    })?;
    if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.len() > 2 * 1024 * 1024
    {
        return Err(ExecutorError::rejected(
            "capacity_topology_invalid",
            "Live LVM capacity topology is invalid.",
        ));
    }
    let contents = fs::read_to_string(&topology.lvm_backup_path)?;
    let parsed = parse_lvm_backup(&contents, &topology.root_lv_name)?;
    let root_bytes = parsed
        .root_extents
        .checked_mul(parsed.extent_bytes)
        .ok_or_else(capacity_invalid)?;
    let total_bytes = parsed
        .total_extents
        .checked_mul(parsed.extent_bytes)
        .ok_or_else(capacity_invalid)?;
    let used_bytes = parsed
        .used_extents
        .checked_mul(parsed.extent_bytes)
        .ok_or_else(capacity_invalid)?;
    let reserve_bytes = total_bytes
        .checked_sub(used_bytes)
        .ok_or_else(capacity_invalid)?;
    Ok(vec![
        CapacitySegment {
            kind: CapacitySegmentKind::RootLv,
            display_name: topology.root_display_name.clone(),
            display_size: display_gib(root_bytes),
            capacity_bytes: root_bytes,
            read_only: true,
        },
        CapacitySegment {
            kind: CapacitySegmentKind::VgUnallocated,
            display_name: topology.reserve_display_name.clone(),
            display_size: display_gib(reserve_bytes),
            capacity_bytes: reserve_bytes,
            read_only: true,
        },
    ])
}

struct LvmFacts {
    extent_bytes: u64,
    total_extents: u64,
    used_extents: u64,
    root_extents: u64,
}

fn parse_lvm_backup(contents: &str, root_lv_name: &str) -> Result<LvmFacts> {
    let mut stack: Vec<String> = Vec::new();
    let mut extent_sectors = None;
    let mut total_extents = 0_u64;
    let mut used_extents = 0_u64;
    let mut root_extents = 0_u64;
    for raw_line in contents.lines() {
        let line = raw_line.split('#').next().unwrap_or_default().trim();
        if line.is_empty() {
            continue;
        }
        if let Some(name) = line.strip_suffix('{') {
            let name = name.trim().trim_matches('"');
            if name.is_empty() || name.len() > 128 {
                return Err(capacity_invalid());
            }
            stack.push(name.to_owned());
            continue;
        }
        if line == "}" {
            stack.pop().ok_or_else(capacity_invalid)?;
            continue;
        }
        let Some((key, raw_value)) = line.split_once('=') else {
            continue;
        };
        let key = key.trim();
        let value = raw_value.trim().trim_matches('"');
        match key {
            "extent_size" if stack.len() == 1 => {
                extent_sectors = Some(parse_u64(value)?);
            }
            "pe_count" if stack.iter().any(|item| item == "physical_volumes") => {
                total_extents = total_extents
                    .checked_add(parse_u64(value)?)
                    .ok_or_else(capacity_invalid)?;
            }
            "extent_count" if stack.iter().any(|item| item == "logical_volumes") => {
                let extents = parse_u64(value)?;
                used_extents = used_extents
                    .checked_add(extents)
                    .ok_or_else(capacity_invalid)?;
                if stack.iter().any(|item| item == root_lv_name) {
                    root_extents = root_extents
                        .checked_add(extents)
                        .ok_or_else(capacity_invalid)?;
                }
            }
            _ => {}
        }
    }
    let extent_bytes = extent_sectors
        .and_then(|value| value.checked_mul(512))
        .ok_or_else(capacity_invalid)?;
    if total_extents == 0 || used_extents == 0 || root_extents == 0 || used_extents > total_extents
    {
        return Err(capacity_invalid());
    }
    Ok(LvmFacts {
        extent_bytes,
        total_extents,
        used_extents,
        root_extents,
    })
}

fn parse_u64(value: &str) -> Result<u64> {
    value.parse().map_err(|_| capacity_invalid())
}

fn display_gib(bytes: u64) -> String {
    let gib = bytes as f64 / 1024_f64.powi(3);
    if (gib - gib.round()).abs() < 0.005 {
        format!("{gib:.0} GiB")
    } else {
        format!("{gib:.2} GiB")
    }
}

fn ensure_root_still_safe(policy: &VerifiedPolicy, root: &RootPolicy) -> Result<()> {
    policy.assert_root_identity(root)
}

fn valid_single_name(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 255
        && value != "."
        && value != ".."
        && !value.contains('/')
        && !value.contains('\\')
        && !value.as_bytes().contains(&0)
}

fn cstring_name(value: &str) -> Result<CString> {
    if !valid_single_name(value) {
        return Err(ExecutorError::rejected(
            "candidate_invalid",
            "The storage entry identifier is invalid.",
        ));
    }
    CString::new(value).map_err(|_| {
        ExecutorError::rejected(
            "candidate_invalid",
            "The storage entry identifier is invalid.",
        )
    })
}

fn open_directory(path: &Path) -> Result<OwnedFd> {
    let path = CString::new(path.as_os_str().as_bytes()).map_err(|_| {
        ExecutorError::rejected("root_invalid", "An allowlisted storage root is invalid.")
    })?;
    // SAFETY: path is a valid NUL-terminated path. The returned descriptor is
    // immediately owned and closed by OwnedFd.
    let fd = unsafe {
        libc::open(
            path.as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
        )
    };
    if fd < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    // SAFETY: fd was returned uniquely by open above.
    Ok(unsafe { OwnedFd::from_raw_fd(fd) })
}

fn open_policy_root(policy: &VerifiedPolicy, root: &RootPolicy) -> Result<OwnedFd> {
    policy.assert_root_identity(root)?;
    let descriptor = open_directory(&root.path)?;
    let opened = fstat_fd(descriptor.as_raw_fd())?;
    let metadata = fs::metadata(&root.path)?;
    if opened.st_dev as u64 != metadata.dev() || opened.st_ino as u64 != metadata.ino() {
        return Err(ExecutorError::rejected(
            "root_changed",
            "An allowlisted storage root changed during open.",
        ));
    }
    policy.assert_root_identity(root)?;
    Ok(descriptor)
}

fn open_private_child(parent: RawFd, name: &CStr) -> Result<OwnedFd> {
    // SAFETY: parent is an open pinned directory and name is a single
    // NUL-terminated component. O_NOFOLLOW rejects a substituted symlink.
    let fd = unsafe {
        libc::openat(
            parent,
            name.as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
        )
    };
    if fd < 0 {
        return Err(ExecutorError::rejected(
            "executor_trash_unavailable",
            "The executor-owned cleanup staging directory is unavailable.",
        ));
    }
    // SAFETY: fd is uniquely owned after successful openat.
    let fd = unsafe { OwnedFd::from_raw_fd(fd) };
    let stat = fstat_fd(fd.as_raw_fd())?;
    let permissions = stat.st_mode & 0o777;
    // The node agent normally runs as root. Tests and unprivileged VM drills
    // use their own effective UID with the same private ownership invariant.
    if stat.st_uid != unsafe { libc::geteuid() } || permissions & 0o077 != 0 {
        return Err(ExecutorError::rejected(
            "executor_trash_unsafe",
            "The executor cleanup staging directory is not private.",
        ));
    }
    Ok(fd)
}

fn rollback_rename(
    from_parent: RawFd,
    from_name: &CStr,
    to_parent: RawFd,
    to_name: &CStr,
) -> Result<()> {
    if stat_at(to_parent, to_name)?.is_some() {
        return Err(ExecutorError::incomplete(
            "rename_rollback_conflict",
            "A rename race could not be rolled back automatically.",
        ));
    }
    // SAFETY: descriptors are pinned directories and names are single
    // components. This reverses a just-observed rename without deleting data.
    if unsafe { libc::renameat(from_parent, from_name.as_ptr(), to_parent, to_name.as_ptr()) } != 0
    {
        return Err(ExecutorError::incomplete(
            "rename_rollback_failed",
            "A rename race could not be rolled back automatically.",
        ));
    }
    fsync_fd(from_parent)?;
    fsync_fd(to_parent)?;
    Ok(())
}

fn stat_at(parent: RawFd, name: &CStr) -> Result<Option<libc::stat>> {
    let mut stat: libc::stat = unsafe { std::mem::zeroed() };
    // SAFETY: parent is an open directory, name is NUL-terminated and stat is
    // writable. AT_SYMLINK_NOFOLLOW prevents following the final component.
    let result =
        unsafe { libc::fstatat(parent, name.as_ptr(), &mut stat, libc::AT_SYMLINK_NOFOLLOW) };
    if result == 0 {
        return Ok(Some(stat));
    }
    let error = std::io::Error::last_os_error();
    if error.raw_os_error() == Some(libc::ENOENT) {
        Ok(None)
    } else {
        Err(error.into())
    }
}

fn fstat_fd(fd: RawFd) -> Result<libc::stat> {
    let mut stat: libc::stat = unsafe { std::mem::zeroed() };
    // SAFETY: fd is valid and stat points to writable memory.
    if unsafe { libc::fstat(fd, &mut stat) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    Ok(stat)
}

fn remove_at(parent: RawFd, name: &CStr, expected_device: u64) -> Result<()> {
    let stat = stat_at(parent, name)?.ok_or_else(|| {
        ExecutorError::rejected(
            "candidate_missing",
            "The preview candidate no longer exists.",
        )
    })?;
    let kind = stat.st_mode & libc::S_IFMT;
    if stat.st_dev as u64 != expected_device {
        return Err(ExecutorError::incomplete(
            "mount_boundary_changed",
            "Recursive cleanup refused to cross a filesystem boundary.",
        ));
    }
    if kind == libc::S_IFLNK {
        return Err(ExecutorError::rejected(
            "symlink_blocked",
            "Symbolic links are never followed or removed.",
        ));
    }
    if kind == libc::S_IFDIR {
        // SAFETY: parent is an open directory and name is a validated
        // component. O_NOFOLLOW prevents a symlink swap from escaping.
        let child = unsafe {
            libc::openat(
                parent,
                name.as_ptr(),
                libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            )
        };
        if child < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        // SAFETY: child was uniquely returned by openat.
        let child = unsafe { OwnedFd::from_raw_fd(child) };
        let opened = fstat_fd(child.as_raw_fd())?;
        if opened.st_dev != stat.st_dev || opened.st_ino != stat.st_ino {
            return Err(ExecutorError::incomplete(
                "recursive_identity_changed",
                "A recursive cleanup entry changed identity.",
            ));
        }
        for entry in list_directory(child.as_raw_fd())? {
            remove_at(child.as_raw_fd(), &entry, expected_device)?;
        }
        fsync_fd(child.as_raw_fd())?;
        // SAFETY: parent/name are valid; AT_REMOVEDIR only removes this empty
        // directory and never follows it.
        if unsafe { libc::unlinkat(parent, name.as_ptr(), libc::AT_REMOVEDIR) } != 0 {
            return Err(std::io::Error::last_os_error().into());
        }
    } else if kind == libc::S_IFREG {
        // Open and compare the regular file before unlink. The enclosing
        // staging directory is private, so no new path lookup is available to
        // unprivileged writers after the candidate was moved there.
        let opened = unsafe {
            libc::openat(
                parent,
                name.as_ptr(),
                libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            )
        };
        if opened < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        let opened = unsafe { OwnedFd::from_raw_fd(opened) };
        let opened_stat = fstat_fd(opened.as_raw_fd())?;
        if opened_stat.st_dev != stat.st_dev || opened_stat.st_ino != stat.st_ino {
            return Err(ExecutorError::incomplete(
                "recursive_identity_changed",
                "A recursive cleanup entry changed identity.",
            ));
        }
        // SAFETY: unlinkat removes only the named directory entry.
        if unsafe { libc::unlinkat(parent, name.as_ptr(), 0) } != 0 {
            return Err(std::io::Error::last_os_error().into());
        }
    } else {
        return Err(ExecutorError::rejected(
            "special_file_blocked",
            "Special filesystem entries are never removed.",
        ));
    }
    Ok(())
}

fn list_directory(fd: RawFd) -> Result<Vec<CString>> {
    // SAFETY: dup creates an independent descriptor owned by fdopendir.
    let duplicated = unsafe { libc::dup(fd) };
    if duplicated < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    // SAFETY: duplicated is a valid directory descriptor. fdopendir owns it.
    let directory = unsafe { libc::fdopendir(duplicated) };
    if directory.is_null() {
        // SAFETY: fdopendir did not take ownership on failure.
        unsafe { libc::close(duplicated) };
        return Err(std::io::Error::last_os_error().into());
    }
    let mut entries = Vec::new();
    loop {
        // SAFETY: directory remains valid until closed below.
        let entry = unsafe { libc::readdir(directory) };
        if entry.is_null() {
            break;
        }
        // SAFETY: d_name is NUL-terminated for a valid dirent.
        let name = unsafe { CStr::from_ptr((*entry).d_name.as_ptr()) };
        if name.to_bytes() == b"." || name.to_bytes() == b".." {
            continue;
        }
        entries.push(name.to_owned());
    }
    // SAFETY: directory was returned by fdopendir and is closed once.
    if unsafe { libc::closedir(directory) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    entries.sort_by(|left, right| left.to_bytes().cmp(right.to_bytes()));
    Ok(entries)
}

fn fsync_fd(fd: RawFd) -> Result<()> {
    // SAFETY: fd is open and owned by the caller.
    if unsafe { libc::fsync(fd) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    Ok(())
}

#[cfg(target_os = "linux")]
fn has_live_reference(candidate: &Path) -> bool {
    if has_mount_reference(candidate) {
        return true;
    }
    let Ok(processes) = fs::read_dir("/proc") else {
        return true;
    };
    for process in processes.flatten() {
        let Some(pid) = process
            .file_name()
            .to_str()
            .and_then(|value| value.parse::<u32>().ok())
        else {
            continue;
        };
        let base = std::path::PathBuf::from("/proc").join(pid.to_string());
        for link in [base.join("cwd"), base.join("exe")] {
            match fs::read_link(link) {
                Ok(target) if target.starts_with(candidate) => return true,
                Ok(_) => {}
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(_) => return true,
            }
        }
        match fs::read_dir(base.join("fd")) {
            Ok(descriptors) => {
                for descriptor in descriptors {
                    let Ok(descriptor) = descriptor else {
                        return true;
                    };
                    match fs::read_link(descriptor.path()) {
                        Ok(target) if target.starts_with(candidate) => return true,
                        Ok(_) => {}
                        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                        Err(_) => return true,
                    }
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return true,
        }
    }
    false
}

#[cfg(target_os = "linux")]
fn has_mount_reference(candidate: &Path) -> bool {
    let Ok(mountinfo) = fs::read_to_string("/proc/self/mountinfo") else {
        return true;
    };
    mountinfo_references_candidate(&mountinfo, candidate).unwrap_or(true)
}

#[cfg(target_os = "linux")]
#[derive(Debug)]
struct MountInfoEntry {
    device: String,
    root: std::path::PathBuf,
    mount_point: std::path::PathBuf,
}

#[cfg(target_os = "linux")]
fn mountinfo_references_candidate(mountinfo: &str, candidate: &Path) -> Option<bool> {
    let mut entries = Vec::new();
    for line in mountinfo.lines() {
        let fields: Vec<&str> = line.split_whitespace().collect();
        let Some(separator) = fields.iter().position(|field| *field == "-") else {
            return None;
        };
        if fields.len() <= 5 || fields.len() <= separator + 2 {
            return None;
        }
        let root = std::path::PathBuf::from(unescape_mountinfo(fields[3])?);
        let mount_point = std::path::PathBuf::from(unescape_mountinfo(fields[4])?);
        if !root.is_absolute() || !mount_point.is_absolute() {
            return None;
        }
        entries.push(MountInfoEntry {
            device: fields[2].to_owned(),
            root,
            mount_point,
        });
    }
    for entry in &entries {
        if entry.mount_point != Path::new("/") && paths_overlap(&entry.mount_point, candidate) {
            return Some(true);
        }
    }
    for (index, entry) in entries.iter().enumerate() {
        if entry.root == Path::new("/") {
            continue;
        }
        let mut found_base = false;
        for (other_index, base) in entries.iter().enumerate() {
            if other_index == index
                || base.device != entry.device
                || !entry.root.starts_with(&base.root)
            {
                continue;
            }
            found_base = true;
            let relative = entry.root.strip_prefix(&base.root).ok()?;
            let bind_source = base.mount_point.join(relative);
            if paths_overlap(&bind_source, candidate) {
                return Some(true);
            }
        }
        if !found_base {
            return None;
        }
    }
    Some(false)
}

#[cfg(target_os = "linux")]
fn paths_overlap(left: &Path, right: &Path) -> bool {
    left.starts_with(right) || right.starts_with(left)
}

#[cfg(target_os = "linux")]
fn unescape_mountinfo(value: &str) -> Option<String> {
    let bytes = value.as_bytes();
    let mut output = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] != b'\\' {
            output.push(bytes[index]);
            index += 1;
            continue;
        }
        let escape = bytes.get(index..index + 4)?;
        output.push(match escape {
            b"\\040" => b' ',
            b"\\011" => b'\t',
            b"\\012" => b'\n',
            b"\\134" => b'\\',
            _ => return None,
        });
        index += 4;
    }
    String::from_utf8(output).ok()
}

#[cfg(not(target_os = "linux"))]
fn has_live_reference(_candidate: &Path) -> bool {
    false
}

fn limit_exceeded() -> ExecutorError {
    ExecutorError::rejected(
        "storage_limit_exceeded",
        "The storage operation exceeds a configured hard limit.",
    )
}

fn capacity_invalid() -> ExecutorError {
    ExecutorError::rejected(
        "capacity_topology_invalid",
        "Live LVM capacity topology is invalid.",
    )
}

#[cfg(test)]
mod tests {
    use std::cell::{Cell, RefCell};
    use std::io::Read;
    use std::os::unix::fs::PermissionsExt;

    use ed25519_dalek::{Signer, SigningKey};
    use tempfile::TempDir;

    use crate::model::REQUIRED_PROTECTION_SCOPES;
    use crate::policy::{GuardPolicy, Limits, Policy, RootPolicy, SignedPolicy};

    use super::*;

    #[test]
    fn parses_lvm_capacity_without_commands() {
        let source = r#"
ubuntu-vg {
  extent_size = 8192
  physical_volumes {
    pv0 {
      pe_count = 58837
    }
  }
  logical_volumes {
    ubuntu-lv {
      segment1 {
        extent_count = 53760
      }
    }
  }
}
"#;
        let parsed = parse_lvm_backup(source, "ubuntu-lv").unwrap();
        assert_eq!(parsed.extent_bytes, 4_194_304);
        assert_eq!(parsed.root_extents, 53_760);
        assert_eq!(parsed.total_extents - parsed.used_extents, 5_077);
    }

    #[test]
    fn live_reference_after_staging_rolls_candidate_back() {
        let temp = TempDir::new().unwrap();
        let base = fs::canonicalize(temp.path()).unwrap();
        let cache = base.join("cache");
        fs::create_dir(&cache).unwrap();
        let trash = cache.join(TRASH_NAME);
        fs::create_dir(&trash).unwrap();
        fs::set_permissions(&trash, fs::Permissions::from_mode(0o700)).unwrap();
        let guards = REQUIRED_PROTECTION_SCOPES
            .into_iter()
            .map(|scope| {
                let path = base.join(format!("guard-{scope:?}"));
                fs::create_dir(&path).unwrap();
                GuardPolicy {
                    scope,
                    paths: vec![path],
                }
            })
            .collect();
        let policy = Policy {
            policy_version: "race-test-1".into(),
            protocol_version: "v1".into(),
            node_id: "primary".into(),
            execute_enabled: true,
            preview_ttl_seconds: 300,
            quarantine_retention_seconds: 604_800,
            limits: Limits {
                max_candidates: 10,
                max_bytes_per_operation: 1024 * 1024,
                max_scan_entries: 1000,
                max_scan_depth: 16,
                max_request_bytes: 64 * 1024,
            },
            capacity_topology: None,
            guard_evidence: None,
            roots: vec![RootPolicy {
                root_id: "cache-race".into(),
                kind: RootKind::Cache,
                path: cache.clone(),
                minimum_age_seconds: 0,
            }],
            guards,
        };
        let signing_key = SigningKey::from_bytes(&[31_u8; 32]);
        let signature = signing_key.sign(&serde_json::to_vec(&policy).unwrap());
        let mut verified = VerifiedPolicy::verify(
            SignedPolicy {
                policy,
                signature_hex: hex::encode(signature.to_bytes()),
            },
            &hex::encode(signing_key.verifying_key().to_bytes()),
        )
        .unwrap();
        verified.enable_test_execution();

        let candidate_path = cache.join("candidate");
        fs::create_dir(&candidate_path).unwrap();
        fs::write(candidate_path.join("data"), b"retain-me").unwrap();
        let mut budget = ScanBudget {
            entries: 0,
            maximum: 1000,
            maximum_depth: 16,
        };
        let facts = inspect_tree(
            &candidate_path,
            fs::metadata(&cache).unwrap().dev(),
            0,
            &mut budget,
        )
        .unwrap();
        let candidate = CandidateManifest {
            root_id: "cache-race".into(),
            relative_name: "candidate".into(),
            size_bytes: facts.size_bytes,
            modified_at: facts.modified_at,
            device: facts.device,
            inode: facts.inode,
            tree_digest: facts.digest,
        };
        let referenced = Cell::new(false);
        let held = RefCell::new(None);
        let mut after_staging = |staged: &Path| {
            *held.borrow_mut() = Some(fs::File::open(staged.join("data")).unwrap());
            referenced.set(true);
        };
        let probe = |_path: &Path| referenced.get();
        let error = remove_candidate_with_test_hook(
            &verified,
            &candidate,
            "del_race",
            &mut after_staging,
            &probe,
        )
        .unwrap_err();
        assert_eq!(error.code(), "cleanup_stage_became_referenced");
        assert!(candidate_path.exists());
        assert!(!trash.join("del_race").exists());
        let mut contents = Vec::new();
        held.borrow_mut()
            .as_mut()
            .unwrap()
            .read_to_end(&mut contents)
            .unwrap();
        assert_eq!(contents, b"retain-me");
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn mountinfo_detects_bind_source_from_mount_root() {
        let mountinfo = "\
24 1 8:1 / / rw,relatime - ext4 /dev/sda1 rw
31 24 8:1 /srv/kolibri/data /mnt/kolibri-data rw,relatime - ext4 /dev/sda1 rw
";
        assert_eq!(
            mountinfo_references_candidate(mountinfo, Path::new("/srv/kolibri/data")),
            Some(true)
        );
        assert_eq!(
            mountinfo_references_candidate(mountinfo, Path::new("/srv/unrelated")),
            Some(false)
        );
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn malformed_mountinfo_fails_closed() {
        assert_eq!(
            mountinfo_references_candidate("malformed", Path::new("/srv/data")),
            None
        );
    }
}
