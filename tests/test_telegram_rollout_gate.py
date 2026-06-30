import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_gate():
    spec = importlib.util.spec_from_file_location("telegram_readable_rollout_gate", ROOT / "scripts" / "telegram_readable_rollout_gate.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_rollout_gate_writes_offline_artifact(tmp_path):
    gate = load_gate()
    report = tmp_path / "telegram-rollout-gate-report.json"

    assert gate.main(["--report", str(report)]) == 0

    data = json.loads(report.read_text(encoding="utf-8"))
    checks = {check["name"]: check for check in data["checks"]}
    assert checks["no_raw_json_formatter"]["status"] == "pass"
    assert checks["html_escaping"]["status"] == "pass"
    assert checks["getupdates_409_ownership_contract"]["status"] == "pass"
    assert checks["live_telegram"]["status"] == "skip"
    assert data["rollback"]["command_configured"] is False
