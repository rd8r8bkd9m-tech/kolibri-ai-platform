#!/usr/bin/env python3
"""Launch Home's optional provider-egress SOCKS fallback from a signed selector.

No IP address is stored in the config or source.  The owner signs a durable
``egress_node_id`` and the launcher resolves its current mesh address from the
canonical replicated membership manifest.  The marked Amnezia route remains
primary.  The private key is passed only to OpenSSH by path and is never read
or printed by this program.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from ops.control_plane_endpoint import assert_local_home_control_plane
    from ops.fleet_membership import MeshMembershipSource, canonical_node_id
except ImportError:  # installed standalone beside dependencies
    from control_plane_endpoint import assert_local_home_control_plane
    from fleet_membership import MeshMembershipSource, canonical_node_id


SCHEMA_VERSION = "kolibri.provider-egress.v1"
SIGNATURE_NAMESPACE = "kolibri-provider-egress"
DEFAULT_CONFIG = Path("/etc/kolibri/provider-egress.json")
DEFAULT_SIGNATURE = Path("/etc/kolibri/provider-egress.json.sig")
DEFAULT_ALLOWED_SIGNERS = Path("/etc/kolibri/owner_allowed_signers")
DEFAULT_MEMBERSHIP = Path("/var/lib/kolibri-mesh/peers.json")
DEFAULT_SSH = Path("/usr/bin/ssh")
DEFAULT_SSH_KEYGEN = Path("/usr/bin/ssh-keygen")
MAX_CONFIG_BYTES = 64 * 1024
MAX_SIGNATURE_BYTES = 64 * 1024
SAFE_USER = re.compile(r"[a-z_][a-z0-9_-]{0,31}\Z")
SAFE_SIGNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z")
EXPECTED_KEYS = {
    "schema_version",
    "egress_node_id",
    "ssh_user",
    "ssh_port",
    "identity_file",
    "known_hosts_file",
    "listen_host",
    "listen_port",
    "signer_identity",
}


class ProviderEgressError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderEgressConfig:
    egress_node_id: str
    ssh_user: str
    ssh_port: int
    identity_file: Path
    known_hosts_file: Path
    listen_host: str
    listen_port: int
    signer_identity: str
    endpoint: str


def _read_regular(
    path: Path,
    *,
    max_bytes: int,
    code: str,
    require_private: bool = False,
) -> bytes:
    try:
        value = path.lstat()
        if (
            not stat.S_ISREG(value.st_mode)
            or stat.S_ISLNK(value.st_mode)
            or value.st_nlink != 1
            or value.st_uid != os.geteuid()
            or value.st_mode & (0o077 if require_private else 0o022)
            or not 0 < value.st_size <= max_bytes
        ):
            raise ProviderEgressError(code)
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if (opened.st_dev, opened.st_ino) != (value.st_dev, value.st_ino):
                raise ProviderEgressError(code)
            payload = handle.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ProviderEgressError(code)
        return payload
    except ProviderEgressError:
        raise
    except OSError as exc:
        raise ProviderEgressError(code) from exc


def _require_executable(path: Path, code: str) -> None:
    try:
        value = path.resolve(strict=True).stat()
    except OSError as exc:
        raise ProviderEgressError(code) from exc
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_uid != os.geteuid()
        or value.st_mode & 0o022
        or not value.st_mode & 0o111
    ):
        raise ProviderEgressError(code)


def _require_file_metadata(
    path: Path,
    *,
    code: str,
    require_private: bool = False,
) -> None:
    """Validate a key/public metadata file without reading its contents."""

    try:
        value = path.lstat()
    except OSError as exc:
        raise ProviderEgressError(code) from exc
    if (
        not stat.S_ISREG(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or value.st_nlink != 1
        or value.st_uid != os.geteuid()
        or value.st_mode & (0o077 if require_private else 0o022)
        or not 0 < value.st_size <= MAX_CONFIG_BYTES
    ):
        raise ProviderEgressError(code)


def _load_canonical_config(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular(path, max_bytes=MAX_CONFIG_BYTES, code="provider_egress_config_invalid")
    try:
        value = json.loads(raw.decode("utf-8"))
        canonical = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ProviderEgressError("provider_egress_config_invalid") from exc
    if not isinstance(value, dict) or set(value) != EXPECTED_KEYS or canonical != raw:
        raise ProviderEgressError("provider_egress_config_invalid")
    return value, raw


def _verify_signature(
    payload: bytes,
    signature_path: Path,
    allowed_signers: Path,
    ssh_keygen: Path,
    signer_identity: str,
) -> None:
    _require_executable(ssh_keygen, "provider_egress_signature_verifier_unavailable")
    signature = _read_regular(
        signature_path,
        max_bytes=MAX_SIGNATURE_BYTES,
        code="provider_egress_signature_invalid",
    )
    _read_regular(
        allowed_signers,
        max_bytes=MAX_CONFIG_BYTES,
        code="provider_egress_allowed_signers_invalid",
    )
    try:
        completed = subprocess.run(
            [
                str(ssh_keygen),
                "-Y",
                "verify",
                "-f",
                str(allowed_signers),
                "-I",
                signer_identity,
                "-n",
                SIGNATURE_NAMESPACE,
                "-s",
                str(signature_path),
            ],
            input=payload,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProviderEgressError("provider_egress_signature_verifier_unavailable") from exc
    if completed.returncode != 0 or not signature.startswith(b"-----BEGIN SSH SIGNATURE-----"):
        raise ProviderEgressError("provider_egress_signature_invalid")


def load_config(
    *,
    config_path: Path = DEFAULT_CONFIG,
    signature_path: Path = DEFAULT_SIGNATURE,
    allowed_signers: Path = DEFAULT_ALLOWED_SIGNERS,
    membership_path: Path = DEFAULT_MEMBERSHIP,
    ssh_keygen: Path = DEFAULT_SSH_KEYGEN,
    local_addresses: list[str] | None = None,
) -> ProviderEgressConfig:
    value, canonical = _load_canonical_config(config_path)
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ProviderEgressError("provider_egress_config_schema_invalid")
    signer_identity = str(value.get("signer_identity") or "")
    if not SAFE_SIGNER.fullmatch(signer_identity):
        raise ProviderEgressError("provider_egress_signer_invalid")
    _verify_signature(
        canonical,
        signature_path,
        allowed_signers,
        ssh_keygen,
        signer_identity,
    )
    _require_file_metadata(
        membership_path,
        code="provider_egress_membership_metadata_invalid",
    )
    try:
        assert_local_home_control_plane(
            manifest_path=membership_path,
            local_addresses=local_addresses,
        )
        snapshot = MeshMembershipSource(membership_path).load()
        node_id = canonical_node_id(value.get("egress_node_id"))
    except Exception as exc:
        raise ProviderEgressError("provider_egress_home_membership_invalid") from exc
    if node_id == "home" or node_id not in snapshot.by_id:
        raise ProviderEgressError("provider_egress_node_not_canonical")
    ssh_user = str(value.get("ssh_user") or "")
    ssh_port = value.get("ssh_port")
    listen_host = str(value.get("listen_host") or "")
    listen_port = value.get("listen_port")
    identity_file = Path(str(value.get("identity_file") or ""))
    known_hosts_file = Path(str(value.get("known_hosts_file") or ""))
    if (
        not SAFE_USER.fullmatch(ssh_user)
        or isinstance(ssh_port, bool)
        or not isinstance(ssh_port, int)
        or not 1 <= ssh_port <= 65535
        or listen_host != "127.0.0.1"
        or isinstance(listen_port, bool)
        or not isinstance(listen_port, int)
        or not 1024 <= listen_port <= 65535
        or not identity_file.is_absolute()
        or not known_hosts_file.is_absolute()
    ):
        raise ProviderEgressError("provider_egress_config_invalid")
    _require_file_metadata(
        identity_file,
        code="provider_egress_identity_invalid",
        require_private=True,
    )
    _require_file_metadata(
        known_hosts_file,
        code="provider_egress_known_hosts_invalid",
    )
    return ProviderEgressConfig(
        egress_node_id=node_id,
        ssh_user=ssh_user,
        ssh_port=ssh_port,
        identity_file=identity_file,
        known_hosts_file=known_hosts_file,
        listen_host=listen_host,
        listen_port=listen_port,
        signer_identity=signer_identity,
        endpoint=snapshot.by_id[node_id].mesh_ip,
    )


def ssh_command(config: ProviderEgressConfig, ssh: Path = DEFAULT_SSH) -> list[str]:
    _require_executable(ssh, "provider_egress_ssh_unavailable")
    return [
        str(ssh),
        "-F", "/dev/null",
        "-N",
        "-T",
        "-o", "BatchMode=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={config.known_hosts_file}",
        "-o", "IdentitiesOnly=yes",
        "-o", "ProxyCommand=none",
        "-o", "PermitLocalCommand=no",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=3",
        "-o", "ConnectTimeout=10",
        "-i", str(config.identity_file),
        "-p", str(config.ssh_port),
        "-D", f"{config.listen_host}:{config.listen_port}",
        "--",
        f"{config.ssh_user}@{config.endpoint}",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("check", "run"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--signature", type=Path, default=DEFAULT_SIGNATURE)
    parser.add_argument("--allowed-signers", type=Path, default=DEFAULT_ALLOWED_SIGNERS)
    parser.add_argument("--membership", type=Path, default=DEFAULT_MEMBERSHIP)
    parser.add_argument("--ssh", type=Path, default=DEFAULT_SSH)
    parser.add_argument("--ssh-keygen", type=Path, default=DEFAULT_SSH_KEYGEN)
    args = parser.parse_args(argv)
    try:
        config = load_config(
            config_path=args.config,
            signature_path=args.signature,
            allowed_signers=args.allowed_signers,
            membership_path=args.membership,
            ssh_keygen=args.ssh_keygen,
        )
        command = ssh_command(config, args.ssh)
        if args.command == "check":
            print(json.dumps({
                "schema_version": SCHEMA_VERSION,
                "status": "ready",
                "authority": "home",
                "role": "optional_fallback",
                "egress_node_id": config.egress_node_id,
                "endpoint_source": "canonical_mesh_manifest",
                "listen": f"{config.listen_host}:{config.listen_port}",
            }, sort_keys=True))
            return 0
        environment = {
            "HOME": "/nonexistent",
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        }
        os.execve(str(args.ssh), command, environment)
        return 1  # pragma: no cover
    except ProviderEgressError as exc:
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "reason": str(exc),
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
