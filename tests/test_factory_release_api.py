from __future__ import annotations

import importlib.util
import json
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_control():
    path = ROOT / "ops" / "factory_control.py"
    spec = importlib.util.spec_from_file_location("factory_release_contract", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MemoryRedis:
    def __init__(self):
        self.values = {}
        self.sets = {}
        self.lists = {}
        self.lock = threading.Lock()

    def command(self, name, *args):
        name = name.upper()
        if name == "GET":
            return self.values.get(args[0])
        if name == "SET":
            self.values[args[0]] = args[1]
            return "OK"
        if name == "MGET":
            return [self.values.get(key) for key in args]
        if name == "SADD":
            target = self.sets.setdefault(args[0], set())
            before = len(target)
            target.update(args[1:])
            return len(target) - before
        if name == "SREM":
            target = self.sets.setdefault(args[0], set())
            for value in args[1:]:
                target.discard(value)
            return 1
        if name == "SMEMBERS":
            return sorted(self.sets.get(args[0], set()))
        if name == "RPUSH":
            target = self.lists.setdefault(args[0], [])
            target.extend(args[1:])
            return len(target)
        if name == "LREM":
            target = self.lists.setdefault(args[0], [])
            self.lists[args[0]] = [value for value in target if value != args[2]]
            return 1
        if name == "EVAL":
            _script, key_count, *values = args
            keys = values[:key_count]
            argv = values[key_count:]
            with self.lock:
                existing = self.values.get(keys[0])
                if existing is not None:
                    return [0, existing]
                self.values[keys[0]] = argv[0]
                self.values[keys[1]] = argv[1]
                self.sets.setdefault(keys[2], set()).add(argv[2])
                self.lists.setdefault(keys[3], []).append(argv[2])
                if argv[3] == "1":
                    self.sets.setdefault(keys[4], set()).add(argv[2])
                return [1, argv[1]]
        raise AssertionError(f"unsupported fake redis command: {name} {args}")


def approval_body(control):
    return {
        "approval_id": "approval-release-20260710",
        "release_id": "kolibri-2026.07.10",
        "manifest_digest": "sha256:" + "a" * 64,
        "release_signature_namespace": "kolibri-release",
        "release_signer_identity": "owner",
        "decision": "approved",
        "allow_rollback": True,
        "rollback": {
            "release_id": "kolibri-2026.07.09",
            "manifest_digest": "sha256:" + "b" * 64,
            "signature_namespace": "kolibri-release",
            "signer_identity": "owner",
        },
        "rollout_plan": [{"name": "canary", "nodes": ["agent-09"]}],
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        "nonce": "nonce-20260710-01",
        "signer_identity": "owner",
        "signature": "-----BEGIN SSH SIGNATURE-----\nverified-test-signature\n-----END SSH SIGNATURE-----\n",
    }


def store_approval(control, memory, tmp_path, monkeypatch, body=None):
    monkeypatch.setattr(control, "redis", memory)
    allowed = tmp_path / "allowed_signers"
    allowed.write_text("owner ssh-ed25519 public-material\n", encoding="utf-8")
    monkeypatch.setattr(control, "OWNER_ALLOWED_SIGNERS", allowed)
    monkeypatch.setattr(
        control.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )
    record = control.verify_owner_approval(body or approval_body(control))
    control.save_owner_approval(record)
    return record


def test_owner_approval_is_signature_verified_canonical_and_expiring(tmp_path, monkeypatch):
    control = load_control()
    memory = MemoryRedis()
    monkeypatch.setattr(control, "redis", memory)
    allowed = tmp_path / "allowed_signers"
    allowed.write_text("owner ssh-ed25519 public-material\n", encoding="utf-8")
    monkeypatch.setattr(control, "OWNER_ALLOWED_SIGNERS", allowed)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(control.subprocess, "run", fake_run)
    body = approval_body(control)
    record = control.verify_owner_approval(body)
    control.save_owner_approval(record)

    command, kwargs = calls[0]
    assert command[command.index("-n") + 1] == "kolibri-owner-approval"
    assert command[command.index("-I") + 1] == "owner"
    assert b"BEGIN SSH SIGNATURE" not in kwargs["input"]
    assert record["status"] == "approved"
    assert record["approved_by"] == {"role": "owner", "identity": "owner"}
    assert record["attestation"]["signature"] == body["signature"]
    stored = control.get_json(control.owner_approval_key(body["approval_id"]))
    assert stored["release_id"] == body["release_id"]
    assert stored["signature"]["sha256"]
    assert control.list_owner_approvals() == [stored]


def test_owner_approval_rejects_expired_or_unsigned_payload(monkeypatch):
    control = load_control()
    body = approval_body(control)
    body["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError, match="owner_approval_expired"):
        control.verify_owner_approval(body)

    body = approval_body(control)
    body.pop("signature")
    with pytest.raises(ValueError, match="signature_missing"):
        control.verify_owner_approval(body)


def test_release_health_is_derived_from_fenced_task_evidence(monkeypatch):
    control = load_control()
    memory = MemoryRedis()
    monkeypatch.setattr(control, "redis", memory)
    release_id = "kolibri-2026.07.10"
    manifest_digest = "sha256:" + "a" * 64
    task = control.normalize_task({
        "task_id": "release-agent-09",
        "idempotency_key": "release-idempotent-agent-09",
        "kind": "release_bundle_apply",
        "release_id": release_id,
        "target_node": "agent-09",
        "required_capability": "release_apply_v1",
    })
    memory.command("SADD", control.release_task_ids_key(release_id), task["task_id"])
    task["state"] = control.STATE_COMPLETED
    task["result"] = {
        "status": "completed",
        "manifest_digest": manifest_digest,
        "release_health": {
            "status": "healthy",
            "manifest_digest": manifest_digest,
        },
    }
    control.save_task(task)

    health = control.release_health(release_id, "agent-09")
    assert health["status"] == "healthy"
    assert health["manifest_digest"] == manifest_digest
    assert health["task_id"] == task["task_id"]

    unknown = control.release_health(release_id, "other-node")
    assert unknown["status"] == "unknown"


def test_release_task_authority_reverifies_stored_attestation_and_binds_scope(
    tmp_path, monkeypatch
):
    control = load_control()
    memory = MemoryRedis()
    record = store_approval(control, memory, tmp_path, monkeypatch)
    envelope = {
        "task_id": "release-agent-09",
        "idempotency_key": "release-idempotent-agent-09",
        "kind": "release_bundle_apply",
        "release_id": record["release_id"],
        "manifest_digest": record["manifest_digest"],
        "artifact_uri": "artifact://releases/kolibri.tar.gz",
        "source_commit": "0123456789abcdef",
        "target_node": "agent-09",
        "rollout_wave": "canary",
        "required_capability": "release_apply_v1",
        "approval_id": record["approval_id"],
        "signature": {
            "format": "sshsig",
            "namespace": "kolibri-release",
            "signer_identity": "owner",
            "verified_by_controller": True,
        },
    }

    task = control.create_task(envelope)

    stored_envelope = task["envelope"]
    assert stored_envelope["approval_attestation_digest"] == record["attestation_digest"]
    assert stored_envelope["approval_attestation"]["payload"]["release_id"] == record["release_id"]
    assert "verified_by_controller" not in stored_envelope["signature"]

    with pytest.raises(ValueError, match="release_task_approval_scope_mismatch"):
        control.create_task({**envelope, "idempotency_key": "wrong-digest", "manifest_digest": "sha256:" + "f" * 64})
    with pytest.raises(ValueError, match="release_task_rollout_binding_invalid"):
        control.create_task({**envelope, "idempotency_key": "wrong-node", "target_node": "other-node"})
    with pytest.raises(ValueError, match="release_artifact_transport_forbidden"):
        control.create_task({**envelope, "idempotency_key": "remote", "artifact_uri": "https://example.com/release"})


def test_atomic_idempotency_claim_deduplicates_concurrent_requests_and_conflicts(monkeypatch):
    control = load_control()
    memory = MemoryRedis()
    monkeypatch.setattr(control, "redis", memory)
    envelope = {
        "task_id": "idempotent-task",
        "idempotency_key": "same-key",
        "kind": "read_only_probe",
        "objective": "same request",
    }
    results = []
    failures = []

    def submit():
        try:
            results.append(control.create_task(dict(envelope)))
        except Exception as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    threads = [threading.Thread(target=submit) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    assert {result["task_id"] for result in results} == {"idempotent-task"}
    assert memory.lists[control.key("queue")] == ["idempotent-task"]
    with pytest.raises(control.IdempotencyConflict, match="idempotency_key_payload_conflict"):
        control.create_task({**envelope, "objective": "different request"})
