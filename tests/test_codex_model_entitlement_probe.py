from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "codex_model_entitlement_probe", ROOT / "ops" / "codex_model_entitlement_probe.py"
)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def executable(path: Path, body: str) -> Path:
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_probe_records_entitlement_without_raw_output(tmp_path):
    codex = executable(
        tmp_path / "codex",
        "printf '%s\\n' '{\"type\":\"item.completed\",\"item\":{\"type\":\"agent_message\",\"text\":\"KOLIBRI_ENTITLEMENT_OK\"}}'",
    )
    result = probe.probe_model(codex, "gpt-5.6-sol", tmp_path, timeout_seconds=5)
    assert result["entitled"] is True
    assert result["failure_category"] is None
    assert result["output_bytes"] == len(probe.SUCCESS_MARKER)
    assert probe.SUCCESS_MARKER not in json.dumps(result)


def test_probe_classifies_failure_and_never_returns_provider_body(tmp_path):
    secret_body = "authentication failed token=never-return-this"
    codex = executable(
        tmp_path / "codex",
        f"printf '%s\\n' '{secret_body}' >&2; exit 1",
    )
    result = probe.probe_model(codex, "gpt-5.6-sol", tmp_path, timeout_seconds=5)
    serialized = json.dumps(result)
    assert result["entitled"] is False
    assert result["failure_category"] == "authentication"
    assert "never-return-this" not in serialized


def test_report_enables_only_models_with_exact_probe_marker(tmp_path):
    codex = executable(
        tmp_path / "codex",
        "case \"$*\" in *gpt-5.6-terra*) exit 1;; *) printf '%s\\n' '{\"type\":\"item.completed\",\"item\":{\"type\":\"agent_message\",\"text\":\"KOLIBRI_ENTITLEMENT_OK\"}}';; esac",
    )
    report = probe.build_report(
        codex, tmp_path, ["gpt-5.6-sol", "gpt-5.6-terra"], timeout_seconds=5,
    )
    assert report["enabled_models"] == ["gpt-5.6-sol"]
    assert report["schema_version"] == probe.SCHEMA_VERSION
