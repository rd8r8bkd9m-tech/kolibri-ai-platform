import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_factory_control_single_file_launcher_imports_siblings_from_repo_workdir(tmp_path):
    install_dir = tmp_path / "usr-local-bin"
    install_dir.mkdir()
    launcher = install_dir / "kolibri-factory-control"
    shutil.copy2(ROOT / "ops" / "factory_control.py", launcher)

    env = os.environ.copy()
    env.pop("KOLIBRI_OPS_DIR", None)
    env.pop("KOLIBRI_REPO_ROOT", None)
    result = subprocess.run(
        ["python3", str(launcher), "--help"],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "ModuleNotFoundError" not in result.stderr


def test_factory_control_systemd_unit_uses_repo_runtime_contract():
    unit = (ROOT / "ops" / "systemd" / "kolibri-factory-control.service").read_text(encoding="utf-8")

    assert "WorkingDirectory=/opt/kolibri-ai-platform" in unit
    assert "Environment=KOLIBRI_REPO_ROOT=/opt/kolibri-ai-platform" in unit
    assert "Environment=KOLIBRI_OPS_DIR=/opt/kolibri-ai-platform/ops" in unit
    assert "ExecStart=/usr/bin/python3 /opt/kolibri-ai-platform/ops/factory_control.py" in unit
    assert "ExecStart=/usr/local/bin/kolibri-factory-control" not in unit


def test_home_dropin_selects_atomic_immutable_runtime_through_fixed_launcher():
    dropin = (
        ROOT
        / "ops/systemd/kolibri-factory-control-immutable-release.conf"
    ).read_text(encoding="utf-8")

    assert "ExecStart=" in dropin
    assert "home_control_plane_launcher.py" in dropin
    assert "control_plane_endpoint.py --assert-local-home" in dropin
    assert "/opt/kolibri-ai-platform/ops/factory_control.py" not in dropin
    assert "EnvironmentFile=" not in dropin


def test_factory_control_runtime_preflight_is_read_only_and_checks_fabric_routes():
    script = ROOT / "scripts" / "preflight-factory-control-runtime.sh"
    text = script.read_text(encoding="utf-8")

    assert "systemctl restart" not in text
    assert "systemctl start" not in text
    assert "telegram" not in text.lower().replace("telegram_superfactory", "")
    assert "/v1/fabric/health" in text
    assert "/v1/fabric/routes" in text

    result = subprocess.run(
        ["bash", str(script), str(ROOT)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "factory_control_runtime_preflight=ok" in result.stdout
