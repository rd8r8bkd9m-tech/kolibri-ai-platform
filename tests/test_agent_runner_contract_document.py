from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "agent" / "AGENT_RUNNER_CONTRACT.md"
AGENT_HOST = ROOT / "ops" / "agent_host.py"
CONTROL_PLANE = ROOT / "ops" / "factory_control.py"


def test_runner_contract_freezes_home_first_attempt_and_completion_truth() -> None:
    text = CONTRACT.read_text(encoding="utf-8")

    for required in (
        "control-plane/home",
        "authority_epoch",
        "fencing_token",
        "max_attempts",
        "active_attempts",
        "runner_auth_blocked",
        "artifact://sha256/<digest>",
        "kolibri.task-completion-evidence.v1",
        "kolibri.task-completion-binding.v1",
        "kolibri.control-plane-completion-verifier.v1",
        "SSH is not worker transport",
        "ContextPack",
    ):
        assert required in text

    assert "`max_retries` is canonical" not in text
    assert "Current compatibility gap" in text
    assert "it does not yet persist or validate `authority_epoch`" in text


def test_runner_contract_tracks_current_python_compatibility_without_claiming_multislot() -> None:
    contract = CONTRACT.read_text(encoding="utf-8")
    agent_host = AGENT_HOST.read_text(encoding="utf-8")
    control = CONTROL_PLANE.read_text(encoding="utf-8")

    # Source evidence for the compatibility statements in the document.
    assert '"active_task": active_task' in agent_host
    assert 'parser.add_argument("--max-inflight"' in agent_host
    assert "self._active_task_id" in agent_host
    assert '"max_attempts": canonical_max_attempts(envelope)' in control
    assert '"fencing_token": 0' in control
    assert '"verifier": "control-plane/home"' in control

    assert "single-slot compatibility worker" in contract
    assert "Scalar `active_task`" in contract
    assert "not durable CAS proof" in contract


def test_runner_contract_marks_old_spellings_and_direct_paths_legacy() -> None:
    text = CONTRACT.read_text(encoding="utf-8")

    assert "`max_retries` | LEGACY input alias" in text
    assert "Direct Mimo/Codex write paths | LEGACY" in text
    assert "Pre-fencing Redis task | LEGACY migration record" in text
    assert "SSH task launch | Forbidden" in text
