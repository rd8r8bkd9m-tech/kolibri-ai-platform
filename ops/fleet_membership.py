#!/usr/bin/env python3
"""Canonical physical fleet membership derived from the replicated mesh.

The mesh registry's materialised ``peers`` collection is the only authority
for active physical server membership.  Redis Agent Host cards are runtime
observations and an audit ledger; they cannot add a server to the scheduler.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

try:
    from control_plane_endpoint import DEFAULT_MESH_MANIFEST
except ImportError:  # pragma: no cover - package import
    from ops.control_plane_endpoint import DEFAULT_MESH_MANIFEST


CGNAT_NETWORK = ipaddress.IPv4Network("100.64.0.0/10")
NODE_ID_RE = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?\Z")
MAX_MANIFEST_BYTES = 2 * 1024 * 1024


class MembershipError(RuntimeError):
    """Stable, non-secret failure used to fail scheduling closed."""


def canonical_node_id(value: object) -> str:
    node_id = str(value or "").strip().lower().replace("_", "-")
    if not NODE_ID_RE.fullmatch(node_id):
        raise MembershipError("canonical_mesh_node_id_invalid")
    return node_id


def validate_mesh_ip(value: object) -> str:
    try:
        address = ipaddress.ip_address(str(value or "").strip())
    except ValueError as exc:
        raise MembershipError("canonical_mesh_ip_invalid") from exc
    if (
        address.version != 4
        or address.is_unspecified
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or not (address.is_private or address in CGNAT_NETWORK)
    ):
        raise MembershipError("canonical_mesh_ip_invalid")
    return str(address)


@dataclass(frozen=True)
class CanonicalMember:
    node_id: str
    mesh_ip: str


@dataclass(frozen=True)
class MembershipSnapshot:
    members: tuple[CanonicalMember, ...]
    digest: str
    epoch: int | None
    schema_version: int | None
    cluster_id: str | None
    path: str

    @property
    def by_id(self) -> dict[str, CanonicalMember]:
        return {member.node_id: member for member in self.members}

    def metadata(self) -> dict[str, Any]:
        return {
            "authority": "replicated_mesh_manifest",
            "path": self.path,
            "digest": self.digest,
            "epoch": self.epoch,
            "schema_version": self.schema_version,
            "cluster_id": self.cluster_id,
            "canonical_total": len(self.members),
        }


class MeshMembershipSource:
    """Read and validate one atomic mesh membership snapshot."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(
            path
            or os.environ.get("KOLIBRI_MESH_MEMBERSHIP_MANIFEST")
            or DEFAULT_MESH_MANIFEST
        )

    def _read_payload(self) -> Mapping[str, Any]:
        try:
            info = self.path.lstat()
        except FileNotFoundError as exc:
            raise MembershipError("canonical_mesh_manifest_missing") from exc
        except OSError as exc:
            raise MembershipError("canonical_mesh_manifest_unreadable") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise MembershipError("canonical_mesh_manifest_not_regular")
        if info.st_size <= 0 or info.st_size > MAX_MANIFEST_BYTES:
            raise MembershipError("canonical_mesh_manifest_size_invalid")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise MembershipError("canonical_mesh_manifest_invalid") from exc
        if not isinstance(payload, Mapping):
            raise MembershipError("canonical_mesh_manifest_invalid")
        return payload

    def load(self) -> MembershipSnapshot:
        payload = self._read_payload()
        peers = payload.get("peers")
        if isinstance(peers, Mapping):
            raw_records = list(peers.items())
        elif isinstance(peers, list):
            raw_records = [(None, item) for item in peers]
        else:
            raise MembershipError("canonical_mesh_peers_invalid")

        by_id: dict[str, CanonicalMember] = {}
        by_ip: dict[str, str] = {}
        for raw_key, raw_record in raw_records:
            if not isinstance(raw_record, Mapping):
                raise MembershipError("canonical_mesh_peer_invalid")
            if raw_record.get("tombstone") is True:
                # ``peers`` should already be materialised live membership;
                # treating an embedded tombstone as active would be unsafe.
                raise MembershipError("canonical_mesh_peer_tombstone_invalid")
            node_id = canonical_node_id(raw_record.get("node_id"))
            mesh_value = raw_record.get("mesh_ip")
            if not mesh_value and raw_key is not None:
                mesh_value = raw_key
            mesh_ip = validate_mesh_ip(mesh_value)
            if node_id in by_id:
                raise MembershipError("canonical_mesh_node_id_ambiguous")
            if mesh_ip in by_ip:
                raise MembershipError("canonical_mesh_ip_ambiguous")
            by_id[node_id] = CanonicalMember(node_id=node_id, mesh_ip=mesh_ip)
            by_ip[mesh_ip] = node_id

        if "home" not in by_id:
            raise MembershipError("canonical_home_not_in_mesh_membership")
        members = tuple(sorted(by_id.values(), key=lambda item: (item.node_id != "home", item.node_id)))
        material = {
            "members": [
                {"node_id": member.node_id, "mesh_ip": member.mesh_ip}
                for member in members
            ],
            "epoch": payload.get("epoch"),
            "schema_version": payload.get("schema_version"),
            "cluster_id": payload.get("cluster_id"),
        }
        digest = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return MembershipSnapshot(
            members=members,
            digest=digest,
            epoch=payload.get("epoch") if isinstance(payload.get("epoch"), int) else None,
            schema_version=(
                payload.get("schema_version")
                if isinstance(payload.get("schema_version"), int)
                else None
            ),
            cluster_id=(
                str(payload.get("cluster_id"))
                if payload.get("cluster_id") is not None
                else None
            ),
            path=str(self.path),
        )
