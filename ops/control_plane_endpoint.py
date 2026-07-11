#!/usr/bin/env python3
"""Resolve the single canonical Home Control Plane endpoint.

The endpoint is discovered from the replicated mesh membership manifest when
it is not supplied explicitly.  Multiple Control Plane URLs are rejected: a
provider fallback must never become a Control Plane authority fallback.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import socket
import subprocess
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit


CANONICAL_CONTROL_PLANE_NODE_ID = "home"
CONTROL_PLANE_PORT = 9101
DEFAULT_MESH_MANIFEST = Path("/var/lib/kolibri-mesh/peers.json")
class ControlPlaneEndpointError(RuntimeError):
    """Raised when the canonical Home endpoint cannot be resolved safely."""


def _normalized_urls(*values: str | None) -> list[str]:
    urls: list[str] = []
    for value in values:
        for candidate in str(value or "").split(","):
            normalized = candidate.strip().rstrip("/")
            if normalized and normalized not in urls:
                urls.append(normalized)
    return urls


def _validate_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ControlPlaneEndpointError("canonical_home_control_plane_url_invalid")
    try:
        parsed.port
    except ValueError as exc:
        raise ControlPlaneEndpointError("canonical_home_control_plane_url_invalid") from exc
    if parsed.username or parsed.password:
        raise ControlPlaneEndpointError("canonical_home_control_plane_url_must_not_embed_credentials")
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ControlPlaneEndpointError("canonical_home_control_plane_url_invalid")
    hostname = parsed.hostname.rstrip(".").lower()
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", hostname) or ".." in hostname:
            raise ControlPlaneEndpointError("canonical_home_control_plane_url_invalid")
    return url.rstrip("/")


def _validate_dynamic_home_authority(
    url: str,
    manifest_path: Path,
    *,
    local_addresses: Iterable[str] | None = None,
) -> str:
    validated = _validate_url(url)
    hostname = (urlsplit(validated).hostname or "").rstrip(".").lower()
    home_mesh_ip = _read_home_mesh_ip(manifest_path)
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            resolved = {
                str(ipaddress.ip_address(item[4][0]))
                for item in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
            }
        except (OSError, ValueError) as exc:
            raise ControlPlaneEndpointError("control_plane_authority_not_home") from exc
        if home_mesh_ip not in resolved:
            raise ControlPlaneEndpointError("control_plane_authority_not_home")
        return validated
    if address.is_loopback:
        # Loopback is safe only when this process is running on the host that
        # owns Home's manifest address.  ``local_addresses`` is an explicit
        # dependency-injection seam for deterministic tests; normal runtime
        # callers omit it and the interface address is read from the kernel.
        assert_local_home_control_plane(
            manifest_path=manifest_path,
            local_addresses=local_addresses,
        )
        return validated
    if str(address) != home_mesh_ip:
        raise ControlPlaneEndpointError("control_plane_authority_not_home")
    return validated


def _read_home_mesh_ip(manifest_path: Path) -> str:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ControlPlaneEndpointError("canonical_home_control_plane_manifest_missing") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlPlaneEndpointError("canonical_home_control_plane_manifest_invalid") from exc

    if not isinstance(payload, dict):
        raise ControlPlaneEndpointError("canonical_home_control_plane_manifest_invalid")
    peers = payload.get("peers")
    if isinstance(peers, dict):
        records = peers.values()
    elif isinstance(peers, list):
        records = peers
    else:
        raise ControlPlaneEndpointError("canonical_home_control_plane_manifest_invalid")
    home_mesh_ips: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        node_id = str(record.get("node_id") or "").strip().lower().replace("_", "-")
        if node_id != CANONICAL_CONTROL_PLANE_NODE_ID:
            continue
        mesh_ip = str(record.get("mesh_ip") or "").strip()
        try:
            parsed_ip = ipaddress.ip_address(mesh_ip)
        except ValueError as exc:
            raise ControlPlaneEndpointError("canonical_home_control_plane_mesh_ip_invalid") from exc
        if (
            parsed_ip.version != 4
            or not parsed_ip.is_private
            or parsed_ip.is_loopback
            or parsed_ip.is_link_local
            or parsed_ip.is_multicast
            or parsed_ip.is_unspecified
        ):
            raise ControlPlaneEndpointError("canonical_home_control_plane_mesh_ip_not_private")
        home_mesh_ips.add(str(parsed_ip))
    if not home_mesh_ips:
        raise ControlPlaneEndpointError("canonical_home_control_plane_not_registered")
    if len(home_mesh_ips) != 1:
        raise ControlPlaneEndpointError("canonical_home_control_plane_membership_ambiguous")
    return next(iter(home_mesh_ips))


def resolve_home_control_plane_url(
    control_url: str | None = None,
    control_urls: str | None = None,
    *,
    manifest_path: str | Path | None = None,
    local_addresses: Iterable[str] | None = None,
) -> str:
    """Return exactly one Home Control Plane URL or fail closed."""

    urls = _normalized_urls(control_url, control_urls)
    if not urls:
        urls = _normalized_urls(
            os.environ.get("KOLIBRI_FACTORY_CONTROL_URL"),
            os.environ.get("KOLIBRI_FACTORY_CONTROL_URLS"),
        )
    if len(urls) > 1:
        raise ControlPlaneEndpointError("multiple_control_plane_authorities_forbidden")
    state_path = Path(
        manifest_path
        or os.environ.get("KOLIBRI_MESH_MEMBERSHIP_MANIFEST")
        or DEFAULT_MESH_MANIFEST
    )
    if urls:
        return _validate_dynamic_home_authority(
            urls[0],
            state_path,
            local_addresses=local_addresses,
        )
    mesh_ip = _read_home_mesh_ip(state_path)
    return f"http://{mesh_ip}:{CONTROL_PLANE_PORT}"


def assert_local_home_control_plane(
    *,
    manifest_path: str | Path | None = None,
    interface: str | None = None,
    local_addresses: Iterable[str] | None = None,
) -> str:
    """Prove that this host owns Home's mesh IP before starting the server."""

    state_path = Path(
        manifest_path
        or os.environ.get("KOLIBRI_MESH_MEMBERSHIP_MANIFEST")
        or DEFAULT_MESH_MANIFEST
    )
    home_mesh_ip = _read_home_mesh_ip(state_path)
    if local_addresses is None:
        mesh_interface = interface or os.environ.get("KOLIBRI_MESH_INTERFACE", "wg-kolibri")
        try:
            completed = subprocess.run(
                ["ip", "-4", "-o", "addr", "show", mesh_interface],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ControlPlaneEndpointError("local_home_mesh_identity_unavailable") from exc
        if completed.returncode != 0:
            raise ControlPlaneEndpointError("local_home_mesh_identity_unavailable")
        local_addresses = [
            field.split("/", 1)[0]
            for line in completed.stdout.splitlines()
            for field in line.split()
            if "/" in field
        ]
    normalized_local_addresses: set[str] = set()
    for value in local_addresses:
        try:
            normalized_local_addresses.add(str(ipaddress.ip_address(str(value).split("/", 1)[0])))
        except ValueError:
            continue
    if home_mesh_ip not in normalized_local_addresses:
        raise ControlPlaneEndpointError("control_plane_must_run_on_home")
    return home_mesh_ip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--print-url", action="store_true")
    action.add_argument("--assert-local-home", action="store_true")
    parser.add_argument("--control-url")
    parser.add_argument("--control-urls")
    parser.add_argument("--manifest")
    parser.add_argument("--interface")
    args = parser.parse_args(argv)
    try:
        if args.assert_local_home:
            assert_local_home_control_plane(manifest_path=args.manifest, interface=args.interface)
        else:
            print(resolve_home_control_plane_url(args.control_url, args.control_urls, manifest_path=args.manifest))
    except ControlPlaneEndpointError as exc:
        parser.exit(2, f"home_control_plane_unresolved: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
