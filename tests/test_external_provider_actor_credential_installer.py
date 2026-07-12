from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "macos" / "install-external-provider-actor-credential.py"
NODE_ID = "mac-codex-provider-test"
CREDENTIAL_ID = "mac-codex-provider-test-v1"
TOKEN = "test-installer-" + "token-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def load_installer():
    name = f"external_provider_credential_installer_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, INSTALLER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def mac_record(*, epoch: int = 1, token: str = TOKEN) -> dict[str, object]:
    return {
        "schema_version": "kolibri.external-provider-credential.v1",
        "credential_id": CREDENTIAL_ID,
        "node_id": NODE_ID,
        "epoch": epoch,
        "token": token,
    }


def write_private_json(path: Path, payload: dict[str, object], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    path.chmod(mode)


def configure_installer(monkeypatch, module, tmp_path: Path):
    layout = module.MacProviderLayout.from_home(tmp_path / "owner-home")
    monkeypatch.setattr(module.os, "geteuid", lambda: 501)
    monkeypatch.setattr(module, "home_ip", lambda _path: "10.99.0.1")
    monkeypatch.setattr(
        module.MacProviderLayout,
        "from_home",
        classmethod(lambda _cls, _home: layout),
    )
    return layout


def base_args(tmp_path: Path) -> list[str]:
    return [
        "--mesh-manifest", str(tmp_path / "mesh.json"),
        "--node-id", NODE_ID,
        "--credential-id", CREDENTIAL_ID,
    ]


def test_dry_run_never_generates_writes_connects_or_returns_a_secret(
    tmp_path, monkeypatch, capsys,
):
    installer = load_installer()
    layout = configure_installer(monkeypatch, installer, tmp_path)
    monkeypatch.setattr(
        installer.secrets,
        "token_urlsafe",
        lambda *_args, **_kwargs: pytest.fail("dry-run generated a credential"),
    )
    monkeypatch.setattr(
        installer,
        "atomic_write",
        lambda *_args, **_kwargs: pytest.fail("dry-run wrote a credential"),
    )
    monkeypatch.setattr(
        installer,
        "run",
        lambda *_args, **_kwargs: pytest.fail("dry-run contacted Home or launchd"),
    )

    assert installer.main(base_args(tmp_path)) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "validated"
    assert payload["apply"] is False
    assert payload["secrets_returned"] is False
    assert payload["credential_source"] == "generate_on_apply"
    assert not layout.provider_credential.exists()
    serialized = json.dumps(payload, sort_keys=True)
    assert TOKEN not in serialized
    assert hashlib.sha256(TOKEN.encode()).hexdigest() not in serialized


@pytest.mark.parametrize("unsafe_kind", ["symlink", "mode"])
def test_existing_mac_credential_must_be_private_regular_user_owned_file(
    unsafe_kind: str, tmp_path, monkeypatch,
):
    installer = load_installer()
    layout = configure_installer(monkeypatch, installer, tmp_path)
    if unsafe_kind == "symlink":
        target = tmp_path / "credential-target"
        write_private_json(target, mac_record())
        layout.provider_credential.parent.mkdir(parents=True, exist_ok=True)
        layout.provider_credential.symlink_to(target)
    else:
        write_private_json(layout.provider_credential, mac_record(), mode=0o644)

    with pytest.raises(installer.MacProviderConfigError) as exc_info:
        installer.main(base_args(tmp_path))

    assert exc_info.value.code == "credential_destination_unsafe"


@pytest.mark.parametrize("unsafe_kind", ["symlink", "mode"])
def test_credential_source_must_be_private_regular_user_owned_file(
    unsafe_kind: str, tmp_path, monkeypatch,
):
    installer = load_installer()
    configure_installer(monkeypatch, installer, tmp_path)
    source = tmp_path / "source-token"
    if unsafe_kind == "symlink":
        target = tmp_path / "source-token-target"
        target.write_text(TOKEN + "\n", encoding="ascii")
        target.chmod(0o600)
        source.symlink_to(target)
    else:
        source.write_text(TOKEN + "\n", encoding="ascii")
        source.chmod(0o644)

    with pytest.raises(installer.MacProviderConfigError) as exc_info:
        installer.main([*base_args(tmp_path), "--credential-source", str(source)])

    assert exc_info.value.code == "credential_source_unsafe"


def test_existing_credential_requires_explicit_rotation_before_any_write_or_ssh(
    tmp_path, monkeypatch,
):
    installer = load_installer()
    layout = configure_installer(monkeypatch, installer, tmp_path)
    write_private_json(layout.provider_credential, mac_record())
    previous = layout.provider_credential.read_bytes()
    monkeypatch.setattr(
        installer,
        "run",
        lambda *_args, **_kwargs: pytest.fail("rotation guard contacted Home"),
    )

    with pytest.raises(installer.MacProviderConfigError) as exc_info:
        installer.main([*base_args(tmp_path), "--apply"])

    assert exc_info.value.code == "credential_exists_rotate_required"
    assert layout.provider_credential.read_bytes() == previous


@pytest.mark.parametrize("requested_epoch", [1, 3, 0])
def test_rotation_epoch_must_be_exactly_one_greater_than_the_current_record(
    requested_epoch: int, tmp_path, monkeypatch,
):
    installer = load_installer()
    layout = configure_installer(monkeypatch, installer, tmp_path)
    write_private_json(layout.provider_credential, mac_record(epoch=1))
    previous = layout.provider_credential.read_bytes()
    monkeypatch.setattr(
        installer,
        "run",
        lambda *_args, **_kwargs: pytest.fail("bad epoch contacted Home"),
    )

    with pytest.raises(installer.MacProviderConfigError) as exc_info:
        installer.main([
            *base_args(tmp_path), "--rotate", "--epoch", str(requested_epoch),
        ])

    assert exc_info.value.code in {
        "credential_epoch_invalid",
        "credential_epoch_not_increasing",
    }
    assert layout.provider_credential.read_bytes() == previous


def test_apply_stores_raw_token_only_on_mac_and_hash_only_in_home_stage(
    tmp_path, monkeypatch, capsys,
):
    installer = load_installer()
    layout = configure_installer(monkeypatch, installer, tmp_path)
    monkeypatch.setattr(installer.secrets, "token_urlsafe", lambda _length: TOKEN)
    calls: list[tuple[list[str], bytes | None, tuple[int, ...]]] = []
    home_record: dict[str, object] = {}

    def fake_run(command, *, stdin=None, accepted_returncodes=(0,)):
        command = list(command)
        calls.append((command, stdin, accepted_returncodes))
        if command[0] == "scp":
            home_record.update(json.loads(Path(command[-2]).read_text(encoding="utf-8")))
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(installer, "run", fake_run)

    assert installer.main([*base_args(tmp_path), "--apply"]) == 0

    output = capsys.readouterr().out
    plan = json.loads(output)
    stored = json.loads(layout.provider_credential.read_text(encoding="utf-8"))
    expected_hash = hashlib.sha256(TOKEN.encode("utf-8")).hexdigest()
    assert stored == mac_record()
    assert "token_sha256" not in stored
    assert stat.S_IMODE(layout.provider_credential.stat().st_mode) == 0o600
    assert home_record == {
        "schema_version": "kolibri.external-provider-credential.v1",
        "credential_id": CREDENTIAL_ID,
        "node_id": NODE_ID,
        "epoch": 1,
        "token_sha256": expected_hash,
    }
    assert "token" not in home_record
    assert plan["status"] == "credential_installed_actor_drained"
    assert plan["secrets_returned"] is False
    visible = output + json.dumps([call[0] for call in calls])
    assert TOKEN not in visible
    assert expected_hash not in visible
    assert [call[0][0] for call in calls] == ["ssh", "scp", "ssh"]
    assert calls[0][0][-4:-1] == ["install", "-d", "-m700"]
    assert calls[0][0][-1].startswith("/run/kolibri/external-provider-auth-")
    apply_call = calls[-1]
    assert apply_call[1] == installer.remote_apply_script()


def test_remote_apply_contract_drains_then_checks_zero_leases_and_can_roll_back():
    installer = load_installer()
    script = installer.remote_apply_script().decode("utf-8")
    drain = script.index('"http://127.0.0.1:9101/v1/nodes/${node_id}/drain"')
    diagnostics = script.index("/v1/tasks/queue/diagnostics")
    leases = script.index("'.lease_index_total'")
    backup = script.index('cp -a "$target" "$backup/previous"')
    trap = script.index("trap rollback ERR INT TERM")
    install = script.index('install -o root -g root -m600 "$stage" "$target"')
    restart = script.index("systemctl restart kolibri-factory-control.service", install)
    assert drain < diagnostics < leases < backup < trap < install < restart
    assert "expired_leases" in script
    assert "stuck_heartbeat_tasks" in script
    assert 'cp -a "$backup/previous" "$target"' in script


def test_remote_validation_cannot_delete_an_existing_home_record_before_backup():
    installer = load_installer()
    apply_script = installer.remote_apply_script().decode("utf-8")
    last_rotation_validation = apply_script.index(
        'test "$new_epoch" -eq $((expected_epoch + 1))'
    )
    backup = apply_script.index('cp -a "$target" "$backup/previous"')
    absent_marker = apply_script.index(': >"$backup/absent"')
    trap = apply_script.index("trap rollback ERR INT TERM")
    assert last_rotation_validation < backup < trap
    assert last_rotation_validation < absent_marker < trap

    rollback_script = installer.remote_rollback_script().decode("utf-8")
    assert 'if [ -e "$backup/previous" ]' in rollback_script
    assert 'elif [ -e "$backup/absent" ]' in rollback_script
    assert 'else rm -f "$target"' not in rollback_script


def test_rotation_reconciles_the_exact_previous_home_hash_and_schema(
    tmp_path, monkeypatch, capsys,
):
    installer = load_installer()
    layout = configure_installer(monkeypatch, installer, tmp_path)
    previous_token = "previous-token-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    next_token = "next-token-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZABCD"
    write_private_json(layout.provider_credential, mac_record(epoch=1, token=previous_token))
    source = tmp_path / "next-token"
    source.write_text(next_token + "\n", encoding="ascii")
    source.chmod(0o600)
    calls: list[tuple[list[str], bytes | None]] = []

    def fake_run(command, *, stdin=None, accepted_returncodes=(0,)):
        command = list(command)
        calls.append((command, stdin))
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(installer, "run", fake_run)
    assert installer.main([
        *base_args(tmp_path), "--credential-source", str(source),
        "--apply", "--rotate", "--reload-launch-agent", "--epoch", "2",
    ]) == 0
    capsys.readouterr()

    apply_command = next(
        command for command, stdin in calls if stdin == installer.remote_apply_script()
    )
    expected_previous_hash = hashlib.sha256(previous_token.encode("utf-8")).hexdigest()
    assert apply_command[-5:] == [
        CREDENTIAL_ID, "1", expected_previous_hash, "2", "1",
    ]
    assert previous_token not in json.dumps(apply_command)
    script = installer.remote_apply_script().decode("utf-8")
    assert "jq -r '.schema_version'" in script
    assert "kolibri.external-provider-credential.v1" in script
    assert "jq -r '.token_sha256'" in script
    assert '"$expected_hash"' in script


def test_home_restart_gate_requires_exact_new_auth_binding():
    installer = load_installer()
    script = installer.remote_apply_script().decode("utf-8")
    assert ".auth_configured == true" in script
    assert ".auth_binding.bound_node_id == $node" in script
    assert ".auth_binding.credential_id == $credential" in script
    assert ".auth_binding.epoch == $epoch" in script
    assert "--arg node \"$node_id\"" in script
    assert "--arg credential \"$new_id\"" in script
    assert "--argjson epoch \"$new_epoch\"" in script


def test_failed_remote_apply_restores_mac_record_and_invokes_home_rollback(
    tmp_path, monkeypatch,
):
    installer = load_installer()
    layout = configure_installer(monkeypatch, installer, tmp_path)
    previous_record = mac_record(
        epoch=1,
        token="previous-" + "token-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    )
    write_private_json(layout.provider_credential, previous_record)
    previous = layout.provider_credential.read_bytes()
    monkeypatch.setattr(installer.secrets, "token_urlsafe", lambda _length: TOKEN)
    calls: list[tuple[list[str], bytes | None]] = []

    def fake_run(command, *, stdin=None, accepted_returncodes=(0,)):
        command = list(command)
        calls.append((command, stdin))
        if stdin == installer.remote_apply_script():
            raise installer.MacProviderConfigError("credential_install_command_failed")
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(installer, "run", fake_run)

    with pytest.raises(installer.MacProviderConfigError) as exc_info:
        installer.main([
            *base_args(tmp_path),
            "--apply", "--rotate", "--reload-launch-agent", "--epoch", "2",
        ])

    assert exc_info.value.code == "credential_install_command_failed"
    assert layout.provider_credential.read_bytes() == previous
    apply_index = next(
        index for index, (_command, stdin) in enumerate(calls)
        if stdin == installer.remote_apply_script()
    )
    rollback_index = next(
        index for index, (_command, stdin) in enumerate(calls)
        if stdin == installer.remote_rollback_script()
    )
    assert apply_index < rollback_index
    rollback_command = calls[rollback_index][0]
    assert rollback_command[0] == "ssh"
    assert rollback_command[-2] == installer.HOME_AUTH_FILE


def test_rotation_requires_launch_agent_reload_before_any_mutation(tmp_path, monkeypatch):
    installer = load_installer()
    layout = configure_installer(monkeypatch, installer, tmp_path)
    write_private_json(layout.provider_credential, mac_record(epoch=1))
    previous = layout.provider_credential.read_bytes()
    monkeypatch.setattr(
        installer,
        "run",
        lambda *_args, **_kwargs: pytest.fail("unsafe rotation contacted Home"),
    )

    with pytest.raises(installer.MacProviderConfigError) as exc_info:
        installer.main([
            *base_args(tmp_path), "--apply", "--rotate", "--epoch", "2",
        ])

    assert exc_info.value.code == "rotation_requires_launch_agent_reload"
    assert layout.provider_credential.read_bytes() == previous


def test_initial_install_rejects_inline_launch_agent_reload_before_mutation(tmp_path, monkeypatch):
    installer = load_installer()
    layout = configure_installer(monkeypatch, installer, tmp_path)
    monkeypatch.setattr(
        installer, "run",
        lambda *_args, **_kwargs: pytest.fail("initial two-phase gate contacted Home"),
    )

    with pytest.raises(installer.MacProviderConfigError) as exc_info:
        installer.main([*base_args(tmp_path), "--apply", "--reload-launch-agent"])

    assert exc_info.value.code == "initial_install_requires_separate_launch_agent_load"
    assert not layout.provider_credential.exists()


def test_rotation_never_downgrades_after_new_server_marker_is_bound(tmp_path, monkeypatch):
    installer = load_installer()
    layout = configure_installer(monkeypatch, installer, tmp_path)
    previous_token = "previous-token-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    next_token = "next-token-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZABCD"
    write_private_json(layout.provider_credential, mac_record(epoch=1, token=previous_token))
    source = tmp_path / "next-token"
    source.write_text(next_token + "\n", encoding="ascii")
    source.chmod(0o600)
    rollback_called = False

    def fake_run(command, *, stdin=None, accepted_returncodes=(0,)):
        nonlocal rollback_called
        command = list(command)
        if command[0] == "/bin/launchctl":
            raise installer.MacProviderConfigError("credential_install_command_failed")
        if stdin == installer.remote_marker_probe_script():
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")
        if stdin == installer.remote_rollback_script():
            rollback_called = True
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(installer, "run", fake_run)
    with pytest.raises(installer.MacProviderConfigError) as exc_info:
        installer.main([
            *base_args(tmp_path), "--credential-source", str(source),
            "--apply", "--rotate", "--reload-launch-agent", "--epoch", "2",
        ])

    assert exc_info.value.code == "credential_rotation_committed_actor_drained_recovery_required"
    current = json.loads(layout.provider_credential.read_text(encoding="utf-8"))
    assert current["epoch"] == 2
    assert current["token"] == next_token
    assert rollback_called is False


def test_rotation_never_downgrades_when_marker_state_is_uncertain_after_home_switch(
    tmp_path, monkeypatch,
):
    installer = load_installer()
    layout = configure_installer(monkeypatch, installer, tmp_path)
    previous_token = "previous-token-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    next_token = "next-token-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZABCD"
    write_private_json(layout.provider_credential, mac_record(epoch=1, token=previous_token))
    source = tmp_path / "next-token"
    source.write_text(next_token + "\n", encoding="ascii")
    source.chmod(0o600)
    rollback_called = False

    def fake_run(command, *, stdin=None, accepted_returncodes=(0,)):
        nonlocal rollback_called
        command = list(command)
        if stdin == installer.remote_verify_actor_script():
            raise installer.MacProviderConfigError("credential_install_command_failed")
        if stdin == installer.remote_marker_probe_script():
            return subprocess.CompletedProcess(command, 1, stdout=b"", stderr=b"")
        if stdin == installer.remote_rollback_script():
            rollback_called = True
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(installer, "run", fake_run)
    with pytest.raises(installer.MacProviderConfigError) as exc_info:
        installer.main([
            *base_args(tmp_path), "--credential-source", str(source),
            "--apply", "--rotate", "--reload-launch-agent", "--epoch", "2",
        ])

    assert exc_info.value.code == "credential_rotation_switched_actor_drained_recovery_required"
    current = json.loads(layout.provider_credential.read_text(encoding="utf-8"))
    assert current["epoch"] == 2
    assert current["token"] == next_token
    assert rollback_called is False
