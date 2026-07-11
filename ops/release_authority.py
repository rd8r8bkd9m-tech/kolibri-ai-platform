#!/usr/bin/env python3
"""Canonical owner authority contract shared by Home and release workers."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any


OWNER_APPROVAL_SCHEMA = "kolibri.owner-approval.v2"
OWNER_APPROVAL_ATTESTATION_SCHEMA = "kolibri.owner-approval-attestation.v1"
OWNER_APPROVAL_NAMESPACE = "kolibri-owner-approval"
RELEASE_SIGNATURE_NAMESPACE = "kolibri-release"
RELEASE_CAPABILITY = "release_apply_v1"
RELEASE_TASK_KINDS = frozenset({"release_bundle_apply", "release_bundle_rollback"})
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}")
SAFE_WAVE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
SHA256 = re.compile(r"sha256:[0-9a-f]{64}")


class ReleaseAuthorityError(ValueError):
    pass


def safe_id(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not SAFE_ID.fullmatch(text):
        raise ReleaseAuthorityError(f"invalid_{field_name}")
    return text


def manifest_digest(value: Any, field_name: str = "manifest_digest") -> str:
    text = str(value or "").strip().lower()
    if not SHA256.fullmatch(text):
        raise ReleaseAuthorityError(f"invalid_{field_name}")
    return text


def parse_iso_timestamp(value: Any) -> float | None:
    try:
        text = str(value or "").strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError):
        return None


def canonical_rollout_plan(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 64:
        raise ReleaseAuthorityError("owner_approval_rollout_plan_invalid")
    result: list[dict[str, Any]] = []
    wave_names: set[str] = set()
    node_ids: set[str] = set()
    for raw_wave in value:
        if not isinstance(raw_wave, dict) or set(raw_wave) != {"name", "nodes"}:
            raise ReleaseAuthorityError("owner_approval_rollout_plan_invalid")
        name = str(raw_wave.get("name") or "").strip()
        raw_nodes = raw_wave.get("nodes")
        if not SAFE_WAVE.fullmatch(name) or name in wave_names:
            raise ReleaseAuthorityError("owner_approval_rollout_plan_invalid")
        if not isinstance(raw_nodes, list) or not 1 <= len(raw_nodes) <= 512:
            raise ReleaseAuthorityError("owner_approval_rollout_plan_invalid")
        nodes = [safe_id(node, "rollout_node_id") for node in raw_nodes]
        if len(nodes) != len(set(nodes)) or node_ids.intersection(nodes):
            raise ReleaseAuthorityError("owner_approval_rollout_plan_invalid")
        wave_names.add(name)
        node_ids.update(nodes)
        result.append({"name": name, "nodes": sorted(nodes)})
    return result


def _canonical_rollback(value: Any, *, required: bool) -> dict[str, str] | None:
    if not required:
        if value is not None and value is not False:
            raise ReleaseAuthorityError("owner_approval_rollback_contract_invalid")
        return None
    if not isinstance(value, dict) or set(value) != {
        "release_id",
        "manifest_digest",
        "signature_namespace",
        "signer_identity",
    }:
        raise ReleaseAuthorityError("owner_approval_rollback_contract_invalid")
    namespace = str(value.get("signature_namespace") or "")
    if namespace != RELEASE_SIGNATURE_NAMESPACE:
        raise ReleaseAuthorityError("owner_approval_rollback_contract_invalid")
    return {
        "release_id": safe_id(value.get("release_id"), "rollback_release_id"),
        "manifest_digest": manifest_digest(value.get("manifest_digest"), "rollback_manifest_digest"),
        "signature_namespace": namespace,
        "signer_identity": safe_id(value.get("signer_identity"), "rollback_signer_identity"),
    }


def canonical_owner_approval_payload(
    value: Any,
    *,
    now: float | None = None,
    max_ttl_seconds: int | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReleaseAuthorityError("owner_approval_payload_invalid")
    decision = str(value.get("decision") or value.get("status") or "").strip().lower()
    if decision not in {"approved", "denied"}:
        raise ReleaseAuthorityError("invalid_owner_decision")
    expires_at = str(value.get("expires_at") or "").strip()
    expires_ts = parse_iso_timestamp(expires_at)
    current = datetime.now(timezone.utc).timestamp() if now is None else now
    if expires_ts is None or expires_ts <= current:
        raise ReleaseAuthorityError("owner_approval_expired")
    if max_ttl_seconds is not None and expires_ts - current > max_ttl_seconds:
        raise ReleaseAuthorityError("owner_approval_ttl_exceeds_policy")
    allow_rollback = value.get("allow_rollback") is True
    namespace = str(value.get("release_signature_namespace") or "")
    if namespace != RELEASE_SIGNATURE_NAMESPACE:
        raise ReleaseAuthorityError("owner_approval_release_signature_invalid")
    return {
        "schema_version": OWNER_APPROVAL_SCHEMA,
        "approval_id": safe_id(value.get("approval_id"), "approval_id"),
        "release_id": safe_id(value.get("release_id"), "release_id"),
        "manifest_digest": manifest_digest(value.get("manifest_digest")),
        "release_signature_namespace": namespace,
        "release_signer_identity": safe_id(
            value.get("release_signer_identity"), "release_signer_identity"
        ),
        "decision": decision,
        "allow_rollback": allow_rollback,
        "rollback": _canonical_rollback(value.get("rollback"), required=allow_rollback),
        "rollout_plan": canonical_rollout_plan(value.get("rollout_plan")),
        "expires_at": expires_at,
        "nonce": safe_id(value.get("nonce"), "nonce"),
        "signer_identity": safe_id(value.get("signer_identity"), "signer_identity"),
    }


def canonical_owner_approval_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_owner_approval_attestation(
    value: Any,
    *,
    now: float | None = None,
    max_ttl_seconds: int | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"schema_version", "payload", "signature"}:
        raise ReleaseAuthorityError("owner_approval_attestation_invalid")
    if value.get("schema_version") != OWNER_APPROVAL_ATTESTATION_SCHEMA:
        raise ReleaseAuthorityError("owner_approval_attestation_invalid")
    signature = value.get("signature")
    if (
        not isinstance(signature, str)
        or not signature.startswith("-----BEGIN SSH SIGNATURE-----")
        or len(signature.encode("utf-8")) > 32 * 1024
    ):
        raise ReleaseAuthorityError("owner_approval_signature_invalid")
    return {
        "schema_version": OWNER_APPROVAL_ATTESTATION_SCHEMA,
        "payload": canonical_owner_approval_payload(
            value.get("payload"), now=now, max_ttl_seconds=max_ttl_seconds
        ),
        "signature": signature,
    }


def approval_attestation_digest(attestation: dict[str, Any]) -> str:
    signature = str(attestation.get("signature") or "").encode("utf-8")
    payload = canonical_owner_approval_bytes(attestation["payload"])
    return f"sha256:{hashlib.sha256(payload + b'\0' + signature).hexdigest()}"


def validate_approval_for_task(payload: dict[str, Any], envelope: dict[str, Any]) -> None:
    if payload.get("decision") != "approved":
        raise ReleaseAuthorityError("release_task_owner_approval_denied")
    kind = str(envelope.get("kind") or "")
    if kind not in RELEASE_TASK_KINDS:
        raise ReleaseAuthorityError("release_task_kind_invalid")
    if envelope.get("required_capability") != RELEASE_CAPABILITY:
        raise ReleaseAuthorityError("release_task_capability_invalid")
    if str(envelope.get("approval_id") or "") != payload["approval_id"]:
        raise ReleaseAuthorityError("release_task_approval_mismatch")

    target_node = safe_id(envelope.get("target_node"), "target_node")
    rollout_wave = str(envelope.get("rollout_wave") or "").strip()
    matching_waves = [wave for wave in payload["rollout_plan"] if target_node in wave["nodes"]]
    if len(matching_waves) != 1 or matching_waves[0]["name"] != rollout_wave:
        raise ReleaseAuthorityError("release_task_rollout_binding_invalid")

    signature = envelope.get("signature")
    if not isinstance(signature, dict):
        raise ReleaseAuthorityError("release_task_signature_contract_invalid")
    namespace = str(signature.get("namespace") or "")
    signer_identity = str(signature.get("signer_identity") or "")
    if signature.get("format") != "sshsig" or namespace != RELEASE_SIGNATURE_NAMESPACE:
        raise ReleaseAuthorityError("release_task_signature_contract_invalid")

    if kind == "release_bundle_apply":
        if (
            str(envelope.get("release_id") or "") != payload["release_id"]
            or str(envelope.get("manifest_digest") or "").lower() != payload["manifest_digest"]
            or namespace != payload["release_signature_namespace"]
            or signer_identity != payload["release_signer_identity"]
        ):
            raise ReleaseAuthorityError("release_task_approval_scope_mismatch")
        return

    rollback = payload.get("rollback")
    if payload.get("allow_rollback") is not True or not isinstance(rollback, dict):
        raise ReleaseAuthorityError("release_task_rollback_not_approved")
    if (
        str(envelope.get("failed_release_id") or "") != payload["release_id"]
        or str(envelope.get("rollback_to_release_id") or "") != rollback["release_id"]
        or str(envelope.get("manifest_digest") or "").lower() != rollback["manifest_digest"]
        or namespace != rollback["signature_namespace"]
        or signer_identity != rollback["signer_identity"]
    ):
        raise ReleaseAuthorityError("release_task_approval_scope_mismatch")
