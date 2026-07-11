#!/usr/bin/env python3
"""Authenticated, replicated membership registry for the Kolibri WireGuard mesh.

Every server runs this same registrar.  Membership mutations are authenticated
with a pre-provisioned cluster credential, persisted atomically, reconciled
with deterministic last-writer-wins semantics, and gossiped to bounded peers
already present in membership or explicitly configured as discovery seeds.

The canonical v2 manifest keeps ``records`` (including tombstones) while also
materialising the legacy ``peers`` map so existing Home discovery consumers can
read the same file during a controlled migration.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import concurrent.futures
import fcntl
import hashlib
import hmac
import ipaddress
import json
import os
import random
import re
import secrets
import socket
import stat
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


SCHEMA_VERSION = 3
LEGACY_SCHEMA_VERSIONS = frozenset({1, 2})
DEFAULT_STATE = Path("/var/lib/kolibri-mesh/peers.json")
DEFAULT_PEER_DIR = Path("/etc/wireguard/kolibri-peers.d")
DEFAULT_APPLIED_STATE = Path("/var/lib/kolibri-mesh/applied-public-keys")
DEFAULT_TRUST_FILE = Path("/etc/kolibri/mesh-registry.key")
DEFAULT_IDENTITY_FILE = Path("/etc/kolibri/mesh-identity")
DEFAULT_OWNER_TRUST_DIR = Path("/etc/kolibri/mesh-trust/owners")
DEFAULT_REGISTRAR_TRUST_DIR = Path("/etc/kolibri/mesh-trust/registrars")
DEFAULT_SSH_KEYGEN = Path("/usr/bin/ssh-keygen")
DEFAULT_APPLY_HELPER = Path("/usr/local/sbin/kolibri-mesh-apply-peers")
DEFAULT_INTERFACE = "wg-kolibri"
DEFAULT_PORT = 9291
CGNAT_NETWORK = ipaddress.IPv4Network("100.64.0.0/10")
MAX_BODY_BYTES = 1024 * 1024
MAX_CLOCK_SKEW_SECONDS = 120
MAX_NONCES = 8192
MAX_ORIGIN_REVISION_JUMP = 1024
MAX_INITIAL_ORIGIN_REVISION = 1024
SIGNATURE_NAMESPACE = "kolibri-mesh-v3"
MAX_ENROLLMENT_TTL_SECONDS = 900
NODE_ID_RE = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?\Z")
HOSTNAME_RE = re.compile(
    r"(?=.{1,253}\Z)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)(?:\.(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?))*\Z"
)


class RegistryError(RuntimeError):
    """A stable, non-secret registry error suitable for an API response."""

    def __init__(self, code: str, status: int = HTTPStatus.BAD_REQUEST):
        super().__init__(code)
        self.code = code
        self.status = int(status)


class ApplyPending(RegistryError):
    """State is durable but the local WireGuard reconciliation needs retry."""

    def __init__(self) -> None:
        super().__init__("wireguard_apply_pending", HTTPStatus.ACCEPTED)


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RegistryError(f"{name.lower()}_invalid") from exc
    if value < minimum or value > maximum:
        raise RegistryError(f"{name.lower()}_invalid")
    return value


def canonical_node_id(value: object) -> str:
    node_id = str(value or "").strip().lower().replace("_", "-")
    if not NODE_ID_RE.fullmatch(node_id):
        raise RegistryError("node_id_invalid")
    return node_id


def validate_public_key(value: object) -> str:
    public_key = str(value or "").strip()
    try:
        decoded = base64.b64decode(public_key, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RegistryError("public_key_invalid") from exc
    if len(decoded) != 32 or len(public_key) != 44:
        raise RegistryError("public_key_invalid")
    return public_key


def validate_mesh_ip(value: object) -> str:
    try:
        address = ipaddress.ip_address(str(value or "").strip())
    except ValueError as exc:
        raise RegistryError("mesh_ip_invalid") from exc
    if (
        address.version != 4
        or address.is_unspecified
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or not (address.is_private or address in CGNAT_NETWORK)
    ):
        raise RegistryError("mesh_ip_invalid")
    return str(address)


def validate_endpoint(value: object) -> str:
    endpoint = str(value or "").strip()
    if not endpoint:
        return ""
    if (
        any(character.isspace() for character in endpoint)
        or "/" in endpoint
        or "@" in endpoint
    ):
        raise RegistryError("endpoint_invalid")
    if endpoint.startswith("["):
        closing = endpoint.find("]")
        if closing < 2 or closing + 1 >= len(endpoint) or endpoint[closing + 1] != ":":
            raise RegistryError("endpoint_invalid")
        host = endpoint[1:closing]
        port_text = endpoint[closing + 2 :]
        try:
            ipaddress.IPv6Address(host)
        except ValueError as exc:
            raise RegistryError("endpoint_invalid") from exc
    else:
        if endpoint.count(":") != 1:
            raise RegistryError("endpoint_invalid")
        host, port_text = endpoint.rsplit(":", 1)
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if not HOSTNAME_RE.fullmatch(host):
                raise RegistryError("endpoint_invalid")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise RegistryError("endpoint_invalid") from exc
    if port < 1 or port > 65535:
        raise RegistryError("endpoint_invalid")
    return endpoint


def _nonnegative_int(value: object, code: str) -> int:
    if isinstance(value, bool):
        raise RegistryError(code)
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and len(value) <= 20 and re.fullmatch(r"[0-9]+", value):
        number = int(value)
    else:
        raise RegistryError(code)
    if number < 0 or number > 2**63 - 1:
        raise RegistryError(code)
    return number


def _record_digest(record: Mapping[str, Any]) -> str:
    material = {
        key: record.get(key)
        for key in (
            "node_id",
            "public_key",
            "mesh_ip",
            "endpoint",
            "generation",
            "revision",
            "origin",
            "origin_key_id",
            "tombstone",
            "reason",
            "conflict_with",
            "identity_keys",
            "owner_attestation",
            "authorization",
            "enrollment_nonce_hash",
            "legacy",
        )
        if key in record
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def record_version(record: Mapping[str, Any]) -> tuple[int, int, int, str, str]:
    """Return the total ordering used for convergence.

    Tombstones win a same-generation/same-revision race so a replayed stale live
    record cannot resurrect a deletion.  The origin and digest make concurrent
    writes deterministic without relying on wall-clock ordering.
    """

    return (
        int(record.get("generation", 0)),
        int(record.get("revision", 0)),
        1 if record.get("tombstone") else 0,
        str(record.get("origin") or "legacy"),
        _record_digest(record),
    )


def normalize_identity_keys(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value or len(value) > 4:
        raise RegistryError("identity_keys_invalid")
    normalized: dict[str, str] = {}
    for raw_key_id, raw_public_key in value.items():
        key_id = canonical_node_id(raw_key_id)
        normalized[key_id] = validate_ssh_public_key(raw_public_key)
    return {key: normalized[key] for key in sorted(normalized)}


def normalize_authorization_proof(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RegistryError("authorization_proof_invalid")
    algorithm = str(value.get("algorithm") or "")
    method = str(value.get("method") or "").upper()
    path = str(value.get("path") or "")
    if (
        algorithm != "ssh-ed25519"
        or method != "POST"
        or path
        not in {
            "/v1/mesh/peers",
            "/v1/mesh/enroll",
        }
    ):
        raise RegistryError("authorization_proof_invalid")
    node_id = canonical_node_id(value.get("node_id"))
    key_id = canonical_node_id(value.get("key_id"))
    timestamp = _nonnegative_int(value.get("timestamp"), "authorization_proof_invalid")
    nonce = str(value.get("nonce") or "")
    signature = str(value.get("signature") or "")
    body = str(value.get("body") or "")
    if not re.fullmatch(r"[0-9a-f]{32,128}", nonce):
        raise RegistryError("authorization_proof_invalid")
    try:
        decoded_signature = base64.b64decode(signature, validate=True)
        decoded_body = base64.b64decode(body, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RegistryError("authorization_proof_invalid") from exc
    if (
        not decoded_signature
        or len(decoded_signature) > 16 * 1024
        or len(decoded_body) > 64 * 1024
    ):
        raise RegistryError("authorization_proof_invalid")
    return {
        "algorithm": algorithm,
        "node_id": node_id,
        "key_id": key_id,
        "method": method,
        "path": path,
        "timestamp": timestamp,
        "nonce": nonce,
        "signature": signature,
        "body": body,
    }


def normalize_record(
    value: Mapping[str, Any], *, legacy_mesh_ip: str | None = None
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RegistryError("peer_record_invalid")
    node_id = canonical_node_id(value.get("node_id"))
    raw_tombstone = value.get("tombstone", False)
    if not isinstance(raw_tombstone, bool):
        raise RegistryError("tombstone_invalid")
    tombstone = raw_tombstone
    record: dict[str, Any] = {
        "node_id": node_id,
        "generation": _nonnegative_int(
            value.get("generation", 0), "peer_generation_invalid"
        ),
        "revision": _nonnegative_int(value.get("revision", 0), "peer_revision_invalid"),
        "origin": canonical_node_id(value.get("origin") or "legacy"),
        "tombstone": tombstone,
    }
    if value.get("origin_key_id"):
        record["origin_key_id"] = canonical_node_id(value["origin_key_id"])
    if value.get("identity_keys") is not None:
        record["identity_keys"] = normalize_identity_keys(value["identity_keys"])
    if value.get("owner_attestation") is not None:
        record["owner_attestation"] = normalize_authorization_proof(
            value["owner_attestation"]
        )
    if value.get("authorization") is not None:
        record["authorization"] = normalize_authorization_proof(value["authorization"])
    if value.get("enrollment_nonce_hash"):
        nonce_hash = str(value["enrollment_nonce_hash"])
        if not re.fullmatch(r"[0-9a-f]{64}", nonce_hash):
            raise RegistryError("enrollment_nonce_hash_invalid")
        record["enrollment_nonce_hash"] = nonce_hash
    if value.get("legacy") is not None:
        if not isinstance(value["legacy"], bool):
            raise RegistryError("legacy_record_marker_invalid")
        record["legacy"] = value["legacy"]
    raw_ip = value.get("mesh_ip") or legacy_mesh_ip
    raw_key = value.get("public_key")
    if not tombstone or raw_ip:
        record["mesh_ip"] = validate_mesh_ip(raw_ip)
    if not tombstone or raw_key:
        record["public_key"] = validate_public_key(raw_key)
    endpoint = validate_endpoint(value.get("endpoint"))
    if endpoint:
        record["endpoint"] = endpoint
    if tombstone:
        reason = str(value.get("reason") or "removed").strip().lower()
        if reason not in {"removed", "conflict"}:
            raise RegistryError("tombstone_reason_invalid")
        record["reason"] = reason
        if value.get("conflict_with"):
            record["conflict_with"] = canonical_node_id(value["conflict_with"])
    return record


def _resolve_identity_conflicts(
    records: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Select unique live node/IP/key identities and tombstone deterministic losers."""

    resolved = {node_id: dict(record) for node_id, record in records.items()}
    candidates = [record for record in resolved.values() if not record.get("tombstone")]
    candidates.sort(
        key=lambda item: (record_version(item), item["node_id"]), reverse=True
    )
    claimed_ips: dict[str, str] = {}
    claimed_keys: dict[str, str] = {}
    for record in candidates:
        node_id = record["node_id"]
        mesh_ip = record["mesh_ip"]
        public_key = record["public_key"]
        conflict_with = claimed_ips.get(mesh_ip) or claimed_keys.get(public_key)
        if conflict_with:
            loser = dict(record)
            loser["tombstone"] = True
            loser["reason"] = "conflict"
            loser["conflict_with"] = conflict_with
            resolved[node_id] = loser
            continue
        claimed_ips[mesh_ip] = node_id
        claimed_keys[public_key] = node_id
    return resolved


