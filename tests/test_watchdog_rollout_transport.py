from pathlib import Path
import json
import os
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_watchdog_rollout_derives_home_and_forbids_agent_forwarding():
    source = (ROOT / "scripts" / "rollout-home-only-watchdogs.sh").read_text(
        encoding="utf-8"
    )

    assert 'HOME_TARGET=""' in source
    assert 'select(.node_id == "home")' in source
    assert 'HOME_TARGET="root@$HOME_IP"' in source
    assert "192.168.88.210" not in source
    assert "ssh -A" not in source
    assert "ProxyJump=home" not in source
    assert 'ProxyJump="$HOME_TARGET"' in source


def test_watchdog_rollout_installs_complete_home_telegram_runtime():
    source = (ROOT / "scripts" / "rollout-home-only-watchdogs.sh").read_text(
        encoding="utf-8"
    )
    unit = (ROOT / "ops" / "systemd" / "kolibri-telegram-gateway.service").read_text(
        encoding="utf-8"
    )

    for module in (
        "telegram_gateway.py",
        "telegram_superfactory.py",
        "telegram_failover_guard.py",
        "orchestrator_memory.py",
        "orchestrator_roster.py",
    ):
        assert f'ops/{module}' in source
        assert f'/usr/local/lib/kolibri/{module}' in source
    assert "ExecStart=/usr/bin/python3 /usr/local/lib/kolibri/telegram_gateway.py" in unit
    assert "/opt/kolibri-ai-platform" not in unit
    assert "Environment=HTTPS_PROXY=http://127.0.0.1:18080" in unit


def test_watchdog_rollout_is_syntax_valid_and_bash_32_compatible():
    script = ROOT / "scripts" / "rollout-home-only-watchdogs.sh"
    subprocess.run(["/bin/bash", "-n", str(script)], check=True)
    source = script.read_text(encoding="utf-8")

    assert "mapfile" not in source
    assert "readarray" not in source
    assert "declare -A" not in source


def test_watchdog_rollout_fails_closed_before_apply_on_incomplete_inventory():
    source = (ROOT / "scripts" / "rollout-home-only-watchdogs.sh").read_text(
        encoding="utf-8"
    )

    gate = source.index('apply_blocked reason=incomplete_inventory')
    first_mutation = source.index("copy_home_runtime_bundle\ninstall_home_runtime")
    assert gate < first_mutation
    assert "unreachable\\t%s\\t%s\\t%s" in source
    assert "multiple_active_receivers" in source
    assert "unmanaged_active_receiver" in source


def test_watchdog_rollout_handoffs_checkpoint_without_printing_secrets():
    source = (ROOT / "scripts" / "rollout-home-only-watchdogs.sh").read_text(
        encoding="utf-8"
    )

    stop = source.index('stop_source_receiver "$SOURCE_NODE" "$SOURCE_IP"')
    copy = source.index('copy_source_checkpoint "$SOURCE_NODE" "$SOURCE_IP"')
    start = source.index("if start_and_verify_home_receiver; then")
    rollback = source.index("handoff_failed reason=home_receiver_verification_failed")
    assert stop < copy < start < rollback
    assert "restart_source_receiver" in source
    assert "state.json.new" in source
    assert "telegram.env.new" in source
    assert "cat /etc/kolibri/telegram.env" not in source
    assert "source /etc/kolibri/telegram.env" not in source
    assert ". /etc/kolibri/telegram.env" not in source
    assert "systemctl cat" not in source


def test_watchdog_rollout_has_no_legacy_node_or_control_plane_literals():
    source = (ROOT / "scripts" / "rollout-home-only-watchdogs.sh").read_text(
        encoding="utf-8"
    )

    assert "10.99." not in source
    assert "kolibri-main" not in source
    assert '"main"' not in source
    assert '"primary"' not in source
    assert "select(.node_id == \"home\")" in source


def test_watchdog_rollout_retires_nonhome_notification_units_by_manifest():
    source = (ROOT / "scripts" / "rollout-home-only-watchdogs.sh").read_text(
        encoding="utf-8"
    )

    assert "retire_nonhome_notifications" in source
    assert "kolibri-factory-cluster-monitor.timer" in source
    assert "*gomesh*evidence*.timer" in source
    assert 'ln -s /dev/null "/etc/systemd/system/$unit"' in source
    assert 'while IFS=$\'\\t\' read -r node ip' in source
    assert '[ "$node" = home ] && continue' in source


def _write_fake_transport(tmp_path: Path, *, worker_reachable: bool) -> tuple[Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "calls.log"
    ssh = fake_bin / "ssh"
    scp = fake_bin / "scp"
    worker_gate = "exit 1" if not worker_reachable else ":"
    ssh.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
printf 'ssh %s\\n' "$*" >>"$FAKE_CALLS"
case " $* " in
  *" root@192.0.2.11 "*) {worker_gate} ;;
esac
case " $* " in
  *" /bin/bash -s -- home 192.0.2.10 home-root "*)
    printf 'home\\t192.0.2.10\\thome-root\\tdisabled\\tinactive\\t0\\t0\\t1\\t1\\t1\\tdisabled\\tinactive\\t5\\t0\\n'
    ;;
  *" /bin/bash -s -- worker-a 192.0.2.11 direct "*)
    printf 'worker-a\\t192.0.2.11\\tdirect\\tmasked\\tinactive\\t0\\t0\\t0\\t0\\t0\\tmasked\\tinactive\\t5\\t0\\n'
    ;;
esac
""",
        encoding="utf-8",
    )
    scp.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf 'scp %s\\n' "$*" >>"$FAKE_CALLS"
exit 97
""",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    scp.chmod(0o755)
    return fake_bin, calls


def _write_test_manifest(tmp_path: Path) -> Path:
    manifest = tmp_path / "peers.json"
    manifest.write_text(
        json.dumps(
            {
                "peers": {
                    "home-key": {"node_id": "home", "mesh_ip": "192.0.2.10"},
                    "worker-key": {"node_id": "worker-a", "mesh_ip": "192.0.2.11"},
                }
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_watchdog_rollout_dry_run_only_audits(tmp_path):
    fake_bin, calls = _write_fake_transport(tmp_path, worker_reachable=True)
    manifest = _write_test_manifest(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["FAKE_CALLS"] = str(calls)

    result = subprocess.run(
        [
            str(ROOT / "scripts" / "rollout-home-only-watchdogs.sh"),
            "--manifest",
            str(manifest),
            "--home-root",
            "root@192.0.2.10",
            "--expect",
            "2",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "summary\tinitial\treachable=2\tunreachable=0\tactive_receivers=0" in result.stdout
    assert "scp " not in calls.read_text(encoding="utf-8")


def test_watchdog_rollout_apply_does_not_mutate_with_unreachable_member(tmp_path):
    fake_bin, calls = _write_fake_transport(tmp_path, worker_reachable=False)
    manifest = _write_test_manifest(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["FAKE_CALLS"] = str(calls)

    result = subprocess.run(
        [
            str(ROOT / "scripts" / "rollout-home-only-watchdogs.sh"),
            "--manifest",
            str(manifest),
            "--home-root",
            "root@192.0.2.10",
            "--expect",
            "2",
            "--apply",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "unreachable\tinitial\tworker-a\t192.0.2.11" in result.stdout
    assert "apply_blocked reason=incomplete_inventory unreachable=1" in result.stderr
    assert "scp " not in calls.read_text(encoding="utf-8")
