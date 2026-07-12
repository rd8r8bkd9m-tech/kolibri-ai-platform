from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_runtime_version_pins.py"


def test_runtime_pins_are_single_source_and_workflows_are_consistent():
    result = subprocess.run(
        ["python3", str(SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "runtime_pins=ok node=26.5.0 npm=11.17.0 python=3.14.6" in result.stdout