def empty_manifest(cluster_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "cluster_id": cluster_id,
        "epoch": 0,
        "vector": {},
        "records": {},
        "peers": {},
    }


def normalize_manifest(
    payload: Mapping[str, Any],
    *,
    cluster_id: str,
    remote: bool = False,
    allow_legacy_remote: bool = False,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise RegistryError("manifest_invalid")
    schema_version = _nonnegative_int(
        payload.get("schema_version", 1), "schema_version_invalid"
    )
    if schema_version not in LEGACY_SCHEMA_VERSIONS | {SCHEMA_VERSION}:
        raise RegistryError("schema_version_unsupported")
    declared_cluster = str(payload.get("cluster_id") or "").strip()
    if (
        remote
        and not allow_legacy_remote
        and (schema_version != SCHEMA_VERSION or declared_cluster != cluster_id)
    ):
        raise RegistryError("cluster_or_schema_mismatch", HTTPStatus.CONFLICT)
    if (
        remote
        and allow_legacy_remote
        and schema_version == SCHEMA_VERSION
        and declared_cluster != cluster_id
    ):
        raise RegistryError("cluster_or_schema_mismatch", HTTPStatus.CONFLICT)
    if declared_cluster and declared_cluster != cluster_id:
        raise RegistryError("cluster_or_schema_mismatch", HTTPStatus.CONFLICT)

    by_node: dict[str, dict[str, Any]] = {}
    raw_records = payload.get("records")
    if isinstance(raw_records, Mapping):
        for key, raw_record in raw_records.items():
            record = normalize_record(raw_record)
            if schema_version in LEGACY_SCHEMA_VERSIONS:
                record["legacy"] = True
            if canonical_node_id(key) != record["node_id"]:
                raise RegistryError("record_key_node_id_mismatch")
            current = by_node.get(record["node_id"])
            if current is None or record_version(record) > record_version(current):
                by_node[record["node_id"]] = record
    elif raw_records is not None:
        raise RegistryError("records_invalid")

    # V1 manifests only had peers.  V2 peers are a compatibility projection;
    # records are authoritative when both representations contain a node.
    raw_peers = payload.get("peers", {})
    if isinstance(raw_peers, Mapping):
        for key, raw_peer in raw_peers.items():
            if not isinstance(raw_peer, Mapping):
                raise RegistryError("peer_record_invalid")
            record = normalize_record(raw_peer, legacy_mesh_ip=str(key))
            if schema_version in LEGACY_SCHEMA_VERSIONS:
                record["legacy"] = True
            current = by_node.get(record["node_id"])
            if current is None:
                by_node[record["node_id"]] = record
            elif schema_version == SCHEMA_VERSION and _record_digest(
                record
            ) != _record_digest(current):
                # A v2 file with a stale/tampered compatibility projection is
                # unsafe to consume as canonical state.
                projected = {
                    k: v
                    for k, v in current.items()
                    if k not in {"reason", "conflict_with"}
                }
                if not current.get("tombstone") and _record_digest(
                    record
                ) != _record_digest(projected):
                    raise RegistryError("peers_projection_mismatch")
    else:
        raise RegistryError("peers_invalid")

    resolved = _resolve_identity_conflicts(by_node)
    vector: dict[str, int] = {}
    for record in resolved.values():
        origin = str(record["origin"])
        vector[origin] = max(vector.get(origin, 0), int(record["revision"]))
    # Compatibility-only status projection. Incoming global epochs never
    # participate in ordering or future local mutation numbering.
    high_water = max(vector.values(), default=0)
    peers: dict[str, dict[str, Any]] = {}
    for record in sorted(resolved.values(), key=lambda item: item["node_id"]):
        if record.get("tombstone"):
            continue
        mesh_ip = record["mesh_ip"]
        if mesh_ip in peers:
            raise RegistryError("mesh_ip_not_unique")
        if any(peer["public_key"] == record["public_key"] for peer in peers.values()):
            raise RegistryError("public_key_not_unique")
        peers[mesh_ip] = dict(record)
    return {
        "schema_version": SCHEMA_VERSION,
        "cluster_id": cluster_id,
        "epoch": high_water,
        "vector": {key: vector[key] for key in sorted(vector)},
        "records": {key: resolved[key] for key in sorted(resolved)},
        "peers": {key: peers[key] for key in sorted(peers, key=ipaddress.ip_address)},
    }


def merge_manifests(
    local: Mapping[str, Any],
    remote: Mapping[str, Any],
    *,
    cluster_id: str,
    allow_legacy_remote: bool = False,
) -> dict[str, Any]:
    left = normalize_manifest(local, cluster_id=cluster_id)
    right = normalize_manifest(
        remote,
        cluster_id=cluster_id,
        remote=True,
        allow_legacy_remote=allow_legacy_remote,
    )
    records = {key: dict(value) for key, value in left["records"].items()}
    for node_id, incoming in right["records"].items():
        current = records.get(node_id)
        if current is None or record_version(incoming) > record_version(current):
            is_legacy_migration = (
                allow_legacy_remote and incoming.get("origin") == "legacy"
            )
            if not is_legacy_migration:
                current_generation = int((current or {}).get("generation", 0))
                incoming_generation = int(incoming.get("generation", 0))
                if current is None:
                    if incoming_generation > 1:
                        raise RegistryError(
                            "remote_generation_jump_rejected", HTTPStatus.CONFLICT
                        )
                elif incoming_generation > current_generation + 1:
                    raise RegistryError(
                        "remote_generation_jump_rejected", HTTPStatus.CONFLICT
                    )
                origin = str(incoming["origin"])
                previous_origin_revision = int(left["vector"].get(origin, 0))
                incoming_revision = int(incoming["revision"])
                maximum_revision = (
                    previous_origin_revision + MAX_ORIGIN_REVISION_JUMP
                    if previous_origin_revision
                    else MAX_INITIAL_ORIGIN_REVISION
                )
                if incoming_revision > maximum_revision:
                    raise RegistryError(
                        "remote_origin_revision_jump_rejected", HTTPStatus.CONFLICT
                    )
            records[node_id] = dict(incoming)
    return normalize_manifest(
        {
            "schema_version": SCHEMA_VERSION,
            "cluster_id": cluster_id,
            "records": records,
            "peers": {},
        },
        cluster_id=cluster_id,
    )


def manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    return (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _assert_not_symlink(path: Path, code: str) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(mode):
        raise RegistryError(code)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: Path, content: bytes, *, mode: int = 0o600) -> None:
    _assert_not_symlink(path, "state_symlink_forbidden")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _assert_not_symlink(path.parent, "state_directory_symlink_forbidden")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
        _fsync_directory(path.parent)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class RegistryConfig:
    state_path: Path
    peer_dir: Path
    applied_state: Path
    trust_file: Path
    apply_helper: Path
    interface: str
    bind: str
    port: int
    node_id: str
    cluster_id: str
    identity_file: Path = DEFAULT_IDENTITY_FILE
    identity_key_id: str = ""
    owner_trust_dir: Path = DEFAULT_OWNER_TRUST_DIR
    registrar_trust_dir: Path = DEFAULT_REGISTRAR_TRUST_DIR
    ssh_keygen: Path = DEFAULT_SSH_KEYGEN
    seeds: tuple[str, ...] = ()
    allocation_cidrs: tuple[str, ...] = ()
    allocation_scan_limit: int = 4096
    http_max_workers: int = 32
    http_request_timeout: float = 5.0
    discovery_interval: float = 10.0
    discovery_timeout: float = 0.75
    discovery_max_targets: int = 64
    discovery_workers: int = 4
    backoff_max: float = 120.0

    @classmethod
    def from_env(cls) -> "RegistryConfig":
        bind = os.getenv("KOLIBRI_MESH_BIND", "").strip() or local_mesh_ip()
        raw_seeds = re.split(
            r"[,\s]+", os.getenv("KOLIBRI_MESH_REGISTRY_SEEDS", "").strip()
        )
        seeds = tuple(seed for seed in raw_seeds if seed)
        allocation_cidrs = tuple(
            item
            for item in re.split(
                r"[,\s]+", os.getenv("KOLIBRI_MESH_ADDRESS_POOLS", "").strip()
            )
            if item
        )
        node_id = canonical_node_id(
            os.getenv("KOLIBRI_MESH_NODE_ID") or socket.gethostname()
        )
        return cls(
            state_path=Path(os.getenv("KOLIBRI_MESH_STATE", str(DEFAULT_STATE))),
            peer_dir=Path(os.getenv("KOLIBRI_MESH_PEER_DIR", str(DEFAULT_PEER_DIR))),
            applied_state=Path(
                os.getenv("KOLIBRI_MESH_APPLIED_STATE", str(DEFAULT_APPLIED_STATE))
            ),
            trust_file=Path(
                os.getenv("KOLIBRI_MESH_TRUST_FILE", str(DEFAULT_TRUST_FILE))
            ),
            apply_helper=Path(
                os.getenv("KOLIBRI_MESH_APPLY_HELPER", str(DEFAULT_APPLY_HELPER))
            ),
            interface=os.getenv("KOLIBRI_MESH_IF", DEFAULT_INTERFACE),
            bind=validate_mesh_ip(bind),
            port=_env_int("KOLIBRI_MESH_REGISTRY_PORT", DEFAULT_PORT, 1, 65535),
            node_id=node_id,
            cluster_id=canonical_node_id(
                os.getenv("KOLIBRI_MESH_CLUSTER_ID", "kolibri")
            ),
            identity_file=Path(
                os.getenv("KOLIBRI_MESH_IDENTITY_FILE", str(DEFAULT_IDENTITY_FILE))
            ),
            identity_key_id=canonical_node_id(
                os.getenv("KOLIBRI_MESH_KEY_ID") or node_id
            ),
            owner_trust_dir=Path(
                os.getenv("KOLIBRI_MESH_OWNER_TRUST_DIR", str(DEFAULT_OWNER_TRUST_DIR))
            ),
            registrar_trust_dir=Path(
                os.getenv(
                    "KOLIBRI_MESH_REGISTRAR_TRUST_DIR",
                    str(DEFAULT_REGISTRAR_TRUST_DIR),
                )
            ),
            ssh_keygen=Path(
                os.getenv("KOLIBRI_MESH_SSH_KEYGEN", str(DEFAULT_SSH_KEYGEN))
            ),
            seeds=seeds,
            allocation_cidrs=allocation_cidrs,
            allocation_scan_limit=_env_int(
                "KOLIBRI_MESH_ALLOCATION_SCAN_LIMIT", 4096, 16, 65536
            ),
            http_max_workers=_env_int("KOLIBRI_MESH_HTTP_MAX_WORKERS", 32, 2, 128),
            http_request_timeout=float(
                _env_int("KOLIBRI_MESH_HTTP_REQUEST_TIMEOUT", 5, 1, 30)
            ),
            discovery_interval=float(
                _env_int("KOLIBRI_MESH_DISCOVERY_INTERVAL", 10, 1, 300)
            ),
            discovery_timeout=float(
                _env_int("KOLIBRI_MESH_DISCOVERY_TIMEOUT", 1, 1, 10)
            ),
            discovery_max_targets=_env_int(
                "KOLIBRI_MESH_DISCOVERY_MAX_TARGETS", 64, 1, 256
            ),
            discovery_workers=_env_int("KOLIBRI_MESH_DISCOVERY_WORKERS", 4, 1, 16),
            backoff_max=float(
                _env_int("KOLIBRI_MESH_DISCOVERY_BACKOFF_MAX", 120, 2, 1800)
            ),
        )


def local_mesh_ip(interface: str | None = None) -> str:
    configured = os.getenv("KOLIBRI_MESH_BIND", "").strip()
    if configured:
        return validate_mesh_ip(configured)
    try:
        completed = subprocess.run(
            [
                "ip",
                "-4",
                "-o",
                "addr",
                "show",
                interface or os.getenv("KOLIBRI_MESH_IF", DEFAULT_INTERFACE),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RegistryError("local_mesh_ip_unavailable") from exc
    for line in completed.stdout.splitlines():
        for field in line.split():
            if "/" in field:
                try:
                    return validate_mesh_ip(field.split("/", 1)[0])
                except RegistryError:
                    continue
    raise RegistryError("local_mesh_ip_unavailable")


def read_cluster_secret(path: Path) -> bytes:
    _assert_not_symlink(path, "cluster_trust_symlink_forbidden")
    try:
        metadata = path.stat()
        secret = path.read_bytes().strip()
    except OSError as exc:
        raise RegistryError(
            "cluster_trust_unavailable", HTTPStatus.SERVICE_UNAVAILABLE
        ) from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise RegistryError("cluster_trust_invalid", HTTPStatus.SERVICE_UNAVAILABLE)
    if metadata.st_mode & 0o077:
        raise RegistryError(
            "cluster_trust_permissions_invalid", HTTPStatus.SERVICE_UNAVAILABLE
        )
    if len(secret) < 32 or len(secret) > 4096:
        raise RegistryError("cluster_trust_invalid", HTTPStatus.SERVICE_UNAVAILABLE)
    return secret


class NonceCache:
    def __init__(
        self, *, maximum: int = MAX_NONCES, clock: Callable[[], float] = time.time
    ):
        self.maximum = maximum
        self.clock = clock
        self._values: dict[str, float] = {}
        self._lock = threading.Lock()

    def accept(self, nonce: str, timestamp: int) -> bool:
        now = self.clock()
        with self._lock:
            cutoff = now - MAX_CLOCK_SKEW_SECONDS
            self._values = {
                key: value for key, value in self._values.items() if value >= cutoff
            }
            if nonce in self._values:
                return False
            if len(self._values) >= self.maximum:
                oldest = min(self._values, key=self._values.get)
                del self._values[oldest]
            self._values[nonce] = float(timestamp)
            return True


class RequestAuthenticator:
    """Legacy shared-HMAC v2 helper.

    It is retained for read-migration tests only and is not installed as the
    v3 mutation authenticator. Node and key id are nevertheless signature
    bound so headers cannot be changed without invalidating the request.
    """

    def __init__(
        self,
        secret: bytes,
        *,
        cluster_id: str,
        node_id: str,
        key_id: str = "legacy-shared",
        clock: Callable[[], float] = time.time,
        nonces: NonceCache | None = None,
    ):
        self._secret = secret
        self.cluster_id = cluster_id
        self.node_id = node_id
        self.key_id = canonical_node_id(key_id)
        self.clock = clock
        self.nonces = nonces or NonceCache(clock=clock)

    def _canonical(
        self,
        method: str,
        path: str,
        timestamp: str,
        nonce: str,
        body: bytes,
        node_id: str,
        key_id: str,
    ) -> bytes:
        body_hash = hashlib.sha256(body).hexdigest()
        return (
            f"hmac-sha256\n{method.upper()}\n{path}\n{timestamp}\n{nonce}\n"
            f"{body_hash}\n{self.cluster_id}\n{node_id}\n{key_id}"
        ).encode("utf-8")

    def headers(self, method: str, path: str, body: bytes) -> dict[str, str]:
        timestamp = str(int(self.clock()))
        nonce = secrets.token_hex(16)
        signature = hmac.new(
            self._secret,
            self._canonical(
                method,
                path,
                timestamp,
                nonce,
                body,
                self.node_id,
                self.key_id,
            ),
            hashlib.sha256,
        ).hexdigest()
        return {
            "X-Kolibri-Cluster": self.cluster_id,
            "X-Kolibri-Node": self.node_id,
            "X-Kolibri-Key-Id": self.key_id,
            "X-Kolibri-Signature-Algorithm": "hmac-sha256",
            "X-Kolibri-Timestamp": timestamp,
            "X-Kolibri-Nonce": nonce,
            "X-Kolibri-Signature": signature,
        }

    def verify(
        self, method: str, path: str, body: bytes, headers: Mapping[str, str]
    ) -> str:
        cluster = str(headers.get("X-Kolibri-Cluster") or "")
        try:
            origin = canonical_node_id(headers.get("X-Kolibri-Node"))
        except RegistryError as exc:
            raise RegistryError(
                "authentication_failed", HTTPStatus.UNAUTHORIZED
            ) from exc
        timestamp_text = str(headers.get("X-Kolibri-Timestamp") or "")
        try:
            key_id = canonical_node_id(headers.get("X-Kolibri-Key-Id"))
        except RegistryError as exc:
            raise RegistryError(
                "authentication_failed", HTTPStatus.UNAUTHORIZED
            ) from exc
        nonce = str(headers.get("X-Kolibri-Nonce") or "")
        signature = str(headers.get("X-Kolibri-Signature") or "")
        algorithm = str(headers.get("X-Kolibri-Signature-Algorithm") or "")
        if cluster != self.cluster_id or algorithm != "hmac-sha256":
            raise RegistryError("authentication_failed", HTTPStatus.UNAUTHORIZED)
        if not re.fullmatch(r"[0-9a-f]{32,128}", nonce) or not re.fullmatch(
            r"[0-9a-f]{64}", signature
        ):
            raise RegistryError("authentication_failed", HTTPStatus.UNAUTHORIZED)
        try:
            timestamp = int(timestamp_text)
        except ValueError as exc:
            raise RegistryError(
                "authentication_failed", HTTPStatus.UNAUTHORIZED
            ) from exc
        if abs(self.clock() - timestamp) > MAX_CLOCK_SKEW_SECONDS:
            raise RegistryError("authentication_failed", HTTPStatus.UNAUTHORIZED)
        expected = hmac.new(
            self._secret,
            self._canonical(method, path, timestamp_text, nonce, body, origin, key_id),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise RegistryError("authentication_failed", HTTPStatus.UNAUTHORIZED)
        if not self.nonces.accept(nonce, timestamp):
            raise RegistryError("authentication_failed", HTTPStatus.UNAUTHORIZED)
        return origin


def validate_ssh_public_key(value: object) -> str:
    parts = str(value or "").strip().split()
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise RegistryError("identity_public_key_invalid")
    try:
        decoded = base64.b64decode(parts[1], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RegistryError("identity_public_key_invalid") from exc
    if len(decoded) < 32 or len(decoded) > 1024:
        raise RegistryError("identity_public_key_invalid")
    return f"ssh-ed25519 {parts[1]}"


def request_signature_material(
    *,
    algorithm: str,
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    body: bytes,
    cluster_id: str,
    node_id: str,
    key_id: str,
) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    return (
        f"{algorithm}\n{method.upper()}\n{path}\n{timestamp}\n{nonce}\n"
        f"{body_hash}\n{cluster_id}\n{node_id}\n{key_id}"
    ).encode("utf-8")


@dataclass(frozen=True)
class AuthContext:
    node_id: str
    key_id: str
    role: str
    algorithm: str
    method: str
    path: str
    timestamp: int
    nonce: str
    signature: str
    body: bytes

    def proof(self) -> dict[str, Any]:
        if len(self.body) > 64 * 1024:
            raise RegistryError("authorization_proof_too_large")
        return {
            "algorithm": self.algorithm,
            "node_id": self.node_id,
            "key_id": self.key_id,
            "method": self.method,
            "path": self.path,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "signature": self.signature,
            "body": base64.b64encode(self.body).decode("ascii"),
        }


class OpenSSHTrustStore:
    """Resolve owner/registrar Ed25519 public keys without shared secrets."""

    def __init__(
        self,
        owner_dir: Path,
        registrar_dir: Path,
        *,
        dynamic_resolver: Callable[[str, str], str | None] | None = None,
    ):
        self.owner_dir = owner_dir
        self.registrar_dir = registrar_dir
        self.dynamic_resolver = dynamic_resolver

    def set_dynamic_resolver(self, resolver: Callable[[str, str], str | None]) -> None:
        self.dynamic_resolver = resolver

    def _read_key(self, directory: Path, node_id: str, key_id: str) -> str | None:
        _assert_not_symlink(directory, "identity_trust_directory_symlink_forbidden")
        path = directory / f"{node_id}--{key_id}.pub"
        if path.parent != directory:
            raise RegistryError("identity_trust_path_invalid")
        _assert_not_symlink(path, "identity_trust_key_symlink_forbidden")
        try:
            metadata = path.stat()
            value = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise RegistryError("identity_trust_unavailable") from exc
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o022:
            raise RegistryError("identity_trust_permissions_invalid")
        return validate_ssh_public_key(value)

    def lookup(self, node_id: str, key_id: str) -> tuple[str, str]:
        node_id = canonical_node_id(node_id)
        key_id = canonical_node_id(key_id)
        owner = self._read_key(self.owner_dir, node_id, key_id)
        registrar = self._read_key(self.registrar_dir, node_id, key_id)
        if owner and registrar:
            raise RegistryError("identity_trust_role_ambiguous")
        if owner:
            return owner, "owner"
        if registrar:
            return registrar, "registrar"
        if self.dynamic_resolver:
            dynamic = self.dynamic_resolver(node_id, key_id)
            if dynamic:
                return validate_ssh_public_key(dynamic), "registrar"
        raise RegistryError("authentication_signer_unknown", HTTPStatus.UNAUTHORIZED)


def _ssh_environment() -> dict[str, str]:
    return {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}


def verify_ssh_signature(
    ssh_keygen: Path,
    *,
    public_key: str,
    principal: str,
    material: bytes,
    signature: bytes,
) -> None:
    if not ssh_keygen.is_file() or not os.access(ssh_keygen, os.X_OK):
        raise RegistryError("ssh_keygen_unavailable", HTTPStatus.SERVICE_UNAVAILABLE)
    with tempfile.TemporaryDirectory(prefix="kolibri-mesh-verify-") as directory_name:
        directory = Path(directory_name)
        allowed = directory / "allowed_signers"
        signature_path = directory / "request.sig"
        allowed.write_text(
            f"{principal} {validate_ssh_public_key(public_key)}\n", encoding="utf-8"
        )
        signature_path.write_bytes(signature)
        os.chmod(allowed, 0o600)
        os.chmod(signature_path, 0o600)
        try:
            completed = subprocess.run(
                [
                    str(ssh_keygen),
                    "-Y",
                    "verify",
                    "-f",
                    str(allowed),
                    "-I",
                    principal,
                    "-n",
                    SIGNATURE_NAMESPACE,
                    "-s",
                    str(signature_path),
                ],
                input=material,
                capture_output=True,
                timeout=5,
                check=False,
                env=_ssh_environment(),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RegistryError(
                "signature_verifier_unavailable", HTTPStatus.SERVICE_UNAVAILABLE
            ) from exc
    if completed.returncode != 0:
        raise RegistryError("authentication_failed", HTTPStatus.UNAUTHORIZED)


class OpenSSHSigner:
    def __init__(
        self,
        identity_file: Path,
        *,
        node_id: str,
        key_id: str,
        ssh_keygen: Path = DEFAULT_SSH_KEYGEN,
    ):
        self.identity_file = identity_file
        self.node_id = canonical_node_id(node_id)
        self.key_id = canonical_node_id(key_id)
        self.ssh_keygen = ssh_keygen

    def sign(self, material: bytes) -> bytes:
        _assert_not_symlink(
            self.identity_file, "identity_private_key_symlink_forbidden"
        )
        try:
            metadata = self.identity_file.stat()
        except OSError as exc:
            raise RegistryError(
                "identity_private_key_unavailable", HTTPStatus.SERVICE_UNAVAILABLE
            ) from exc
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
            raise RegistryError(
                "identity_private_key_permissions_invalid",
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        if not self.ssh_keygen.is_file() or not os.access(self.ssh_keygen, os.X_OK):
            raise RegistryError(
                "ssh_keygen_unavailable", HTTPStatus.SERVICE_UNAVAILABLE
            )
        with tempfile.TemporaryDirectory(prefix="kolibri-mesh-sign-") as directory_name:
            data_path = Path(directory_name) / "request"
            data_path.write_bytes(material)
            os.chmod(data_path, 0o600)
            try:
                completed = subprocess.run(
                    [
                        str(self.ssh_keygen),
                        "-Y",
                        "sign",
                        "-f",
                        str(self.identity_file),
                        "-n",
                        SIGNATURE_NAMESPACE,
                        str(data_path),
                    ],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=5,
                    check=False,
                    env=_ssh_environment(),
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise RegistryError(
                    "request_signing_failed", HTTPStatus.SERVICE_UNAVAILABLE
                ) from exc
            signature_path = Path(f"{data_path}.sig")
            if completed.returncode != 0 or not signature_path.is_file():
                raise RegistryError(
                    "request_signing_failed", HTTPStatus.SERVICE_UNAVAILABLE
                )
            signature = signature_path.read_bytes()
        if not signature or len(signature) > 16 * 1024:
            raise RegistryError(
                "request_signing_failed", HTTPStatus.SERVICE_UNAVAILABLE
            )
        return signature


class OpenSSHRequestAuthenticator:
    algorithm = "ssh-ed25519"

    def __init__(
        self,
        signer: OpenSSHSigner,
        trust_store: OpenSSHTrustStore,
        *,
        cluster_id: str,
        clock: Callable[[], float] = time.time,
        nonces: NonceCache | None = None,
    ):
        self.signer = signer
        self.trust_store = trust_store
        self.cluster_id = cluster_id
        self.node_id = signer.node_id
        self.key_id = signer.key_id
        self.clock = clock
        self.nonces = nonces or NonceCache(clock=clock)
        self.ssh_keygen = signer.ssh_keygen

    def headers(self, method: str, path: str, body: bytes) -> dict[str, str]:
        timestamp = str(int(self.clock()))
        nonce = secrets.token_hex(16)
        material = request_signature_material(
            algorithm=self.algorithm,
            method=method,
            path=path,
            timestamp=timestamp,
            nonce=nonce,
            body=body,
            cluster_id=self.cluster_id,
            node_id=self.node_id,
            key_id=self.key_id,
        )
        signature = base64.b64encode(self.signer.sign(material)).decode("ascii")
        return {
            "X-Kolibri-Cluster": self.cluster_id,
            "X-Kolibri-Node": self.node_id,
            "X-Kolibri-Key-Id": self.key_id,
            "X-Kolibri-Signature-Algorithm": self.algorithm,
            "X-Kolibri-Timestamp": timestamp,
            "X-Kolibri-Nonce": nonce,
            "X-Kolibri-Signature": signature,
        }

    def verify(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
        *,
        public_key_override: str | None = None,
        role_override: str | None = None,
        historical: bool = False,
    ) -> AuthContext:
        try:
            node_id = canonical_node_id(headers.get("X-Kolibri-Node"))
            key_id = canonical_node_id(headers.get("X-Kolibri-Key-Id"))
        except RegistryError as exc:
            raise RegistryError(
                "authentication_failed", HTTPStatus.UNAUTHORIZED
            ) from exc
        cluster = str(headers.get("X-Kolibri-Cluster") or "")
        algorithm = str(headers.get("X-Kolibri-Signature-Algorithm") or "")
        timestamp_text = str(headers.get("X-Kolibri-Timestamp") or "")
        nonce = str(headers.get("X-Kolibri-Nonce") or "")
        signature_text = str(headers.get("X-Kolibri-Signature") or "")
        if cluster != self.cluster_id or algorithm != self.algorithm:
            raise RegistryError("authentication_failed", HTTPStatus.UNAUTHORIZED)
        if not re.fullmatch(r"[0-9a-f]{32,128}", nonce):
            raise RegistryError("authentication_failed", HTTPStatus.UNAUTHORIZED)
        try:
            timestamp = int(timestamp_text)
            signature = base64.b64decode(signature_text, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise RegistryError(
                "authentication_failed", HTTPStatus.UNAUTHORIZED
            ) from exc
        if not signature or len(signature) > 16 * 1024:
            raise RegistryError("authentication_failed", HTTPStatus.UNAUTHORIZED)
        if not historical and abs(self.clock() - timestamp) > MAX_CLOCK_SKEW_SECONDS:
            raise RegistryError("authentication_failed", HTTPStatus.UNAUTHORIZED)
        if public_key_override:
            public_key = validate_ssh_public_key(public_key_override)
            role = role_override or "registrar"
        else:
            public_key, role = self.trust_store.lookup(node_id, key_id)
        material = request_signature_material(
            algorithm=algorithm,
            method=method,
            path=path,
            timestamp=timestamp_text,
            nonce=nonce,
            body=body,
            cluster_id=self.cluster_id,
            node_id=node_id,
            key_id=key_id,
        )
        verify_ssh_signature(
            self.ssh_keygen,
            public_key=public_key,
            principal=node_id,
            material=material,
            signature=signature,
        )
        if not historical and not self.nonces.accept(nonce, timestamp):
            raise RegistryError("authentication_failed", HTTPStatus.UNAUTHORIZED)
        return AuthContext(
            node_id=node_id,
            key_id=key_id,
            role=role,
            algorithm=algorithm,
            method=method.upper(),
            path=path,
            timestamp=timestamp,
            nonce=nonce,
            signature=signature_text,
            body=body,
        )

    def verify_proof(
        self,
        proof: Mapping[str, Any],
        *,
        public_key_override: str | None = None,
        role_override: str | None = None,
    ) -> AuthContext:
        if not isinstance(proof, Mapping):
            raise RegistryError("authorization_proof_invalid")
        try:
            body = base64.b64decode(str(proof.get("body") or ""), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise RegistryError("authorization_proof_invalid") from exc
        if len(body) > 64 * 1024:
            raise RegistryError("authorization_proof_invalid")
        headers = {
            "X-Kolibri-Cluster": self.cluster_id,
            "X-Kolibri-Node": str(proof.get("node_id") or ""),
            "X-Kolibri-Key-Id": str(proof.get("key_id") or ""),
            "X-Kolibri-Signature-Algorithm": str(proof.get("algorithm") or ""),
            "X-Kolibri-Timestamp": str(proof.get("timestamp") or ""),
            "X-Kolibri-Nonce": str(proof.get("nonce") or ""),
            "X-Kolibri-Signature": str(proof.get("signature") or ""),
        }
        return self.verify(
            str(proof.get("method") or ""),
            str(proof.get("path") or ""),
            body,
            headers,
            public_key_override=public_key_override,
            role_override=role_override,
            historical=True,
        )


def _proof_json(context: AuthContext) -> dict[str, Any]:
    try:
        payload = json.loads(context.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegistryError("authorization_proof_body_invalid") from exc
    if not isinstance(payload, dict):
        raise RegistryError("authorization_proof_body_invalid")
    return payload


def _peer_identity_projection(peer: Mapping[str, Any]) -> dict[str, Any]:
    projected: dict[str, Any] = {
        "node_id": canonical_node_id(peer.get("node_id")),
        "public_key": validate_public_key(peer.get("public_key")),
    }
    if peer.get("mesh_ip"):
        projected["mesh_ip"] = validate_mesh_ip(peer.get("mesh_ip"))
    endpoint = validate_endpoint(peer.get("endpoint"))
    if endpoint:
        projected["endpoint"] = endpoint
    if peer.get("identity_keys") is not None:
        projected["identity_keys"] = normalize_identity_keys(peer["identity_keys"])
    return projected


class RecordAuthorizer:
    """Verify immutable per-record mutation proofs during transitive gossip."""

    def __init__(self, authenticator: OpenSSHRequestAuthenticator):
        self.authenticator = authenticator

    def _owner_enrollment(
        self, record: Mapping[str, Any], *, require_initial: bool = False
    ) -> AuthContext:
        proof = record.get("owner_attestation")
        context = self.authenticator.verify_proof(proof)
        if context.role != "owner" or context.path != "/v1/mesh/enroll":
            raise RegistryError("owner_enrollment_proof_required", HTTPStatus.FORBIDDEN)
        payload = _proof_json(context)
        if payload.get("operation") not in {"enroll", "rotate"}:
            raise RegistryError("owner_enrollment_proof_invalid")
        raw_peer = payload.get("peer")
        if not isinstance(raw_peer, Mapping):
            raise RegistryError("owner_enrollment_proof_invalid")
        certified = _peer_identity_projection(raw_peer)
        if certified.get("node_id") != record.get("node_id"):
            raise RegistryError("owner_enrollment_proof_invalid")
        for field_name in ("public_key", "mesh_ip", "identity_keys"):
            if field_name in certified and certified[field_name] != record.get(
                field_name
            ):
                raise RegistryError("owner_enrollment_proof_invalid")
        generation = _nonnegative_int(
            payload.get("generation"), "owner_enrollment_proof_invalid"
        )
        if generation != int(record.get("generation", -1)):
            raise RegistryError("owner_enrollment_proof_invalid")
        if require_initial:
            revision = _nonnegative_int(
                payload.get("revision"), "owner_enrollment_proof_invalid"
            )
            if revision != int(record.get("revision", -1)) or certified.get(
                "endpoint"
            ) != record.get("endpoint"):
                raise RegistryError("owner_enrollment_proof_invalid")
        nonce = str(payload.get("enrollment_nonce") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", nonce):
            raise RegistryError("owner_enrollment_proof_invalid")
        expires_at = _nonnegative_int(
            payload.get("expires_at"), "owner_enrollment_proof_invalid"
        )
        if (
            expires_at < context.timestamp
            or expires_at - context.timestamp > MAX_ENROLLMENT_TTL_SECONDS
        ):
            raise RegistryError("owner_enrollment_proof_invalid")
        if hashlib.sha256(nonce.encode("utf-8")).hexdigest() != record.get(
            "enrollment_nonce_hash"
        ):
            raise RegistryError("owner_enrollment_proof_invalid")
        return context

    def identity_from_bootstrap_record(
        self, record: Mapping[str, Any], node_id: str, key_id: str
    ) -> str:
        self._owner_enrollment(record, require_initial=True)
        if canonical_node_id(record.get("node_id")) != canonical_node_id(node_id):
            raise RegistryError(
                "authentication_signer_unknown", HTTPStatus.UNAUTHORIZED
            )
        identity_keys = normalize_identity_keys(record.get("identity_keys"))
        try:
            return identity_keys[canonical_node_id(key_id)]
        except KeyError as exc:
            raise RegistryError(
                "authentication_signer_unknown", HTTPStatus.UNAUTHORIZED
            ) from exc

    def verify_record(
        self,
        record: Mapping[str, Any],
        current: Mapping[str, Any] | None,
    ) -> None:
        normalized = normalize_record(record)
        if normalized.get("legacy"):
            raise RegistryError("legacy_record_sync_forbidden", HTTPStatus.CONFLICT)
        authorization = normalized.get("authorization")
        if not authorization:
            raise RegistryError("record_authorization_missing", HTTPStatus.CONFLICT)

        # Owner enrollment/rotation establishes the node identity certificate
        # and may be relayed by any registrar.
        if normalized.get("owner_attestation") == authorization:
            context = self._owner_enrollment(normalized, require_initial=True)
            if normalized.get("tombstone"):
                raise RegistryError("owner_enrollment_tombstone_invalid")
            if context.role != "owner":
                raise RegistryError("owner_authority_required")
            return

        # Owner-signed removal is destructive and remains verifiable when
        # relayed by ordinary registrars.
        try:
            context = self.authenticator.verify_proof(authorization)
        except RegistryError:
            context = None
        if context and context.role == "owner":
            payload = _proof_json(context)
            if (
                context.path != "/v1/mesh/peers"
                or payload.get("operation") != "remove"
                or canonical_node_id(payload.get("node_id")) != normalized["node_id"]
                or not normalized.get("tombstone")
            ):
                raise RegistryError("owner_removal_proof_invalid")
            expected_generation = _nonnegative_int(
                payload.get("expected_generation"), "owner_removal_proof_invalid"
            )
            revision = _nonnegative_int(
                payload.get("revision"), "owner_removal_proof_invalid"
            )
            if (
                normalized["generation"] != expected_generation + 1
                or normalized["revision"] != revision
            ):
                raise RegistryError("owner_removal_proof_invalid")
            return

        # Self updates are signed by a key from the owner-attested overlap set.
        self._owner_enrollment(normalized)
        identity_keys = normalize_identity_keys(normalized.get("identity_keys"))
        proof_node_id = canonical_node_id(authorization.get("node_id"))
        proof_key_id = canonical_node_id(authorization.get("key_id"))
        if proof_node_id != normalized["node_id"] or proof_key_id not in identity_keys:
            raise RegistryError("self_update_authority_invalid")
        context = self.authenticator.verify_proof(
            authorization,
            public_key_override=identity_keys[proof_key_id],
            role_override="registrar",
        )
        payload = _proof_json(context)
        raw_peer = payload.get("peer")
        if (
            context.path != "/v1/mesh/peers"
            or payload.get("operation") != "upsert"
            or not isinstance(raw_peer, Mapping)
        ):
            raise RegistryError("self_update_proof_invalid")
        projected = _peer_identity_projection(raw_peer)
        for field_name in ("node_id", "public_key", "mesh_ip", "endpoint"):
            if projected.get(field_name) != normalized.get(field_name):
                raise RegistryError("self_update_proof_invalid")
        if (
            _nonnegative_int(payload.get("generation"), "self_update_proof_invalid")
            != normalized["generation"]
            or _nonnegative_int(payload.get("revision"), "self_update_proof_invalid")
            != normalized["revision"]
        ):
            raise RegistryError("self_update_proof_invalid")
        if current:
            for field_name in (
                "mesh_ip",
                "public_key",
                "identity_keys",
                "owner_attestation",
            ):
                if normalized.get(field_name) != current.get(field_name):
                    raise RegistryError("self_update_identity_change_forbidden")


class ManifestStore:
    def __init__(self, path: Path, cluster_id: str):
        self.path = path
        self.cluster_id = cluster_id

    def load(self) -> dict[str, Any]:
        _assert_not_symlink(self.path, "state_symlink_forbidden")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return empty_manifest(self.cluster_id)
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistryError(
                "manifest_unreadable", HTTPStatus.SERVICE_UNAVAILABLE
            ) from exc
        return normalize_manifest(payload, cluster_id=self.cluster_id)

    def write(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        canonical = normalize_manifest(manifest, cluster_id=self.cluster_id)
        atomic_write(self.path, manifest_bytes(canonical), mode=0o600)
        return canonical


class PeerFragments:
    MANAGED_MARKER = "# Managed by Kolibri mesh registry"

    def __init__(self, path: Path):
        self.path = path

    def _ensure_directory(self) -> None:
        _assert_not_symlink(self.path, "peer_directory_symlink_forbidden")
        self.path.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.path.is_dir():
            raise RegistryError("peer_directory_invalid")
        os.chmod(self.path, 0o700)

    def _target(self, mesh_ip: str) -> Path:
        validated = validate_mesh_ip(mesh_ip)
        target = self.path / f"{validated}.conf"
        if target.parent != self.path or target.name != f"{validated}.conf":
            raise RegistryError("peer_fragment_path_invalid")
        _assert_not_symlink(target, "peer_fragment_symlink_forbidden")
        return target

    def preflight(
        self,
        manifest: Mapping[str, Any],
        *,
        stale_mesh_ips: Iterable[str] = (),
    ) -> None:
        """Reject unsafe fragment paths before canonical state is advanced."""

        self._ensure_directory()
        for candidate in self.path.glob("*.conf"):
            _assert_not_symlink(candidate, "peer_fragment_symlink_forbidden")
            if not stat.S_ISREG(candidate.stat().st_mode):
                raise RegistryError("peer_fragment_type_invalid")
        mesh_ips = set(manifest["peers"])
        mesh_ips.update(
            str(record["mesh_ip"])
            for record in manifest["records"].values()
            if record.get("tombstone") and record.get("mesh_ip")
        )
        mesh_ips.update(validate_mesh_ip(value) for value in stale_mesh_ips)
        for mesh_ip in mesh_ips:
            target = self._target(mesh_ip)
            try:
                metadata = target.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise RegistryError("peer_fragment_type_invalid")

    def _content(self, peer: Mapping[str, Any]) -> bytes:
        node_id = canonical_node_id(peer["node_id"])
        public_key = validate_public_key(peer["public_key"])
        mesh_ip = validate_mesh_ip(peer["mesh_ip"])
        endpoint = validate_endpoint(peer.get("endpoint"))
        lines = [
            self.MANAGED_MARKER,
            f"# node_id={node_id}",
            "[Peer]",
            f"PublicKey = {public_key}",
        ]
        if endpoint:
            lines.append(f"Endpoint = {endpoint}")
        lines.extend(
            [
                f"AllowedIPs = {mesh_ip}/32",
                "PersistentKeepalive = 25",
                "",
            ]
        )
        return "\n".join(lines).encode("utf-8")

    def reconcile(
        self,
        manifest: Mapping[str, Any],
        *,
        stale_mesh_ips: Iterable[str] = (),
    ) -> None:
        stale_ips = {validate_mesh_ip(value) for value in stale_mesh_ips}
        self.preflight(manifest, stale_mesh_ips=stale_ips)
        active_ips = set(manifest["peers"])
        for mesh_ip, peer in manifest["peers"].items():
            atomic_write(self._target(mesh_ip), self._content(peer), mode=0o600)
        # Tombstones retain their former mesh IP specifically so recovery can
        # remove a fragment after a crash between manifest and fragment writes.
        for record in manifest["records"].values():
            if not record.get("tombstone") or not record.get("mesh_ip"):
                continue
            stale_ips.add(validate_mesh_ip(record["mesh_ip"]))

        # A crash after the manifest rename but before fragment cleanup loses
        # the old active address from canonical state.  Registry-written files
        # carry a marker, so recovery can remove only those orphaned fragments
        # while leaving pre-existing/unmanaged files untouched.
        for candidate in self.path.glob("*.conf"):
            _assert_not_symlink(candidate, "peer_fragment_symlink_forbidden")
            metadata = candidate.stat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 4096:
                raise RegistryError("peer_fragment_type_invalid")
            filename_ip = candidate.name.removesuffix(".conf")
            try:
                mesh_ip = validate_mesh_ip(filename_ip)
            except RegistryError:
                continue
            if mesh_ip in active_ips or mesh_ip in stale_ips:
                continue
            with candidate.open("r", encoding="utf-8") as stream:
                if stream.readline().rstrip("\n") == self.MANAGED_MARKER:
                    stale_ips.add(mesh_ip)

        for mesh_ip in sorted(stale_ips, key=ipaddress.ip_address):
            if mesh_ip in active_ips:
                continue
            target = self._target(mesh_ip)
            try:
                metadata = target.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise RegistryError("peer_fragment_type_invalid")
            target.unlink()
            _fsync_directory(self.path)


def _parse_fragment(path: Path) -> tuple[str, str, str]:
    _assert_not_symlink(path, "peer_fragment_symlink_forbidden")
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 4096:
        raise RegistryError("peer_fragment_permissions_invalid")
    if metadata.st_mode & 0o077:
        # V1 used the process umask and may have left public peer material
        # world-readable. It is not a secret, but normalize the established
        # fragment in place before parsing and applying it.
        os.chmod(path, 0o600)
    values: dict[str, list[str]] = {"public_key": [], "mesh_ip": [], "endpoint": []}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if (
            not line
            or line.startswith("#")
            or line == "[Peer]"
            or line == "PersistentKeepalive = 25"
        ):
            continue
        if line.startswith("PublicKey = "):
            values["public_key"].append(line.removeprefix("PublicKey = "))
        elif line.startswith("AllowedIPs = "):
            allowed = line.removeprefix("AllowedIPs = ")
            if not allowed.endswith("/32"):
                raise RegistryError("peer_fragment_allowed_ips_invalid")
            values["mesh_ip"].append(allowed[:-3])
        elif line.startswith("Endpoint = "):
            values["endpoint"].append(line.removeprefix("Endpoint = "))
        else:
            raise RegistryError("peer_fragment_directive_invalid")
    if (
        len(values["public_key"]) != 1
        or len(values["mesh_ip"]) != 1
        or len(values["endpoint"]) > 1
    ):
        raise RegistryError("peer_fragment_fields_invalid")
    public_key = validate_public_key(values["public_key"][0])
    mesh_ip = validate_mesh_ip(values["mesh_ip"][0])
    endpoint = validate_endpoint(values["endpoint"][0] if values["endpoint"] else "")
    if path.name != f"{mesh_ip}.conf":
        raise RegistryError("peer_fragment_filename_mismatch")
    return public_key, mesh_ip, endpoint


def _apply_fragments_unlocked(
    config: RegistryConfig,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    """Reconcile only registry-managed WireGuard keys; preserve unknown peers."""

    _assert_not_symlink(config.peer_dir, "peer_directory_symlink_forbidden")
    config.peer_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    desired: dict[str, tuple[str, str]] = {}
    desired_ips: set[str] = set()
    for path in sorted(config.peer_dir.glob("*.conf")):
        public_key, mesh_ip, endpoint = _parse_fragment(path)
        if public_key in desired:
            raise RegistryError("peer_fragment_public_key_not_unique")
        if mesh_ip in desired_ips:
            raise RegistryError("peer_fragment_mesh_ip_not_unique")
        desired[public_key] = (mesh_ip, endpoint)
        desired_ips.add(mesh_ip)

    previous: set[str] = set()
    _assert_not_symlink(config.applied_state, "applied_state_symlink_forbidden")
    try:
        for line in config.applied_state.read_text(encoding="utf-8").splitlines():
            if line.strip():
                previous.add(validate_public_key(line.strip()))
    except FileNotFoundError:
        pass

    for public_key, (mesh_ip, endpoint) in sorted(desired.items()):
        command = ["wg", "set", config.interface, "peer", public_key]
        if endpoint:
            command.extend(["endpoint", endpoint])
        command.extend(["allowed-ips", f"{mesh_ip}/32", "persistent-keepalive", "25"])
        completed = runner(
            command, check=False, capture_output=True, text=True, timeout=10
        )
        if completed.returncode != 0:
            raise ApplyPending()
    for public_key in sorted(previous - set(desired)):
        completed = runner(
            ["wg", "set", config.interface, "peer", public_key, "remove"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if completed.returncode != 0:
            raise ApplyPending()
    content = ("\n".join(sorted(desired)) + ("\n" if desired else "")).encode("ascii")
    atomic_write(config.applied_state, content, mode=0o600)


def apply_fragments(
    config: RegistryConfig,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    """Serialize boot-time and registrar-triggered applies across processes."""

    state_directory = config.applied_state.parent
    _assert_not_symlink(state_directory, "applied_state_directory_symlink_forbidden")
    state_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = state_directory / ".mesh-apply.lock"
    _assert_not_symlink(lock_path, "applied_state_lock_symlink_forbidden")
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        _apply_fragments_unlocked(config, runner=runner)
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


@dataclass(frozen=True)
class MutationResult:
    manifest: dict[str, Any]
    changed: bool
    apply_pending: bool = False
    peer: dict[str, Any] | None = None


class RegistryEngine:
    def __init__(
        self,
        config: RegistryConfig,
        *,
        store: ManifestStore | None = None,
        fragments: PeerFragments | None = None,
        apply_runner: Callable[[], None] | None = None,
        record_authorizer: RecordAuthorizer | None = None,
    ):
        self.config = config
        self.store = store or ManifestStore(config.state_path, config.cluster_id)
        self.fragments = fragments or PeerFragments(config.peer_dir)
        self.apply_runner = apply_runner or self._run_apply_helper
        self.record_authorizer = record_authorizer
        self.lock = threading.RLock()
        self._apply_pending = True

    def _run_apply_helper(self) -> None:
        try:
            completed = subprocess.run(
                [str(self.config.apply_helper)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ApplyPending() from exc
        if completed.returncode != 0:
            raise ApplyPending()

    def _validate_address_scope(self, manifest: Mapping[str, Any]) -> None:
        networks = self._allocation_networks()
        for peer in manifest["peers"].values():
            address = ipaddress.IPv4Address(peer["mesh_ip"])
            if not any(address in network for network in networks):
                raise RegistryError("mesh_ip_outside_address_pool", HTTPStatus.CONFLICT)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return self.store.load()

    def identity_public_key(self, node_id: str, key_id: str) -> str | None:
        with self.lock:
            state = self.store.load()
            record = state["records"].get(canonical_node_id(node_id))
            if not record or record.get("tombstone"):
                return None
            identity_keys = record.get("identity_keys")
            if not isinstance(identity_keys, Mapping):
                return None
            return identity_keys.get(canonical_node_id(key_id))

    def bootstrap_identity_from_manifest(
        self, manifest: Mapping[str, Any], node_id: str, key_id: str
    ) -> str:
        if not self.record_authorizer:
            raise RegistryError(
                "authentication_signer_unknown", HTTPStatus.UNAUTHORIZED
            )
        normalized = normalize_manifest(
            manifest,
            cluster_id=self.config.cluster_id,
            remote=True,
        )
        record = normalized["records"].get(canonical_node_id(node_id))
        if not record:
            raise RegistryError(
                "authentication_signer_unknown", HTTPStatus.UNAUTHORIZED
            )
        return self.record_authorizer.identity_from_bootstrap_record(
            record, node_id, key_id
        )

    def health(self) -> dict[str, Any]:
        with self.lock:
            state = self.store.load()
            return {
                "status": "degraded" if self._apply_pending else "ok",
                "schema_version": SCHEMA_VERSION,
                "node_id": self.config.node_id,
                "epoch": state["epoch"],
                "apply_pending": self._apply_pending,
            }

    def _persist_and_apply(
        self,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        *,
        force_apply: bool = False,
    ) -> MutationResult:
        canonical = normalize_manifest(after, cluster_id=self.config.cluster_id)
        self._validate_address_scope(canonical)
        changed = manifest_bytes(before) != manifest_bytes(canonical)
        stale_mesh_ips = set(before["peers"]) - set(canonical["peers"])
        should_apply = changed or force_apply or self._apply_pending
        if should_apply:
            self.fragments.preflight(canonical, stale_mesh_ips=stale_mesh_ips)
        if changed:
            canonical = self.store.write(canonical)
        if not should_apply:
            return MutationResult(canonical, changed, False)
        apply_pending = False
        try:
            self.fragments.reconcile(canonical, stale_mesh_ips=stale_mesh_ips)
            self.apply_runner()
        except (ApplyPending, OSError, subprocess.SubprocessError):
            apply_pending = True
        self._apply_pending = apply_pending
        return MutationResult(canonical, changed, apply_pending)

    def recover(self) -> MutationResult:
        with self.lock:
            state = self.store.load()
            return self._persist_and_apply(state, state, force_apply=True)

    def retry_pending_apply(self) -> MutationResult:
        with self.lock:
            state = self.store.load()
            if not self._apply_pending:
                return MutationResult(state, False, False)
            return self._persist_and_apply(state, state, force_apply=True)

    def upsert(
        self,
        peer: Mapping[str, Any],
        *,
        authority: AuthContext | None = None,
        generation: int | None = None,
        revision: int | None = None,
    ) -> MutationResult:
        requested = normalize_record(
            {
                **dict(peer),
                "generation": 0,
                "revision": 0,
                "origin": self.config.node_id,
                "tombstone": False,
            }
        )
        with self.lock:
            before = self.store.load()
            current = before["records"].get(requested["node_id"])
            if authority:
                if (
                    authority.role != "registrar"
                    or authority.node_id != requested["node_id"]
                ):
                    raise RegistryError(
                        "self_update_authority_required", HTTPStatus.FORBIDDEN
                    )
                if (
                    not current
                    or current.get("tombstone")
                    or current.get("legacy")
                    or not current.get("owner_attestation")
                    or authority.key_id not in current.get("identity_keys", {})
                ):
                    raise RegistryError(
                        "owner_enrollment_required", HTTPStatus.FORBIDDEN
                    )
                if requested["mesh_ip"] != current.get("mesh_ip") or requested[
                    "public_key"
                ] != current.get("public_key"):
                    raise RegistryError(
                        "self_update_identity_change_forbidden", HTTPStatus.FORBIDDEN
                    )
                requested_identity_keys = requested.get("identity_keys")
                if (
                    requested_identity_keys is not None
                    and requested_identity_keys != current.get("identity_keys")
                ):
                    raise RegistryError(
                        "self_update_identity_change_forbidden", HTTPStatus.FORBIDDEN
                    )
                expected_generation = int(current["generation"])
                expected_revision = int(before["vector"].get(authority.node_id, 0)) + 1
                if generation != expected_generation or revision != expected_revision:
                    raise RegistryError(
                        "mutation_revision_conflict", HTTPStatus.CONFLICT
                    )
                record = {
                    **current,
                    "generation": expected_generation,
                    "revision": expected_revision,
                    "origin": authority.node_id,
                    "origin_key_id": authority.key_id,
                    "authorization": authority.proof(),
                    "tombstone": False,
                }
                if requested.get("endpoint"):
                    record["endpoint"] = requested["endpoint"]
                else:
                    record.pop("endpoint", None)
                if self.record_authorizer:
                    self.record_authorizer.verify_record(record, current)
                after = {
                    **before,
                    "records": {**before["records"], record["node_id"]: record},
                    "peers": {},
                }
                result = self._persist_and_apply(before, after)
                return MutationResult(
                    result.manifest, result.changed, result.apply_pending, record
                )
            identity_fields = ("node_id", "public_key", "mesh_ip", "endpoint")
            if (
                current
                and not current.get("tombstone")
                and all(
                    str(current.get(field) or "") == str(requested.get(field) or "")
                    for field in identity_fields
                )
            ):
                result = self._persist_and_apply(before, before, force_apply=True)
                return MutationResult(
                    result.manifest, False, result.apply_pending, dict(current)
                )
            for other in before["peers"].values():
                if other["node_id"] == requested["node_id"]:
                    continue
                if other["mesh_ip"] == requested["mesh_ip"]:
                    raise RegistryError("mesh_ip_conflict", HTTPStatus.CONFLICT)
                if other["public_key"] == requested["public_key"]:
                    raise RegistryError("public_key_conflict", HTTPStatus.CONFLICT)
            revision = int(before["vector"].get(self.config.node_id, 0)) + 1
            generation = (
                int(current.get("generation", 0)) + 1
                if current and current.get("tombstone")
                else int((current or {}).get("generation", 1))
            )
            record = {
                **requested,
                "generation": generation,
                "revision": revision,
                "origin": self.config.node_id,
            }
            after = {
                **before,
                "records": {**before["records"], record["node_id"]: record},
                "peers": {},
            }
            result = self._persist_and_apply(before, after)
            return MutationResult(
                result.manifest, result.changed, result.apply_pending, record
            )

    def enroll_owner(
        self,
        peer: Mapping[str, Any],
        *,
        authority: AuthContext,
        generation: int,
        revision: int,
        enrollment_nonce: str,
        expires_at: int,
    ) -> MutationResult:
        if authority.role != "owner" or authority.path != "/v1/mesh/enroll":
            raise RegistryError("owner_authority_required", HTTPStatus.FORBIDDEN)
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", enrollment_nonce):
            raise RegistryError("enrollment_nonce_invalid")
        now = int(time.time())
        if (
            expires_at < now
            or expires_at < authority.timestamp
            or expires_at - authority.timestamp > MAX_ENROLLMENT_TTL_SECONDS
        ):
            raise RegistryError("enrollment_credential_expired", HTTPStatus.FORBIDDEN)
        raw_peer = dict(peer)
        node_id = canonical_node_id(raw_peer.get("node_id"))
        identity_keys = normalize_identity_keys(raw_peer.get("identity_keys"))
        with self.lock:
            before = self.store.load()
            current = before["records"].get(node_id)
            proof = authority.proof()
            if current and current.get("authorization") == proof:
                result = self._persist_and_apply(before, before, force_apply=True)
                return MutationResult(
                    result.manifest, False, result.apply_pending, dict(current)
                )
            expected_generation = int((current or {}).get("generation", 0)) + 1
            expected_revision = int(before["vector"].get(node_id, 0)) + 1
            if generation != expected_generation or revision != expected_revision:
                raise RegistryError("mutation_revision_conflict", HTTPStatus.CONFLICT)
            nonce_hash = hashlib.sha256(enrollment_nonce.encode("utf-8")).hexdigest()
            if any(
                record.get("enrollment_nonce_hash") == nonce_hash
                for record in before["records"].values()
            ):
                raise RegistryError(
                    "enrollment_credential_replayed", HTTPStatus.CONFLICT
                )
            mesh_ip = raw_peer.get("mesh_ip") or self.allocate()
            record = normalize_record(
                {
                    **raw_peer,
                    "mesh_ip": mesh_ip,
                    "identity_keys": identity_keys,
                    "generation": generation,
                    "revision": revision,
                    "origin": node_id,
                    "origin_key_id": sorted(identity_keys)[0],
                    "tombstone": False,
                    "owner_attestation": proof,
                    "authorization": proof,
                    "enrollment_nonce_hash": nonce_hash,
                }
            )
            for other in before["peers"].values():
                if other["node_id"] == node_id:
                    continue
                if other["mesh_ip"] == record["mesh_ip"]:
                    raise RegistryError("mesh_ip_conflict", HTTPStatus.CONFLICT)
                if other["public_key"] == record["public_key"]:
                    raise RegistryError("public_key_conflict", HTTPStatus.CONFLICT)
            if self.record_authorizer:
                self.record_authorizer.verify_record(record, current)
            after = {
                **before,
                "records": {**before["records"], node_id: record},
                "peers": {},
            }
            result = self._persist_and_apply(before, after)
            return MutationResult(
                result.manifest, result.changed, result.apply_pending, record
            )

    def remove(
        self,
        node_id: str,
        *,
        authority: AuthContext | None = None,
        expected_generation: int | None = None,
        revision: int | None = None,
    ) -> MutationResult:
        normalized_node_id = canonical_node_id(node_id)
        with self.lock:
            before = self.store.load()
            current = before["records"].get(normalized_node_id)
            if authority:
                if authority.role != "owner":
                    raise RegistryError(
                        "owner_authority_required", HTTPStatus.FORBIDDEN
                    )
                if not current:
                    raise RegistryError("peer_not_found", HTTPStatus.NOT_FOUND)
                required_generation = int(current.get("generation", 0))
                required_revision = int(before["vector"].get(authority.node_id, 0)) + 1
                if (
                    expected_generation != required_generation
                    or revision != required_revision
                ):
                    raise RegistryError(
                        "mutation_revision_conflict", HTTPStatus.CONFLICT
                    )
                tombstone = {
                    **current,
                    "node_id": normalized_node_id,
                    "generation": required_generation + 1,
                    "revision": required_revision,
                    "origin": authority.node_id,
                    "origin_key_id": authority.key_id,
                    "authorization": authority.proof(),
                    "tombstone": True,
                    "reason": "removed",
                }
                tombstone.pop("conflict_with", None)
                tombstone.pop("legacy", None)
                if self.record_authorizer:
                    self.record_authorizer.verify_record(tombstone, current)
                after = {
                    **before,
                    "records": {**before["records"], normalized_node_id: tombstone},
                    "peers": {},
                }
                result = self._persist_and_apply(before, after)
                return MutationResult(
                    result.manifest, result.changed, result.apply_pending, tombstone
                )
            if current and current.get("tombstone"):
                result = self._persist_and_apply(before, before, force_apply=True)
                return MutationResult(
                    result.manifest, False, result.apply_pending, dict(current)
                )
            revision = int(before["vector"].get(self.config.node_id, 0)) + 1
            tombstone: dict[str, Any] = {
                "node_id": normalized_node_id,
                "generation": int((current or {}).get("generation", 0)) + 1,
                "revision": revision,
                "origin": self.config.node_id,
                "tombstone": True,
                "reason": "removed",
            }
            for field_name in ("mesh_ip", "public_key", "endpoint"):
                if current and current.get(field_name):
                    tombstone[field_name] = current[field_name]
            after = {
                **before,
                "records": {**before["records"], normalized_node_id: tombstone},
                "peers": {},
            }
            result = self._persist_and_apply(before, after)
            return MutationResult(
                result.manifest, result.changed, result.apply_pending, tombstone
            )

    def _allocation_networks(self) -> list[ipaddress.IPv4Network]:
        values = list(self.config.allocation_cidrs)
        if not values:
            try:
                completed = subprocess.run(
                    ["ip", "-4", "-o", "addr", "show", self.config.interface],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise RegistryError(
                    "mesh_address_pool_unavailable", HTTPStatus.SERVICE_UNAVAILABLE
                ) from exc
            values = [
                field
                for line in completed.stdout.splitlines()
                for field in line.split()
                if "/" in field
            ]
        networks: list[ipaddress.IPv4Network] = []
        for value in values:
            try:
                interface = ipaddress.ip_interface(value)
            except ValueError as exc:
                raise RegistryError("mesh_address_pool_invalid") from exc
            if interface.version != 4 or interface.network.prefixlen < 8:
                raise RegistryError("mesh_address_pool_invalid")
            networks.append(interface.network)
        if not networks:
            raise RegistryError(
                "mesh_address_pool_unavailable", HTTPStatus.SERVICE_UNAVAILABLE
            )
        return sorted(
            set(networks),
            key=lambda network: (int(network.network_address), network.prefixlen),
        )

    def allocate(self) -> str:
        with self.lock:
            state = self.store.load()
            occupied = {
                record["mesh_ip"]
                for record in state["records"].values()
                if record.get("mesh_ip")
            }
            occupied.add(self.config.bind)
            scanned = 0
            for network in self._allocation_networks():
                for address in network.hosts():
                    scanned += 1
                    if scanned > self.config.allocation_scan_limit:
                        raise RegistryError(
                            "mesh_address_pool_scan_limit", HTTPStatus.CONFLICT
                        )
                    candidate = str(address)
                    if candidate not in occupied:
                        return candidate
        raise RegistryError("mesh_address_pool_exhausted", HTTPStatus.CONFLICT)

    def enroll_auto(self, peer: Mapping[str, Any]) -> MutationResult:
        with self.lock:
            mesh_ip = self.allocate()
            return self.upsert({**dict(peer), "mesh_ip": mesh_ip})

    def merge(
        self, remote: Mapping[str, Any], *, allow_legacy_remote: bool = False
    ) -> MutationResult:
        with self.lock:
            before = self.store.load()
            normalized_remote = normalize_manifest(
                remote,
                cluster_id=self.config.cluster_id,
                remote=True,
                allow_legacy_remote=allow_legacy_remote,
            )
            if self.record_authorizer and not allow_legacy_remote:
                for node_id, incoming in normalized_remote["records"].items():
                    current = before["records"].get(node_id)
                    if current is None or record_version(incoming) > record_version(
                        current
                    ):
                        self.record_authorizer.verify_record(incoming, current)
            after = merge_manifests(
                before,
                normalized_remote,
                cluster_id=self.config.cluster_id,
                allow_legacy_remote=allow_legacy_remote,
            )
            return self._persist_and_apply(before, after)


def _json_body(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def signed_request(
    authenticator: RequestAuthenticator,
    method: str,
    url: str,
    *,
    payload: Mapping[str, Any] | None = None,
    timeout: float = 1.0,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise RegistryError("registry_url_invalid")
    path = parsed.path or "/"
    if parsed.query or parsed.fragment:
        raise RegistryError("registry_url_invalid")
    body = _json_body(payload) if payload is not None else b""
    headers = authenticator.headers(method, path, body)
    if body:
        headers["Content-Type"] = "application/json"
    request = Request(
        url,
        data=body if method.upper() != "GET" else None,
        headers=headers,
        method=method.upper(),
    )
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read(MAX_BODY_BYTES + 1)
    except (HTTPError, URLError, OSError) as exc:
        raise RegistryError("registry_request_failed", HTTPStatus.BAD_GATEWAY) from exc
    if len(raw) > MAX_BODY_BYTES:
        raise RegistryError("registry_response_too_large", HTTPStatus.BAD_GATEWAY)
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegistryError(
            "registry_response_invalid", HTTPStatus.BAD_GATEWAY
        ) from exc
    if not isinstance(decoded, dict):
        raise RegistryError("registry_response_invalid", HTTPStatus.BAD_GATEWAY)
    return decoded


@dataclass
class BackoffState:
    failures: int = 0
    retry_at: float = 0.0


class DiscoveryLoop:
    def __init__(
        self,
        config: RegistryConfig,
        engine: RegistryEngine,
        authenticator: OpenSSHRequestAuthenticator,
        *,
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[float, float], float] = random.uniform,
        opener: Callable[..., Any] = urlopen,
    ):
        self.config = config
        self.engine = engine
        self.authenticator = authenticator
        self.clock = clock
        self.jitter = jitter
        self.opener = opener
        self.backoff: dict[str, BackoffState] = {}

    def targets(self) -> list[str]:
        state = self.engine.snapshot()
        urls: set[str] = set()
        for seed in self.config.seeds:
            value = seed if "://" in seed else f"http://{seed}"
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                continue
            try:
                port = parsed.port or self.config.port
            except ValueError:
                continue
            host = (
                f"[{parsed.hostname}]"
                if ":" in parsed.hostname and not parsed.hostname.startswith("[")
                else parsed.hostname
            )
            urls.add(f"{parsed.scheme}://{host}:{port}")
        for peer in state["peers"].values():
            if peer["mesh_ip"] == self.config.bind:
                continue
            urls.add(f"http://{peer['mesh_ip']}:{self.config.port}")
        return sorted(urls)[: self.config.discovery_max_targets]

    def _exchange(self, base_url: str) -> None:
        remote = signed_request(
            self.authenticator,
            "GET",
            f"{base_url}/v1/mesh/peers",
            timeout=self.config.discovery_timeout,
            opener=self.opener,
        )
        schema_version = _nonnegative_int(
            remote.get("schema_version", 1), "schema_version_invalid"
        )
        if schema_version == 1:
            # The legacy service has no authenticated /sync route.  The pull
            # already advanced local state; old registrars will consume the
            # live compatibility projection through their existing GET loop.
            self.engine.merge(remote, allow_legacy_remote=True)
            return
        if schema_version != SCHEMA_VERSION:
            # Shared-HMAC v2 state is local migration input only. It is never
            # accepted from an unsigned read response as remote authority.
            raise RegistryError("legacy_v2_remote_sync_forbidden", HTTPStatus.CONFLICT)
        signed_request(
            self.authenticator,
            "POST",
            f"{base_url}/v1/mesh/sync",
            payload={"manifest": self.engine.snapshot()},
            timeout=self.config.discovery_timeout,
            opener=self.opener,
        )

    def run_once(self) -> int:
        now = self.clock()
        current_targets = self.targets()
        target_set = set(current_targets)
        self.backoff = {
            target: state
            for target, state in self.backoff.items()
            if target in target_set
        }
        targets = [
            target
            for target in current_targets
            if self.backoff.get(target, BackoffState()).retry_at <= now
        ]
        successes = 0

        def exchange(target: str) -> tuple[str, bool]:
            try:
                self._exchange(target)
                return target, True
            except (RegistryError, OSError):
                return target, False

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.config.discovery_workers
        ) as executor:
            for target, success in executor.map(exchange, targets):
                if success:
                    successes += 1
                    self.backoff[target] = BackoffState()
                    continue
                previous = self.backoff.get(target, BackoffState())
                failures = min(previous.failures + 1, 16)
                ceiling = min(
                    self.config.backoff_max,
                    self.config.discovery_interval * (2**failures),
                )
                self.backoff[target] = BackoffState(
                    failures=failures,
                    retry_at=now + self.jitter(self.config.discovery_interval, ceiling),
                )
        self.engine.retry_pending_apply()
        return successes

    def run_forever(self) -> None:
        while True:
            self.run_once()
            time.sleep(self.config.discovery_interval)


class RegistryHandler(BaseHTTPRequestHandler):
    server: "RegistryHTTPServer"

    def _write_json(self, status: int, payload: Mapping[str, Any]) -> None:
        encoded = _json_body(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise RegistryError("content_length_invalid") from exc
        if length < 0 or length > MAX_BODY_BYTES:
            raise RegistryError(
                "request_too_large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE
            )
        body = self.rfile.read(length)
        if len(body) != length:
            raise RegistryError("request_body_incomplete")
        return body

    def _json(self, body: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RegistryError("request_json_invalid") from exc
        if not isinstance(payload, dict):
            raise RegistryError("request_json_invalid")
        return payload

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        try:
            if self.path == "/healthz":
                self._write_json(HTTPStatus.OK, self.server.engine.health())
                return
            if self.path != "/v1/mesh/peers":
                raise RegistryError("not_found", HTTPStatus.NOT_FOUND)
            # Read-only GET intentionally remains compatible with the v1
            # registrar during the 21-node rolling migration.  Every state
            # mutation requires v3 per-node Ed25519 authentication.
            self._write_json(HTTPStatus.OK, self.server.engine.snapshot())
        except RegistryError as exc:
            self._write_json(exc.status, {"error": exc.code})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        try:
            if self.path not in {
                "/v1/mesh/peers",
                "/v1/mesh/sync",
                "/v1/mesh/allocate",
                "/v1/mesh/enroll",
            }:
                raise RegistryError("not_found", HTTPStatus.NOT_FOUND)
            body = self._body()
            payload = self._json(body)
            try:
                authority = self.server.authenticator.verify(
                    "POST", self.path, body, self.headers
                )
            except RegistryError as exc:
                if (
                    exc.code != "authentication_signer_unknown"
                    or self.path != "/v1/mesh/sync"
                ):
                    raise
                remote = payload.get("manifest")
                if not isinstance(remote, dict):
                    raise RegistryError("manifest_invalid") from exc
                node_id = canonical_node_id(self.headers.get("X-Kolibri-Node"))
                key_id = canonical_node_id(self.headers.get("X-Kolibri-Key-Id"))
                public_key = self.server.engine.bootstrap_identity_from_manifest(
                    remote, node_id, key_id
                )
                authority = self.server.authenticator.verify(
                    "POST",
                    self.path,
                    body,
                    self.headers,
                    public_key_override=public_key,
                    role_override="registrar",
                )
            if not isinstance(authority, AuthContext):
                raise RegistryError(
                    "legacy_hmac_mutation_forbidden", HTTPStatus.FORBIDDEN
                )
            if self.path == "/v1/mesh/sync":
                remote = payload.get("manifest")
                if not isinstance(remote, dict):
                    raise RegistryError("manifest_invalid")
                result = self.server.engine.merge(remote)
            elif self.path == "/v1/mesh/enroll":
                if payload.get("operation") not in {"enroll", "rotate"}:
                    raise RegistryError("operation_invalid")
                peer = payload.get("peer")
                if not isinstance(peer, dict):
                    raise RegistryError("peer_record_invalid")
                result = self.server.engine.enroll_owner(
                    peer,
                    authority=authority,
                    generation=_nonnegative_int(
                        payload.get("generation"), "generation_invalid"
                    ),
                    revision=_nonnegative_int(
                        payload.get("revision"), "revision_invalid"
                    ),
                    enrollment_nonce=str(payload.get("enrollment_nonce") or ""),
                    expires_at=_nonnegative_int(
                        payload.get("expires_at"), "expires_at_invalid"
                    ),
                )
            elif self.path == "/v1/mesh/allocate":
                mesh_ip = self.server.engine.allocate()
                self._write_json(HTTPStatus.OK, {"status": "ok", "mesh_ip": mesh_ip})
                return
            else:
                operation = str(payload.get("operation") or "upsert")
                if operation == "remove":
                    result = self.server.engine.remove(
                        str(payload.get("node_id") or ""),
                        authority=authority,
                        expected_generation=_nonnegative_int(
                            payload.get("expected_generation"),
                            "expected_generation_invalid",
                        ),
                        revision=_nonnegative_int(
                            payload.get("revision"), "revision_invalid"
                        ),
                    )
                elif operation == "upsert":
                    peer = payload.get("peer", payload)
                    if not isinstance(peer, dict):
                        raise RegistryError("peer_record_invalid")
                    result = self.server.engine.upsert(
                        peer,
                        authority=authority,
                        generation=_nonnegative_int(
                            payload.get("generation"), "generation_invalid"
                        ),
                        revision=_nonnegative_int(
                            payload.get("revision"), "revision_invalid"
                        ),
                    )
                else:
                    raise RegistryError("operation_invalid")
            response: dict[str, Any] = {
                "status": "accepted" if result.apply_pending else "ok",
                "changed": result.changed,
                "epoch": result.manifest["epoch"],
                "apply_pending": result.apply_pending,
            }
            if result.peer:
                response["peer"] = result.peer
                if result.peer.get("mesh_ip"):
                    response["mesh_ip"] = result.peer["mesh_ip"]
            if self.path == "/v1/mesh/enroll":
                response["bootstrap"] = {
                    "manifest": result.manifest,
                    "seeds": [
                        f"http://{peer['mesh_ip']}:{self.server.engine.config.port}"
                        for peer in result.manifest["peers"].values()
                    ][: self.server.engine.config.discovery_max_targets],
                }
            self._write_json(
                HTTPStatus.ACCEPTED if result.apply_pending else HTTPStatus.OK, response
            )
        except RegistryError as exc:
            self._write_json(exc.status, {"error": exc.code})
        except Exception:
            # Never reflect exception text; paths, process output, and trust
            # details must not leak to an unauthenticated caller.
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal_error"}
            )

    def log_message(self, _format: str, *_args: object) -> None:
        return


class RegistryHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64

    def __init__(
        self,
        address: tuple[str, int],
        engine: RegistryEngine,
        authenticator: OpenSSHRequestAuthenticator,
    ):
        self.engine = engine
        self.authenticator = authenticator
        self._request_slots = threading.BoundedSemaphore(engine.config.http_max_workers)
        super().__init__(address, RegistryHandler)

    def get_request(self) -> tuple[Any, Any]:
        request, client_address = super().get_request()
        request.settimeout(self.engine.config.http_request_timeout)
        return request, client_address

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._request_slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._request_slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


def _client_url(config: RegistryConfig, path: str) -> str:
    base = os.getenv("KOLIBRI_MESH_REGISTRY_URL", "").strip()
    if not base:
        base = f"http://{config.bind}:{config.port}"
    parsed = urlsplit(base)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.path not in {"", "/"}
    ):
        raise RegistryError("registry_url_invalid")
    return f"{base.rstrip('/')}{path}"


def _run_client(
    args: argparse.Namespace,
    config: RegistryConfig,
    authenticator: OpenSSHRequestAuthenticator,
) -> int:
    def require_applied(response: Mapping[str, Any]) -> None:
        if response.get("apply_pending"):
            raise RegistryError(
                "wireguard_apply_pending", HTTPStatus.SERVICE_UNAVAILABLE
            )

    def current_manifest() -> dict[str, Any]:
        return signed_request(
            authenticator,
            "GET",
            _client_url(config, "/v1/mesh/peers"),
        )

    if args.client_action == "allocate":
        response = signed_request(
            authenticator,
            "POST",
            _client_url(config, "/v1/mesh/allocate"),
            payload={},
        )
        print(validate_mesh_ip(response.get("mesh_ip")))
        return 0
    if args.client_action == "enroll":
        state = normalize_manifest(current_manifest(), cluster_id=config.cluster_id)
        node_id = canonical_node_id(args.node_id)
        current = state["records"].get(node_id)
        if not current or current.get("tombstone"):
            raise RegistryError("owner_enrollment_required", HTTPStatus.FORBIDDEN)
        peer = {
            "node_id": node_id,
            "public_key": args.public_key,
            "mesh_ip": args.mesh_ip,
            "endpoint": args.endpoint,
        }
        payload = {
            "operation": "upsert",
            "peer": peer,
            "generation": int(current["generation"]),
            "revision": int(state["vector"].get(node_id, 0)) + 1,
        }
        response = signed_request(
            authenticator,
            "POST",
            _client_url(config, "/v1/mesh/peers"),
            payload=payload,
        )
        require_applied(response)
        return 0
    if args.client_action == "enroll-auto":
        raise RegistryError("owner_bootstrap_required", HTTPStatus.FORBIDDEN)
    if args.client_action == "bootstrap":
        state = normalize_manifest(current_manifest(), cluster_id=config.cluster_id)
        node_id = canonical_node_id(args.node_id)
        current = state["records"].get(node_id)
        identity_keys: dict[str, str] = {}
        for specification in args.identity_key:
            if "=" not in specification:
                raise RegistryError("identity_key_argument_invalid")
            key_id_text, public_path_text = specification.split("=", 1)
            key_id = canonical_node_id(key_id_text)
            public_path = Path(public_path_text)
            _assert_not_symlink(public_path, "identity_public_key_symlink_forbidden")
            try:
                identity_keys[key_id] = validate_ssh_public_key(
                    public_path.read_text(encoding="utf-8")
                )
            except OSError as exc:
                raise RegistryError("identity_public_key_unavailable") from exc
        peer = {
            "node_id": node_id,
            "public_key": validate_public_key(args.public_key),
            "endpoint": validate_endpoint(args.endpoint),
            "identity_keys": normalize_identity_keys(identity_keys),
        }
        if args.mesh_ip != "auto":
            peer["mesh_ip"] = validate_mesh_ip(args.mesh_ip)
        payload = {
            "operation": "rotate" if current else "enroll",
            "peer": peer,
            "generation": int((current or {}).get("generation", 0)) + 1,
            "revision": int(state["vector"].get(node_id, 0)) + 1,
            "enrollment_nonce": secrets.token_urlsafe(32),
            "expires_at": int(time.time()) + args.ttl,
        }
        response = signed_request(
            authenticator,
            "POST",
            _client_url(config, "/v1/mesh/enroll"),
            payload=payload,
        )
        require_applied(response)
        # Bootstrap output contains public membership, seeds and signatures
        # only; identity private keys never enter the request or response.
        print(
            json.dumps(response.get("bootstrap"), sort_keys=True, separators=(",", ":"))
        )
        return 0
    if args.client_action == "remove":
        state = normalize_manifest(current_manifest(), cluster_id=config.cluster_id)
        node_id = canonical_node_id(args.node_id)
        current = state["records"].get(node_id)
        if not current:
            raise RegistryError("peer_not_found", HTTPStatus.NOT_FOUND)
        payload = {
            "operation": "remove",
            "node_id": node_id,
            "expected_generation": int(current["generation"]),
            "revision": int(state["vector"].get(authenticator.node_id, 0)) + 1,
        }
        response = signed_request(
            authenticator,
            "POST",
            _client_url(config, "/v1/mesh/peers"),
            payload=payload,
        )
        require_applied(response)
        return 0
    raise RegistryError("client_action_invalid")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("serve")
    subcommands.add_parser("apply")
    client = subcommands.add_parser("client")
    actions = client.add_subparsers(dest="client_action", required=True)
    actions.add_parser("allocate")
    enroll = actions.add_parser("enroll")
    enroll.add_argument("node_id")
    enroll.add_argument("public_key")
    enroll.add_argument("mesh_ip")
    enroll.add_argument("endpoint")
    enroll_auto = actions.add_parser("enroll-auto")
    enroll_auto.add_argument("node_id")
    enroll_auto.add_argument("public_key")
    enroll_auto.add_argument("endpoint")
    bootstrap = actions.add_parser("bootstrap")
    bootstrap.add_argument("node_id")
    bootstrap.add_argument("public_key")
    bootstrap.add_argument("mesh_ip")
    bootstrap.add_argument("endpoint")
    bootstrap.add_argument(
        "identity_key",
        nargs="+",
        help="one or more KEY_ID=/path/to/public_key entries for rotation overlap",
    )
    bootstrap.add_argument("--ttl", type=int, choices=range(60, 901), default=300)
    remove = actions.add_parser("remove")
    remove.add_argument("node_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "serve"
    try:
        config = RegistryConfig.from_env()
        if command == "apply":
            apply_fragments(config)
            return 0
        signer = OpenSSHSigner(
            config.identity_file,
            node_id=config.node_id,
            key_id=config.identity_key_id,
            ssh_keygen=config.ssh_keygen,
        )
        trust_store = OpenSSHTrustStore(
            config.owner_trust_dir,
            config.registrar_trust_dir,
        )
        authenticator = OpenSSHRequestAuthenticator(
            signer,
            trust_store,
            cluster_id=config.cluster_id,
        )
        if command == "client":
            return _run_client(args, config, authenticator)
        record_authorizer = RecordAuthorizer(authenticator)
        engine = RegistryEngine(config, record_authorizer=record_authorizer)
        trust_store.set_dynamic_resolver(engine.identity_public_key)
        engine.recover()
        discovery = DiscoveryLoop(config, engine, authenticator)
        thread = threading.Thread(
            target=discovery.run_forever, name="mesh-discovery", daemon=True
        )
        thread.start()
        RegistryHTTPServer(
            (config.bind, config.port), engine, authenticator
        ).serve_forever()
    except RegistryError as exc:
        print(f"kolibri-mesh-registry: {exc.code}", file=os.sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
