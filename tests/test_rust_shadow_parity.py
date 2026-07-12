from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "contracts/kolibri-os-v1/fixtures/task-lifecycle-parity.json"
PYTHON_REPLAY = ROOT / "scripts/rust_shadow_python_parity.py"


def test_python_authority_matches_shared_rust_shadow_fixture() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(PYTHON_REPLAY),
            str(FIXTURE),
            "--assert-expected",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    summary = json.loads(completed.stdout)
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))["expected_summary"]
    assert summary == expected
    assert summary["authoritative"] is False
    assert summary["authority"] == "python-control-plane"
    assert summary["rejected_stale_completions"] == 1
