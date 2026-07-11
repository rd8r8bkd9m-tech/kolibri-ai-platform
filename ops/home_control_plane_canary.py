#!/usr/bin/env python3
"""Fail-closed side-by-side and live gates for Home Factory Control Plane."""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import stat
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from ops.control_plane_endpoint import assert_local_home_control_plane
    from ops.fleet_membership import MeshMembershipSource
except ImportError:  # installed beside these modules
    from control_plane_endpoint import assert_local_home_control_plane
    from fleet_membership import MeshMembershipSource


SCHEMA_VERSION = "kolibri.home-control-plane-canary.v1"
FLEET_PROOF_SCHEMA = "kolibri.fleet-capability-proof.v1"
DEFAULT_MANIFEST = Path("/var/lib/kolibri-mesh/peers.json")
DEFAULT_LIVE_URL = "http://127.0.0.1:9101"
DEFAULT_RELEASE_ROOT = Path("/opt/kolibri-ai/releases")
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
LEGACY_ROLLBACK_EXIT_CODE = 10
LEGACY_BASELINE_EXIT_CODE = 11
REQUIRED_RUNTIME = (
    "ops/control_plane_endpoint.py",
    "ops/factory_control.py",
    "ops/fleet_membership.py",
    "ops/release_authority.py",
    "ops/telegram_superfactory.py",
)


