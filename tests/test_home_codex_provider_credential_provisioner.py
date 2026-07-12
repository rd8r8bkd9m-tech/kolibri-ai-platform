from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROVISIONER = ROOT / "scripts/linux/provision-home-codex-provider-credential.py"
ROOT_HELPER = ROOT / "scripts/linux/home-codex-provider-credential-root.py"
NODE_ID = "home-codex-provider"
CREDENTIAL_ID = "home-codex-provider-v1"
TOKEN = "home-provider-" + "token-" + "0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def load(path: Path, stem: str):
    name = f"{stem}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict[str, object], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    path.chmod(mode)


def owner_record(epoch: int = 1, token: str = TOKEN) -> dict[str, object]:
    return {
        "schema_version": "kolibri.external-provider-credential.v1",
        "credential_id": CREDENTIAL_ID,
        "node_id": NODE_ID,
        "epoch": epoch,
        "token": token,
    }


def verifier_record(epoch: int = 1, token: str = TOKEN) -> dict[str, object]:
    return {
        "schema_version": "kolibri.external-provider-credential.v1",
        "credential_id": CREDENTIAL_ID,
        "node_id": NODE_ID,
        "epoch": epoch,
        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
    }


def configure_owner(monkeypatch, provisioner, home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(provisioner.Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setattr(provisioner.os, "geteuid", lambda: 1000)


def test_dry_run_never_generates_writes_or_calls_root(tmp_path, monkeypatch, capsys):
    provisioner = load(PROVISIONER, "home_provider_provisioner_dry")
    home = tmp_path / "home"
    configure_owner(monkeypatch, provisioner, home)
    monkeypatch.setattr(
        provisioner.secrets,
        "token_urlsafe",
        lambda *_args: pytest.fail("dry-run generated token"),
    )
    monkeypatch.setattr(
        provisioner,
        "atomic_write",
        lambda *_args, **_kwargs: pytest.fail("dry-run wrote credential"),
    )
    monkeypatch.setattr(
        provisioner,
        "run_root_helper",
        lambda *_args, **_kwargs: pytest.fail("dry-run invoked root helper"),
    )

    assert provisioner.main([]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "validated"
    assert payload["apply"] is False
    assert payload["actor_final_state"] == "drained"
    assert payload["secrets_returned"] is False
    assert not provisioner.credential_destination(home).exists()


def test_apply_stores_raw_owner_record_and_passes_only_hash_stage(
    tmp_path, monkeypatch, capsys,
):
    provisioner = load(PROVISIONER, "home_provider_provisioner_apply")
    home = tmp_path / "home"
    configure_owner(monkeypatch, provisioner, home)
    helper = tmp_path / "root-helper"
    helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    helper.chmod(0o700)
    monkeypatch.setattr(provisioner, "validate_root_helper", lambda _path: helper)
    monkeypatch.setattr(provisioner.secrets, "token_urlsafe", lambda _length: TOKEN)
    observed: dict[str, object] = {}

    def fake_root_helper(
        _helper, *, stage, target, node_id, owner_uid, rotate, migrate_from=None,
    ):
        observed["stage"] = json.loads(stage.read_text(encoding="utf-8"))
        observed["stage_mode"] = stat.S_IMODE(stage.stat().st_mode)
        observed["target"] = str(target)
        observed["node_id"] = node_id
        observed["owner_uid"] = owner_uid
        observed["rotate"] = rotate
        observed["migrate_from"] = migrate_from
        return {
            "status": "binding_verified_actor_drained",
            "node_id": NODE_ID,
            "credential_id": CREDENTIAL_ID,
            "epoch": 1,
            "secrets_returned": False,
        }

    monkeypatch.setattr(provisioner, "run_root_helper", fake_root_helper)
    assert provisioner.main(["--apply", "--root-helper", str(helper)]) == 0

    output = capsys.readouterr().out
    payload = json.loads(output)
    destination = provisioner.credential_destination(home)
    stored = json.loads(destination.read_text(encoding="utf-8"))
    assert stored == owner_record()
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert observed["stage"] == verifier_record()
    assert observed["stage_mode"] == 0o600
    assert observed["migrate_from"] is None
    assert "token" not in observed["stage"]
    assert payload["status"] == "credential_installed_actor_drained"
    assert payload["binding_verified"] is True
    assert payload["secrets_returned"] is False
    assert TOKEN not in output
    assert verifier_record()["token_sha256"] not in output


@pytest.mark.parametrize("epoch", [0, 1, 3])
def test_rotation_requires_exact_next_epoch_before_root_phase(
    epoch: int, tmp_path, monkeypatch,
):
    provisioner = load(PROVISIONER, f"home_provider_rotation_{epoch}")
    home = tmp_path / "home"
    configure_owner(monkeypatch, provisioner, home)
    destination = provisioner.credential_destination(home)
    write_json(destination, owner_record(epoch=1))
    previous = destination.read_bytes()
    monkeypatch.setattr(
        provisioner,
        "run_root_helper",
        lambda *_args, **_kwargs: pytest.fail("invalid rotation reached root"),
    )

    with pytest.raises(provisioner.CredentialProvisionError) as exc_info:
        provisioner.main(["--rotate", "--epoch", str(epoch)])
    assert exc_info.value.code in {"credential_epoch_invalid", "credential_epoch_not_increasing"}
    assert destination.read_bytes() == previous


def test_root_helper_failure_restores_previous_owner_record(tmp_path, monkeypatch):
    provisioner = load(PROVISIONER, "home_provider_owner_rollback")
    home = tmp_path / "home"
    configure_owner(monkeypatch, provisioner, home)
    destination = provisioner.credential_destination(home)
    write_json(destination, owner_record(epoch=1))
    previous = destination.read_bytes()
    helper = tmp_path / "helper"
    helper.touch(mode=0o700)
    source = tmp_path / "next-token"
    source.write_text("next-provider-token-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ\n", encoding="ascii")
    source.chmod(0o600)
    monkeypatch.setattr(provisioner, "validate_root_helper", lambda _path: helper)

    def fail(*_args, **_kwargs):
        raise provisioner.RootHelperDefinitiveFailure("root_helper_failed_root_state_unchanged")

    monkeypatch.setattr(provisioner, "run_root_helper", fail)
    with pytest.raises(provisioner.CredentialProvisionError) as exc_info:
        provisioner.main([
            "--apply", "--rotate", "--epoch", "2",
            "--credential-source", str(source), "--root-helper", str(helper),
        ])
    assert exc_info.value.code == "root_helper_failed_root_state_unchanged"
    assert destination.read_bytes() == previous


def test_owner_invokes_approved_helper_via_sudo_without_credential_material(
    tmp_path, monkeypatch,
):
    provisioner = load(PROVISIONER, "home_provider_sudo_boundary")
    helper = tmp_path / "approved-helper"
    stage = tmp_path / "verifier-stage.json"
    captured: list[str] = []

    def fake_run(command, **_kwargs):
        captured.extend(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({
                "status": "binding_verified_actor_drained",
                "node_id": NODE_ID,
                "credential_id": CREDENTIAL_ID,
                "epoch": 1,
                "secrets_returned": False,
            }),
            stderr="",
        )

    monkeypatch.setattr(provisioner.subprocess, "run", fake_run)
    result = provisioner.run_root_helper(
        helper,
        stage=stage,
        target=provisioner.DEFAULT_ROOT_RECORD,
        node_id=NODE_ID,
        owner_uid=os.getuid(),
        rotate=False,
    )
    assert result["status"] == "binding_verified_actor_drained"
    assert captured[:3] == [str(provisioner.SUDO), "-n", "--"]
    serialized = json.dumps(captured)
    assert TOKEN not in serialized
    assert verifier_record()["token_sha256"] not in serialized


def configure_root(monkeypatch, helper, calls: list[tuple[str, str, object]]):
    monkeypatch.setattr(helper.os, "geteuid", lambda: 0)
    monkeypatch.setattr(helper.os, "chown", lambda *_args: None)

    def fake_request(method, path, body=None):
        calls.append((method, path, body))
        if path.endswith("/drain"):
            assert body == {"drain": True}
            return {"draining": True}
        if path == "/v1/tasks/queue/diagnostics":
            return {
                "redis": "PONG",
                "lease_index_total": 0,
                "expired_leases": 0,
                "stuck_heartbeat_tasks": 0,
            }
        if path == "/v1/health":
            return {"status": "completed"}
        if path.startswith("/v1/runtime/provider-actors"):
            return {
                "auth_configured": True,
                "auth_binding": {
                    "bound_node_id": NODE_ID,
                    "credential_id": CREDENTIAL_ID,
                    "epoch": 1,
                },
            }
        raise AssertionError(path)

    monkeypatch.setattr(helper, "request_json", fake_request)


def test_root_phase_drains_gates_restarts_only_cp_and_verifies_binding(
    tmp_path, monkeypatch,
):
    helper = load(ROOT_HELPER, "home_provider_root_success")
    calls: list[tuple[str, str, object]] = []
    configure_root(monkeypatch, helper, calls)
    restarts: list[str] = []
    monkeypatch.setattr(helper, "restart_factory_control", lambda: restarts.append("cp"))
    stage = tmp_path / "stage.json"
    target = tmp_path / "root" / "auth.json"
    write_json(stage, verifier_record())

    result = helper.apply_root_phase(
        stage=stage,
        target=target,
        node_id=NODE_ID,
        owner_uid=os.getuid(),
        rotate=False,
    )
    assert result == {
        "status": "binding_verified_actor_drained",
        "node_id": NODE_ID,
        "credential_id": CREDENTIAL_ID,
        "epoch": 1,
        "secrets_returned": False,
    }
    assert restarts == ["cp"]
    assert json.loads(target.read_text(encoding="utf-8")) == verifier_record()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert calls[0] == ("POST", f"/v1/nodes/{NODE_ID}/drain", {"drain": True})
    assert calls[1][1] == "/v1/tasks/queue/diagnostics"
    assert not any(body == {"drain": False} for _method, _path, body in calls)


def test_root_phase_rolls_back_record_and_restarts_cp_after_binding_failure(
    tmp_path, monkeypatch,
):
    helper = load(ROOT_HELPER, "home_provider_root_rollback")
    calls: list[tuple[str, str, object]] = []
    configure_root(monkeypatch, helper, calls)
    restarts: list[str] = []
    monkeypatch.setattr(helper, "restart_factory_control", lambda: restarts.append("cp"))
    monkeypatch.setattr(
        helper,
        "wait_for_binding",
        lambda *_args: (_ for _ in ()).throw(helper.RootPhaseError("binding_failed")),
    )
    stage = tmp_path / "stage.json"
    target = tmp_path / "root" / "auth.json"
    write_json(stage, verifier_record())

    with pytest.raises(helper.RootPhaseError) as exc_info:
        helper.apply_root_phase(
            stage=stage,
            target=target,
            node_id=NODE_ID,
            owner_uid=os.getuid(),
            rotate=False,
        )
    assert exc_info.value.code == "binding_failed"
    assert not target.exists()
    assert restarts == ["cp", "cp"]
    assert not any(body == {"drain": False} for _method, _path, body in calls)


def test_root_phase_refuses_nonzero_leases_before_write_or_restart(tmp_path, monkeypatch):
    helper = load(ROOT_HELPER, "home_provider_root_leases")
    monkeypatch.setattr(helper.os, "chown", lambda *_args: None)
    stage = tmp_path / "stage.json"
    target = tmp_path / "auth.json"
    write_json(stage, verifier_record())
    calls: list[tuple[str, str, object]] = []

    def fake_request(method, path, body=None):
        calls.append((method, path, body))
        if path.endswith("/drain"):
            return {"draining": True}
        return {
            "redis": "PONG",
            "lease_index_total": 1,
            "expired_leases": 0,
            "stuck_heartbeat_tasks": 0,
        }

    monkeypatch.setattr(helper, "request_json", fake_request)
    monkeypatch.setattr(
        helper,
        "restart_factory_control",
        lambda: pytest.fail("non-quiescent state restarted CP"),
    )
    with pytest.raises(helper.RootPhaseError) as exc_info:
        helper.apply_root_phase(
            stage=stage,
            target=target,
            node_id=NODE_ID,
            owner_uid=os.getuid(),
            rotate=False,
        )
    assert exc_info.value.code == "home_control_plane_not_quiescent"
    assert not target.exists()


def test_root_phase_independently_rejects_skipped_rotation_epoch(tmp_path, monkeypatch):
    helper = load(ROOT_HELPER, "home_provider_root_rotation_epoch")
    monkeypatch.setattr(helper.os, "chown", lambda *_args: None)
    stage = tmp_path / "stage.json"
    target = tmp_path / "auth.json"
    write_json(target, verifier_record(epoch=1))
    next_token = "next-token-" + "0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    write_json(stage, verifier_record(epoch=3, token=next_token))
    real_read_record = helper.read_record
    monkeypatch.setattr(
        helper,
        "read_record",
        lambda path, *, owner_uid, root_owned: real_read_record(
            path, owner_uid=owner_uid, root_owned=False
        ),
    )
    monkeypatch.setattr(
        helper,
        "request_json",
        lambda *_args, **_kwargs: pytest.fail("invalid epoch reached Control Plane"),
    )

    with pytest.raises(helper.RootPhaseError) as exc_info:
        helper.apply_root_phase(
            stage=stage,
            target=target,
            node_id=NODE_ID,
            owner_uid=os.getuid(),
            rotate=True,
        )
    assert exc_info.value.code == "verifier_epoch_not_increasing"
    assert exc_info.value.owner_rollback_safe is True
    assert json.loads(target.read_text(encoding="utf-8")) == verifier_record(epoch=1)


def test_owner_migrates_existing_global_binding_without_copying_old_token(
    tmp_path, monkeypatch, capsys,
):
    provisioner = load(PROVISIONER, "home_provider_owner_migration")
    home = tmp_path / "home"
    configure_owner(monkeypatch, provisioner, home)
    helper = tmp_path / "root-helper"
    helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    helper.chmod(0o700)
    monkeypatch.setattr(provisioner, "validate_root_helper", lambda _path: helper)
    monkeypatch.setattr(provisioner.secrets, "token_urlsafe", lambda _length: TOKEN)
    observed = {}

    def fake_root_helper(
        _helper, *, stage, target, node_id, owner_uid, rotate, migrate_from=None,
    ):
        observed["stage"] = json.loads(stage.read_text(encoding="utf-8"))
        observed["migrate_from"] = migrate_from
        assert rotate is False
        return {
            "status": "binding_verified_actor_drained",
            "node_id": NODE_ID,
            "credential_id": "home-codex-provider-v2",
            "epoch": 2,
            "secrets_returned": False,
        }

    monkeypatch.setattr(provisioner, "run_root_helper", fake_root_helper)
    assert provisioner.main([
        "--apply",
        "--credential-id", "home-codex-provider-v2",
        "--epoch", "2",
        "--migrate-from-node-id", "mac-codex-provider",
        "--migrate-from-credential-id", "mac-codex-provider-v1",
        "--migrate-from-epoch", "1",
        "--root-helper", str(helper),
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    destination = provisioner.credential_destination(home)
    stored = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["status"] == "credential_migrated_actor_drained"
    assert stored["node_id"] == NODE_ID
    assert stored["credential_id"] == "home-codex-provider-v2"
    assert stored["epoch"] == 2
    assert observed["migrate_from"] == {
        "node_id": "mac-codex-provider",
        "credential_id": "mac-codex-provider-v1",
        "epoch": 1,
    }
    assert "token" not in observed["stage"]


def test_root_phase_migrates_exact_old_binding_and_drains_both_actors(
    tmp_path, monkeypatch,
):
    helper = load(ROOT_HELPER, "home_provider_root_migration")
    monkeypatch.setattr(helper.os, "chown", lambda *_args: None)
    calls: list[tuple[str, str, object]] = []
    new_credential = "home-codex-provider-v2"

    def fake_request(method, path, body=None):
        calls.append((method, path, body))
        if path.endswith("/drain"):
            return {"draining": True}
        if path == "/v1/tasks/queue/diagnostics":
            return {
                "redis": "PONG",
                "lease_index_total": 0,
                "expired_leases": 0,
                "stuck_heartbeat_tasks": 0,
            }
        if path == "/v1/health":
            return {"status": "completed"}
        if path.startswith("/v1/runtime/provider-actors"):
            return {
                "auth_configured": True,
                "auth_binding": {
                    "bound_node_id": NODE_ID,
                    "credential_id": new_credential,
                    "epoch": 2,
                },
            }
        raise AssertionError(path)

    monkeypatch.setattr(helper, "request_json", fake_request)
    monkeypatch.setattr(helper, "restart_factory_control", lambda: None)
    stage = tmp_path / "stage.json"
    target = tmp_path / "root.json"
    old = {
        "schema_version": "kolibri.external-provider-credential.v1",
        "credential_id": "mac-codex-provider-v1",
        "node_id": "mac-codex-provider",
        "epoch": 1,
        "token_sha256": "a" * 64,
    }
    new = {
        "schema_version": "kolibri.external-provider-credential.v1",
        "credential_id": new_credential,
        "node_id": NODE_ID,
        "epoch": 2,
        "token_sha256": "b" * 64,
    }
    write_json(target, old)
    write_json(stage, new)
    real_read_record = helper.read_record
    monkeypatch.setattr(
        helper,
        "read_record",
        lambda path, *, owner_uid, root_owned: real_read_record(
            path, owner_uid=owner_uid, root_owned=False,
        ),
    )

    result = helper.apply_root_phase(
        stage=stage,
        target=target,
        node_id=NODE_ID,
        owner_uid=os.getuid(),
        rotate=False,
        migrate_from={
            "node_id": "mac-codex-provider",
            "credential_id": "mac-codex-provider-v1",
            "epoch": 1,
        },
    )

    assert result["credential_id"] == new_credential
    assert json.loads(target.read_text(encoding="utf-8")) == new
    drains = [path for method, path, body in calls if method == "POST" and body == {"drain": True}]
    assert drains == [
        "/v1/nodes/mac-codex-provider/drain",
        f"/v1/nodes/{NODE_ID}/drain",
    ]


def test_root_phase_rejects_migration_source_mismatch_before_restart(
    tmp_path, monkeypatch,
):
    helper = load(ROOT_HELPER, "home_provider_root_migration_mismatch")
    monkeypatch.setattr(helper.os, "chown", lambda *_args: None)
    stage = tmp_path / "stage.json"
    target = tmp_path / "root.json"
    write_json(target, {
        "schema_version": "kolibri.external-provider-credential.v1",
        "credential_id": "different-provider-v1",
        "node_id": "different-provider",
        "epoch": 1,
        "token_sha256": "c" * 64,
    })
    write_json(stage, verifier_record(epoch=2))
    real_read_record = helper.read_record
    monkeypatch.setattr(
        helper,
        "read_record",
        lambda path, *, owner_uid, root_owned: real_read_record(
            path, owner_uid=owner_uid, root_owned=False,
        ),
    )
    monkeypatch.setattr(
        helper,
        "request_json",
        lambda *_args, **_kwargs: pytest.fail("mismatch reached Control Plane"),
    )
    monkeypatch.setattr(
        helper,
        "restart_factory_control",
        lambda: pytest.fail("mismatch restarted Control Plane"),
    )

    with pytest.raises(helper.RootPhaseError) as exc_info:
        helper.apply_root_phase(
            stage=stage,
            target=target,
            node_id=NODE_ID,
            owner_uid=os.getuid(),
            rotate=False,
            migrate_from={
                "node_id": "mac-codex-provider",
                "credential_id": "mac-codex-provider-v1",
                "epoch": 1,
            },
        )
    assert exc_info.value.code == "verifier_migration_source_mismatch"
    assert exc_info.value.owner_rollback_safe is True


def test_root_helper_source_never_undrains_or_restarts_other_services():
    source = ROOT_HELPER.read_text(encoding="utf-8")
    assert '{"drain": False}' not in source
    assert "kolibri-agent-host.service" not in source
    assert "kolibri-home-codex-provider.service" not in source
    assert source.count('"restart", FACTORY_CONTROL_SERVICE') == 1
    assert "token_sha256" in source
    assert '"token"' not in source
