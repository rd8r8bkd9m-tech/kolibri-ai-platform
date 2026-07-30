from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.config import Settings
from app.direct_model_runtime import _developer_activity_payload


def test_developer_command_activity_preserves_bounded_safe_output(
    tmp_path: Path,
) -> None:
    tool_name, arguments, result = _developer_activity_payload(
        {
            "type": "commandExecution",
            "command": "/bin/pwd",
            "cwd": str(tmp_path),
            "status": "completed",
            "exitCode": 0,
            "durationMs": 25,
            "output": f"{tmp_path}\n",
        },
        phase="completed",
        workspace_root=tmp_path,
    )

    assert tool_name == "developer_command"
    assert arguments == {"command": "/bin/pwd", "cwd": "."}
    assert result == {
        "status": "completed",
        "exitCode": 0,
        "durationMs": 25,
        "output": str(tmp_path),
    }


def test_developer_file_activity_redacts_sensitive_and_external_paths(
    tmp_path: Path,
) -> None:
    tool_name, arguments, result = _developer_activity_payload(
        {
            "type": "fileChange",
            "status": "completed",
            "changes": [
                {
                    "path": str(tmp_path / ".env.local"),
                    "kind": "update",
                    "diff": "+OPENAI_API_KEY=sk-never-expose-this",
                },
                {
                    "path": str(tmp_path.parent / "outside.txt"),
                    "kind": "update",
                    "diff": "+outside",
                },
            ],
        },
        phase="completed",
        workspace_root=tmp_path,
    )

    assert tool_name == "developer_file_change"
    assert arguments["files"] == [
        {"path": ".env.local", "kind": "update"},
        {"path": "[outside-workspace]", "kind": "update"},
    ]
    assert result["changes"][0]["diff"] == "[REDACTED: sensitive path]"
    assert result["changes"][1]["path"] == "[outside-workspace]"


def test_production_rejects_the_local_developer_adapter(
    tmp_path: Path,
) -> None:
    base = Settings.for_testing(database_url=tmp_path / "test.db")
    with pytest.raises(ValueError, match="cannot run in production"):
        replace(
            base,
            environment="production",
            allowed_origins=("https://app.example.test",),
            cookie_secure=True,
            direct_model_runtime_enabled=True,
            developer_agent_enabled=True,
            developer_workspace_root=tmp_path,
        )