class CanaryError(RuntimeError):
    """Sanitized gate failure suitable for installer evidence."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _trusted_runtime_file(path: Path) -> bool:
    try:
        value = path.lstat()
    except OSError:
        return False
    return bool(
        stat.S_ISREG(value.st_mode)
        and not stat.S_ISLNK(value.st_mode)
        and value.st_nlink == 1
        and 0 < value.st_size <= 16 * 1024 * 1024
        and not value.st_mode & 0o022
        and (os.geteuid() != 0 or value.st_uid == 0)
    )


def validate_release_dir(release_dir: Path, release_root: Path) -> Path:
    try:
        resolved_root = release_root.resolve(strict=True)
        resolved = release_dir.resolve(strict=True)
        value = resolved.lstat()
    except OSError as exc:
        raise CanaryError("candidate_release_unavailable") from exc
    if (
        resolved.parent != resolved_root
        or not stat.S_ISDIR(value.st_mode)
        or value.st_mode & 0o022
        or (os.geteuid() == 0 and value.st_uid != 0)
    ):
        raise CanaryError("candidate_release_boundary_invalid")
    if not all(_trusted_runtime_file(resolved / relative) for relative in REQUIRED_RUNTIME):
        raise CanaryError("candidate_runtime_profile_incomplete")
    return resolved


def expected_live_release_id(
    release_dir: Path,
    release_root: Path = DEFAULT_RELEASE_ROOT,
) -> str:
    """Mirror launcher selection for post-switch and legacy rollback gates."""
    try:
        resolved_root = release_root.resolve(strict=True)
        resolved = release_dir.resolve(strict=True)
    except OSError as exc:
        raise CanaryError("expected_release_boundary_invalid") from exc
    if resolved.parent != resolved_root or not resolved.is_dir():
        raise CanaryError("expected_release_boundary_invalid")
    if all(_trusted_runtime_file(resolved / relative) for relative in REQUIRED_RUNTIME):
        return resolved.name
    return "legacy-bootstrap"


def _http_json(base_url: str, path: str, *, timeout: float = 3.0) -> dict[str, Any]:
    request = urllib.request.Request(f"{base_url.rstrip('/')}{path}", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise CanaryError("control_plane_contract_unavailable")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise CanaryError("control_plane_contract_not_found") from exc
        raise CanaryError("control_plane_contract_unavailable") from exc
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise CanaryError("control_plane_contract_unavailable") from exc
    if not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise CanaryError("control_plane_contract_invalid")
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CanaryError("control_plane_contract_invalid") from exc
    if not isinstance(payload, dict):
        raise CanaryError("control_plane_contract_invalid")
    return payload


def validate_contracts(
    base_url: str,
    manifest_path: Path,
    *,
    expected_release_id: str | None = None,
    expected_read_only: bool | None = None,
    allow_legacy_contract: bool = False,
) -> dict[str, Any]:
    snapshot = MeshMembershipSource(manifest_path).load()
    expected_ids = [member.node_id for member in snapshot.members]
    health = _http_json(base_url, "/v1/health")
    data = health.get("data") if isinstance(health.get("data"), dict) else {}
    if (
        health.get("status") != "completed"
        or health.get("node") != "home"
        or health.get("route_used") != "/v1/health"
        or data.get("redis") != "PONG"
        or not data.get("fabric_api_version")
    ):
        raise CanaryError("control_plane_health_contract_invalid")
    state_namespace = str(data.get("state_namespace") or "kolibri_factory")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", state_namespace):
        raise CanaryError("control_plane_state_namespace_invalid")
    legacy_shape = bool(
        data.get("active_release_id") in {None, ""}
        and data.get("canary_read_only") is None
        and data.get("state_namespace") in {None, ""}
    )
    legacy_contract_accepted = False
    legacy_compatibility_reasons: list[str] = []
    if expected_release_id is not None and data.get("active_release_id") != expected_release_id:
        if allow_legacy_contract and legacy_shape:
            legacy_contract_accepted = True
            legacy_compatibility_reasons.append("release_identity_absent")
        else:
            raise CanaryError("control_plane_release_identity_mismatch")
    if expected_read_only is not None and data.get("canary_read_only") is not expected_read_only:
        if allow_legacy_contract and legacy_shape:
            legacy_contract_accepted = True
            legacy_compatibility_reasons.append("canary_mode_absent")
        else:
            raise CanaryError("control_plane_canary_mode_mismatch")

    nodes = _http_json(base_url, "/v1/nodes?scope=active&limit=250")
    node_rows = nodes.get("nodes") if isinstance(nodes.get("nodes"), list) else []
    node_ids = [str(item.get("node_id") or "") for item in node_rows if isinstance(item, dict)]
    membership = nodes.get("membership") if isinstance(nodes.get("membership"), dict) else {}
    if (
        node_ids != expected_ids
        or membership.get("authority") != "replicated_mesh_manifest"
        or membership.get("digest") != snapshot.digest
        or membership.get("canonical_total") != len(expected_ids)
        or nodes.get("scope") != "active"
    ):
        raise CanaryError("control_plane_membership_contract_invalid")
    membership_projection = {
        key: membership.get(key)
        for key in ("registered_total", "missing_total", "schedulable_total")
    }
    if any(type(value) is not int or value < 0 for value in membership_projection.values()):
        raise CanaryError("control_plane_membership_contract_invalid")

    proof_status = "verified"
    try:
        proof = _http_json(base_url, "/v1/runtime/fleet-proof")
    except CanaryError as exc:
        if (
            exc.code == "control_plane_contract_not_found"
            and allow_legacy_contract
            and legacy_shape
        ):
            legacy_contract_accepted = True
            legacy_compatibility_reasons.append("fleet_proof_endpoint_absent")
            proof_status = "legacy_unavailable"
            proof_projection = {
                "fresh_total": None,
                "strict_verified_total": None,
                "missing_strict_verified_total": None,
            }
        else:
            raise
    else:
        proof_summary = proof.get("summary") if isinstance(proof.get("summary"), dict) else {}
        proof_membership = proof.get("membership") if isinstance(proof.get("membership"), dict) else {}
        proof_nodes = proof.get("nodes") if isinstance(proof.get("nodes"), list) else []
        proof_ids = [str(item.get("node_id") or "") for item in proof_nodes if isinstance(item, dict)]
        if (
            proof.get("schema_version") != FLEET_PROOF_SCHEMA
            or proof.get("source") != "control-plane/home"
            or proof_membership.get("digest") != snapshot.digest
            or proof_summary.get("canonical_total") != len(expected_ids)
            or proof_ids != expected_ids
        ):
            raise CanaryError("control_plane_fleet_proof_contract_invalid")
        proof_projection = {
            key: proof_summary.get(key)
            for key in (
                "fresh_total",
                "strict_verified_total",
                "missing_strict_verified_total",
            )
        }
        if any(type(value) is not int or value < 0 for value in proof_projection.values()):
            raise CanaryError("control_plane_fleet_proof_contract_invalid")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "passed",
        "authority": "home",
        "membership_digest": snapshot.digest,
        "canonical_total": len(expected_ids),
        "release_id": data.get("active_release_id"),
        "state_namespace": state_namespace,
        "membership_projection": membership_projection,
        "fleet_proof_projection": proof_projection,
        "fleet_proof_status": proof_status,
        "legacy_contract_accepted": legacy_contract_accepted,
        "legacy_compatibility_reasons": sorted(set(legacy_compatibility_reasons)),
    }


def _available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _stop_candidate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass


def run_candidate(
    release_dir: Path,
    manifest_path: Path,
    *,
    release_root: Path = DEFAULT_RELEASE_ROOT,
    live_url: str = DEFAULT_LIVE_URL,
    startup_timeout: float = 20.0,
    release_kind: str = "apply",
) -> dict[str, Any]:
    if release_kind not in {"apply", "rollback"}:
        raise CanaryError("candidate_release_kind_invalid")
    assert_local_home_control_plane(manifest_path=manifest_path)
    resolved = validate_release_dir(release_dir, release_root)
    # The baseline is part of the gate: the candidate must project the same
    # dynamic membership as the currently authoritative Home listener.
    baseline = validate_contracts(
        live_url,
        manifest_path,
        allow_legacy_contract=True,
    )
    port = _available_loopback_port()
    candidate_url = f"http://127.0.0.1:{port}"
    environment = dict(os.environ)
    environment.update({
        "FACTORY_BIND": "127.0.0.1",
        "FACTORY_PORT": str(port),
        "FACTORY_CANARY_READ_ONLY": "1",
        "FACTORY_NAMESPACE": str(baseline["state_namespace"]),
        "KOLIBRI_ACTIVE_RELEASE_ID": resolved.name,
        "KOLIBRI_MESH_MEMBERSHIP_MANIFEST": str(manifest_path),
        "KOLIBRI_REPO_ROOT": str(resolved),
        "KOLIBRI_OPS_DIR": str(resolved / "ops"),
        "PYTHONPATH": f"{resolved / 'ops'}:{resolved}",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    })
    try:
        process = subprocess.Popen(
            [
                "/usr/bin/python3",
                str(resolved / "ops/factory_control.py"),
                "--bind", "127.0.0.1",
                "--port", str(port),
            ],
            cwd=resolved,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise CanaryError("candidate_process_unavailable") from exc
    try:
        deadline = time.monotonic() + max(1.0, startup_timeout)
        last_error: CanaryError | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise CanaryError("candidate_process_exited")
            try:
                result = validate_contracts(
                    candidate_url,
                    manifest_path,
                    expected_release_id=resolved.name,
                    expected_read_only=True,
                    allow_legacy_contract=release_kind == "rollback",
                )
                if process.poll() is not None:
                    raise CanaryError("candidate_process_exited")
                if (
                    result.get("membership_projection")
                    != baseline.get("membership_projection")
                ):
                    raise CanaryError("candidate_runtime_projection_mismatch")
                if (
                    baseline.get("fleet_proof_status") == "verified"
                    and result.get("fleet_proof_projection")
                    != baseline.get("fleet_proof_projection")
                ):
                    raise CanaryError("candidate_runtime_projection_mismatch")
                if release_kind == "apply" and (
                    result.get("fleet_proof_status") != "verified"
                    or result.get("legacy_contract_accepted") is not False
                ):
                    raise CanaryError("candidate_strict_contract_required")
                return result
            except CanaryError as exc:
                last_error = exc
                time.sleep(0.2)
        raise CanaryError("candidate_startup_timeout") from last_error
    finally:
        _stop_candidate(process)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    candidate = commands.add_parser("candidate")
    candidate.add_argument("--release-dir", required=True)
    candidate.add_argument("--release-root", default=str(DEFAULT_RELEASE_ROOT))
    candidate.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    candidate.add_argument("--live-url", default=DEFAULT_LIVE_URL)
    candidate.add_argument("--release-kind", choices=("apply", "rollback"), default="apply")
    live = commands.add_parser("live")
    live.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    live.add_argument("--url", default=DEFAULT_LIVE_URL)
    live.add_argument("--expected-release-dir")
    live.add_argument("--release-kind", choices=("apply", "rollback"), default="apply")
    live.add_argument("--allow-legacy-baseline", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "candidate":
            result = run_candidate(
                Path(args.release_dir),
                Path(args.manifest),
                release_root=Path(args.release_root),
                live_url=args.live_url,
                release_kind=args.release_kind,
            )
        else:
            assert_local_home_control_plane(manifest_path=args.manifest)
            expected = (
                expected_live_release_id(Path(args.expected_release_dir))
                if args.expected_release_dir
                else None
            )
            result = validate_contracts(
                args.url,
                Path(args.manifest),
                expected_release_id=expected,
                expected_read_only=False if expected is not None else None,
                allow_legacy_contract=(
                    args.release_kind == "rollback"
                    or args.allow_legacy_baseline
                ),
            )
        print(json.dumps(result, sort_keys=True))
        if result.get("legacy_contract_accepted") is True:
            if args.command == "live" and args.allow_legacy_baseline:
                return LEGACY_BASELINE_EXIT_CODE
            return LEGACY_ROLLBACK_EXIT_CODE
        return 0
    except Exception as exc:
        reason = str(exc) if isinstance(exc, CanaryError) else "home_control_plane_canary_failed"
        print(json.dumps({"status": "failed", "reason": reason}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
