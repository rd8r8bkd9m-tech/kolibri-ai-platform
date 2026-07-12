#!/usr/bin/env python3
"""Plan or apply one signed immutable Home Control Plane release.

Planning is the default and performs no mutation.  ``--apply`` delegates the
single Home wave to the existing API-only release controller; signature,
owner approval, fenced completion and signed rollback remain mandatory.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from ops.control_plane_endpoint import (
        ControlPlaneEndpointError,
        resolve_home_control_plane_url,
    )
except ImportError:  # standalone operator execution beside resolver
    from control_plane_endpoint import (  # type: ignore[no-redef]
        ControlPlaneEndpointError,
        resolve_home_control_plane_url,
    )

try:
    from ops.release_controller import (
        ControlPlaneClient,
        ReleaseError,
        ReleaseManifest,
        execute_progressive_release,
        load_release_manifest,
        plan_home_canary,
        release_plan_payload,
        verify_ssh_signature,
    )
except ImportError:  # standalone operator execution beside release_controller
    from release_controller import (  # type: ignore[no-redef]
        ControlPlaneClient,
        ReleaseError,
        ReleaseManifest,
        execute_progressive_release,
        load_release_manifest,
        plan_home_canary,
        release_plan_payload,
        verify_ssh_signature,
    )


PROFILE_SCHEMA = "kolibri.home-control-plane-release.v1"
REQUIRED_RUNTIME_PATHS = frozenset({
    "RELEASE_ID",
    "ops/agent_host.py",
    "ops/control_plane_endpoint.py",
    "ops/factory_control.py",
    "ops/fleet_membership.py",
    "ops/immutable_release_preflight.py",
    "ops/marked_connect_proxy.py",
    "ops/mimo/kolibri-response-only.md",
    "ops/provider_egress_policy.py",
    "ops/provider_egress_preflight.py",
    "ops/provider_egress_tunnel.py",
    "ops/release_authority.py",
    "ops/release_helper.py",
    "ops/release_installer.py",
    "ops/runner_access.py",
    "ops/telegram_superfactory.py",
    "ops/systemd/kolibri-agent-host-provider-egress.conf",
    "ops/systemd/kolibri-provider-egress-proxy.service",
    "ops/systemd/kolibri-provider-egress-tunnel.service",
})


def validate_unified_profile(manifest: ReleaseManifest) -> dict[str, object]:
    paths = {item.path for item in manifest.files}
    missing = sorted(REQUIRED_RUNTIME_PATHS - paths)
    has_backend = any(path.startswith("backend/") for path in paths)
    has_frontend = any(path.startswith("frontend/dist/") for path in paths)
    if missing or not has_backend or not has_frontend:
        raise ReleaseError("signed Home release does not contain the unified backend/frontend/control-plane profile")
    return {
        "schema_version": PROFILE_SCHEMA,
        "profile": "unified-home-runtime",
        "required_runtime_paths": sorted(REQUIRED_RUNTIME_PATHS),
        "backend_present": has_backend,
        "frontend_dist_present": has_frontend,
    }


def _required_apply_value(parser: argparse.ArgumentParser, value: str | None, flag: str) -> str:
    if not value:
        parser.error(f"{flag} is required with --apply")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--expected-nodes", type=int)
    parser.add_argument("--control-url")
    parser.add_argument("--mesh-manifest")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--signature")
    parser.add_argument("--rollback-manifest")
    parser.add_argument("--rollback-signature")
    parser.add_argument("--allowed-signers")
    parser.add_argument("--signer-identity")
    parser.add_argument("--rollback-signer-identity")
    parser.add_argument("--approval-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        manifest = load_release_manifest(args.manifest)
        profile = validate_unified_profile(manifest)
        if args.mesh_manifest:
            control_url = resolve_home_control_plane_url(
                args.control_url,
                manifest_path=args.mesh_manifest,
            )
            client = ControlPlaneClient(control_url, timeout=args.timeout)
        else:
            client = ControlPlaneClient.from_environment(
                timeout=args.timeout,
                control_url=args.control_url,
            )
        waves = plan_home_canary(client.fleet(), expected_nodes=args.expected_nodes)
        if not args.apply:
            result = release_plan_payload(manifest, waves)
            result.update({
                "status": "planned",
                "mutation": "none",
                "authority": "home-only",
                "profile": profile,
                "requires": [
                    "detached_sshsig",
                    "owner_approval_attestation",
                    "signed_rollback_bundle",
                ],
            })
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0

        signature = _required_apply_value(parser, args.signature, "--signature")
        rollback_manifest_path = _required_apply_value(
            parser, args.rollback_manifest, "--rollback-manifest"
        )
        rollback_signature = _required_apply_value(
            parser, args.rollback_signature, "--rollback-signature"
        )
        allowed_signers = _required_apply_value(
            parser, args.allowed_signers, "--allowed-signers"
        )
        signer_identity = _required_apply_value(
            parser, args.signer_identity, "--signer-identity"
        )
        approval_id = _required_apply_value(parser, args.approval_id, "--approval-id")

        verified = verify_ssh_signature(
            manifest,
            Path(signature),
            Path(allowed_signers),
            signer_identity,
        )
        rollback_manifest = load_release_manifest(rollback_manifest_path)
        validate_unified_profile(rollback_manifest)
        rollback_verified = verify_ssh_signature(
            rollback_manifest,
            Path(rollback_signature),
            Path(allowed_signers),
            args.rollback_signer_identity or signer_identity,
        )
        result = execute_progressive_release(
            client,
            verified,
            rollback_verified,
            waves,
            approval_id,
        )
        result["authority"] = "home-only"
        result["profile"] = profile
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("status") == "completed" else 1
    except (ReleaseError, ControlPlaneEndpointError) as exc:
        print(json.dumps({
            "status": "blocked",
            "reason": "home_control_plane_release_error",
            "detail": str(exc),
        }, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
