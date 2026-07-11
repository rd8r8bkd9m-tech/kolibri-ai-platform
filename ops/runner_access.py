#!/usr/bin/env python3
"""Validate non-secret runner access declarations for dynamic fleet nodes.

The manifest describes *how* a service user becomes ready.  It never contains
the credential itself and must never point at a copied Codex auth file.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "kolibri.runner-access.v1"
DEFAULT_MANIFEST = Path("/etc/kolibri/runner-access.json")
MAX_MANIFEST_BYTES = 64 * 1024
TRUSTED_CODEX_BROKERS = frozenset({
    "runner-broker://home/codex",
    "runner-broker://mac/codex",
})
FORBIDDEN_SECRET_KEYS = frozenset({
    "access_token",
    "api_key",
    "auth_json",
    "authorization",
    "bearer",
    "client_secret",
    "cookie",
    "credential",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token",
})
REFERENCE_RE = re.compile(r"(?:service-user|control-plane|systemd-credential)://[a-z0-9][a-z0-9._/-]{2,200}\Z")


class RunnerAccessError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require_keys(value: Mapping[str, Any], allowed: set[str], code: str) -> None:
    if set(value) - allowed:
        raise RunnerAccessError(code)


def _forbidden_key(key: object) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")
    return normalized in FORBIDDEN_SECRET_KEYS or normalized.endswith(
        ("_api_key", "_password", "_private_key", "_refresh_token", "_secret", "_token")
    )


def _reject_secret_material(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _forbidden_key(key):
                raise RunnerAccessError("runner_access_raw_secret_field_forbidden")
            _reject_secret_material(child, (*path, str(key)))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_material(child, (*path, str(index)))
        return
    if not isinstance(value, str):
        return
    lowered = value.strip().lower()
    if (
        "auth.json" in lowered
        or "/.codex/" in lowered
        or lowered.startswith(("sk-", "bearer ", "http://", "https://", "file://"))
    ):
        raise RunnerAccessError("runner_access_raw_auth_or_endpoint_forbidden")


def _bounded_int(value: Any, *, minimum: int, maximum: int, code: str) -> int:
    if isinstance(value, bool):
        raise RunnerAccessError(code)
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise RunnerAccessError(code) from exc
    if number < minimum or number > maximum:
        raise RunnerAccessError(code)
    return number


def validate_runner_access_manifest(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise RunnerAccessError("runner_access_manifest_invalid")
    _reject_secret_material(payload)
    _require_keys(
        payload,
        {"schema_version", "authority", "node_selector", "runners"},
        "runner_access_manifest_unknown_field",
    )
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise RunnerAccessError("runner_access_schema_unsupported")
    if payload.get("authority") != "home":
        raise RunnerAccessError("runner_access_authority_must_be_home")
    if payload.get("node_selector") != "dynamic-membership":
        raise RunnerAccessError("runner_access_node_selector_must_be_dynamic")
    runners = payload.get("runners")
    if not isinstance(runners, Mapping):
        raise RunnerAccessError("runner_access_runners_invalid")
    unknown = set(runners) - {"codex", "mimo"}
    if unknown:
        raise RunnerAccessError("runner_access_runner_unsupported")

    codex = runners.get("codex", {"mode": "disabled"})
    if not isinstance(codex, Mapping):
        raise RunnerAccessError("runner_access_codex_invalid")
    mode = str(codex.get("mode") or "disabled")
    normalized_codex: dict[str, Any] = {"mode": mode}
    if mode == "local_service_account":
        _require_keys(
            codex,
            {"mode", "authorization_flow", "identity_ref", "probe"},
            "runner_access_codex_unknown_field",
        )
        if codex.get("authorization_flow") != "browser_device":
            raise RunnerAccessError("runner_access_codex_device_flow_required")
        identity_ref = str(codex.get("identity_ref") or "")
        if not REFERENCE_RE.fullmatch(identity_ref) or not identity_ref.startswith("service-user://"):
            raise RunnerAccessError("runner_access_codex_identity_ref_invalid")
        probe = codex.get("probe")
        if not isinstance(probe, Mapping):
            raise RunnerAccessError("runner_access_codex_probe_invalid")
        _require_keys(
            probe,
            {"model", "sandbox", "timeout_seconds"},
            "runner_access_codex_probe_unknown_field",
        )
        if probe.get("model") != "gpt-5.5" or probe.get("sandbox") != "read-only":
            raise RunnerAccessError("runner_access_codex_probe_contract_invalid")
        normalized_codex.update({
            "authorization_flow": "browser_device",
            "identity_ref": identity_ref,
            "probe": {
                "model": "gpt-5.5",
                "sandbox": "read-only",
                "timeout_seconds": _bounded_int(
                    probe.get("timeout_seconds", 45),
                    minimum=5,
                    maximum=60,
                    code="runner_access_codex_probe_timeout_invalid",
                ),
            },
        })
    elif mode == "trusted_broker":
        _require_keys(
            codex,
            {"mode", "broker_ref", "authorization_ref"},
            "runner_access_codex_unknown_field",
        )
        broker_ref = str(codex.get("broker_ref") or "")
        authorization_ref = str(codex.get("authorization_ref") or "")
        if broker_ref not in TRUSTED_CODEX_BROKERS:
            raise RunnerAccessError("runner_access_codex_broker_untrusted")
        if not REFERENCE_RE.fullmatch(authorization_ref) or not authorization_ref.startswith("control-plane://home/"):
            raise RunnerAccessError("runner_access_codex_broker_authorization_ref_invalid")
        normalized_codex.update({
            "broker_ref": broker_ref,
            "authorization_ref": authorization_ref,
            # Broker execution remains non-schedulable until the runtime
            # adapter supplies a live attestation. A declaration alone is not
            # an availability claim.
            "requires_runtime_attestation": True,
        })
    elif mode == "disabled":
        _require_keys(codex, {"mode"}, "runner_access_codex_unknown_field")
    else:
        raise RunnerAccessError("runner_access_codex_mode_invalid")

    mimo = runners.get("mimo", {"mode": "local_no_user_auth"})
    if not isinstance(mimo, Mapping) or mimo.get("mode") not in {"local_no_user_auth", "disabled"}:
        raise RunnerAccessError("runner_access_mimo_mode_invalid")
    _require_keys(mimo, {"mode"}, "runner_access_mimo_unknown_field")
    return {
        "schema_version": SCHEMA_VERSION,
        "authority": "home",
        "node_selector": "dynamic-membership",
        "runners": {
            "codex": normalized_codex,
            "mimo": {"mode": str(mimo.get("mode"))},
        },
    }


def load_runner_access_manifest(path: str | Path | None = None) -> dict[str, Any]:
    manifest_path = Path(
        path or os.environ.get("KOLIBRI_RUNNER_ACCESS_MANIFEST") or DEFAULT_MANIFEST
    )
    try:
        info = manifest_path.lstat()
    except FileNotFoundError as exc:
        raise RunnerAccessError("runner_access_manifest_missing") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RunnerAccessError("runner_access_manifest_not_regular")
    if info.st_size > MAX_MANIFEST_BYTES:
        raise RunnerAccessError("runner_access_manifest_too_large")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RunnerAccessError("runner_access_manifest_unreadable") from exc
    return validate_runner_access_manifest(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    try:
        manifest = load_runner_access_manifest(args.manifest)
    except RunnerAccessError as exc:
        print(json.dumps({"status": "invalid", "error": exc.code}, sort_keys=True))
        return 1
    print(json.dumps({
        "status": "valid",
        "schema_version": manifest["schema_version"],
        "authority": manifest["authority"],
        "codex_mode": manifest["runners"]["codex"]["mode"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
