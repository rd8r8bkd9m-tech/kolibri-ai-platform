use std::fs;
use std::io::Write;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use ed25519_dalek::{Signer, SigningKey};
use kolibri_storage_executor::{Policy, SignedPolicy};

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("{message}");
            ExitCode::from(64)
        }
    }
}

fn run() -> Result<(), &'static str> {
    let mut arguments = std::env::args_os();
    let _program = arguments.next();
    let policy_path = take_flag(&mut arguments, "--policy")?;
    let private_key_path = take_flag(&mut arguments, "--private-key-file")?;
    if arguments.next().is_some() {
        return Err("unexpected policy signer argument");
    }
    let policy_bytes = read_regular_file(&policy_path, 256 * 1024)?;
    let policy: Policy =
        serde_json::from_slice(&policy_bytes).map_err(|_| "invalid unsigned policy JSON")?;
    let key_metadata =
        fs::symlink_metadata(&private_key_path).map_err(|_| "private key unavailable")?;
    if key_metadata.file_type().is_symlink()
        || !key_metadata.is_file()
        || key_metadata.permissions().mode() & 0o077 != 0
    {
        return Err("private key file must be regular, non-symlink and mode 0600");
    }
    let key_text = String::from_utf8(read_regular_file(&private_key_path, 256)?)
        .map_err(|_| "invalid private key encoding")?;
    let key_bytes = hex::decode(key_text.trim()).map_err(|_| "invalid private key hex")?;
    let key_bytes: [u8; 32] = key_bytes
        .try_into()
        .map_err(|_| "Ed25519 private key must contain exactly 32 bytes")?;
    let signing_key = SigningKey::from_bytes(&key_bytes);
    let canonical = serde_json::to_vec(&policy).map_err(|_| "cannot canonicalize policy")?;
    let signed = SignedPolicy {
        policy,
        signature_hex: hex::encode(signing_key.sign(&canonical).to_bytes()),
    };
    let mut output =
        serde_json::to_vec_pretty(&signed).map_err(|_| "cannot serialize signed policy")?;
    output.push(b'\n');
    std::io::stdout()
        .write_all(&output)
        .map_err(|_| "cannot write signed policy")?;
    Ok(())
}

fn take_flag(
    arguments: &mut impl Iterator<Item = std::ffi::OsString>,
    expected: &str,
) -> Result<PathBuf, &'static str> {
    if arguments.next().as_deref() != Some(std::ffi::OsStr::new(expected)) {
        return Err("invalid policy signer arguments");
    }
    arguments
        .next()
        .map(PathBuf::from)
        .ok_or("missing policy signer argument")
}

fn read_regular_file(path: &Path, maximum: u64) -> Result<Vec<u8>, &'static str> {
    let metadata = fs::symlink_metadata(path).map_err(|_| "file unavailable")?;
    if metadata.file_type().is_symlink() || !metadata.is_file() || metadata.len() > maximum {
        return Err("file is not a bounded regular file");
    }
    fs::read(path).map_err(|_| "cannot read file")
}
