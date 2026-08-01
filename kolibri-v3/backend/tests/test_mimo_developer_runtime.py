from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import pytest

from app.mimo_developer_runtime import (
    MimoDeveloperRuntimeError,
    MimoDeveloperServerRuntime,
    _MimoPresentationAdapter,
)


def _fake_auth_file(tmp_path: Path) -> Path:
    auth_file = tmp_path / "source-auth.json"
    auth_file.write_bytes(b'{"opaque":"test-login"}')
    auth_file.chmod(0o600)
    return auth_file


def test_presentation_adapter_exposes_builtin_web_search_as_web_activity(
    tmp_path: Path,
) -> None:
    activities: list[tuple[str, dict[str, Any]]] = []
    adapter = _MimoPresentationAdapter(
        workspace_root=tmp_path,
        on_delta=lambda _delta: None,
        on_activity=lambda phase, item: activities.append((phase, item)),
    )

    adapter.feed_line(
        json.dumps(
            {
                "part": {
                    "type": "tool",
                    "tool": "websearch",
                    "callID": "call_web_01",
                    "state": {
                        "status": "completed",
                        "title": "Latest official release",
                        "input": {"query": "latest official release"},
                        "output": "Official result",
                    },
                }
            }
        ).encode("utf-8")
    )

    assert [phase for phase, _item in activities] == ["started", "completed"]
    assert activities[0][1]["type"] == "webSearch"
    assert activities[0][1]["status"] == "inProgress"
    assert activities[1][1]["query"] == "latest official release"
    assert activities[1][1]["action"] == {"type": "search"}


def _attached_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    script_body: str,
) -> tuple[MimoDeveloperServerRuntime, Path, list[str]]:
    script = tmp_path / "fake_mimo.py"
    observation = tmp_path / "client-observations.jsonl"
    script.write_text(script_body.strip(), encoding="utf-8")
    runtime = MimoDeveloperServerRuntime(
        runtime_root=tmp_path / "mimo-runtime",
        command_prefix=(
            sys.executable,
            str(script),
            str(observation),
        ),
        attached_url="http://127.0.0.1:49291",
        attached_password="test-password",
        auth_file=_fake_auth_file(tmp_path),
    )
    aborts: list[str] = []

    def request_json(
        path: str,
        *,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        timeout: float = 3,
    ) -> Any:
        del body, timeout
        if path.startswith("/session?"):
            sessions = []
            for conversation_key, session_id in runtime._sessions.items():
                sessions.append(
                    {
                        "id": session_id,
                        "title": runtime._session_title(conversation_key),
                        "directory": str(tmp_path),
                        "time": {"updated": 1},
                    }
                )
            return sessions
        if "/abort?" in path and method == "POST":
            aborts.append(path)
            return True
        if path == "/global/health":
            return {"healthy": True, "version": "0.1.9"}
        raise AssertionError(f"unexpected fake MiMo request: {method} {path}")

    monkeypatch.setattr(runtime, "_request_json", request_json)
    return runtime, observation, aborts


@pytest.mark.parametrize(
    ("access_mode", "dangerous_flag_expected"),
    (("auto", False), ("full", True)),
)
def test_persistent_mimo_client_reuses_thread_session_without_secret_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    access_mode: str,
    dangerous_flag_expected: bool,
) -> None:
    runtime, observation, _aborts = _attached_runtime(
        tmp_path,
        monkeypatch,
        script_body="""
import json
import os
from pathlib import Path
import sys

observation = Path(sys.argv[1])
argv = sys.argv[2:]
if "--session" in argv:
    session_id = argv[argv.index("--session") + 1]
else:
    session_id = "ses_persistent_test_01"
record = {
    "argv": argv,
    "cwd": os.getcwd(),
    "env_names": sorted(os.environ),
    "env": {
        name: os.environ.get(name)
        for name in (
            "HOME",
            "XDG_DATA_HOME",
            "XDG_CONFIG_HOME",
            "XDG_CACHE_HOME",
            "XDG_STATE_HOME",
            "MIMOCODE_DISABLE_CLAUDE_IMPORT",
            "MIMOCODE_DISABLE_MODELS_FETCH",
            "MIMOCODE_MIMO_ONLY",
            "MIMOCODE_ENABLE_ANALYSIS",
        )
    },
    "prompt": sys.stdin.read(),
}
with observation.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(record) + "\\n")
print(json.dumps({
    "type": "text",
    "sessionID": session_id,
    "part": {"type": "text", "text": "MiMo completed."},
}))
""",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-child")
    deltas: list[str] = []
    activities: list[tuple[str, dict[str, object]]] = []

    first = runtime.complete(
        workspace_root=tmp_path,
        prompt="Inspect the repository.",
        run_id=f"run-mimo-first-{access_mode}",
        conversation_key="tenant:test-thread",
        timeout=10,
        access_mode=access_mode,
        on_delta=deltas.append,
        on_activity=lambda phase, item: activities.append((phase, item)),
    )
    second = runtime.complete(
        workspace_root=tmp_path,
        prompt="Now run the focused tests.",
        run_id=f"run-mimo-second-{access_mode}",
        conversation_key="tenant:test-thread",
        timeout=10,
        access_mode=access_mode,
        on_delta=deltas.append,
        on_activity=lambda phase, item: activities.append((phase, item)),
    )

    records = [
        json.loads(line)
        for line in observation.read_text(encoding="utf-8").splitlines()
    ]
    assert first.session_id == "ses_persistent_test_01"
    assert second.session_id == first.session_id
    assert [record["prompt"] for record in records] == [
        "Inspect the repository.",
        "Now run the focused tests.",
    ]
    assert "--attach" in records[0]["argv"]
    assert "--title" in records[0]["argv"]
    assert "--session" not in records[0]["argv"]
    assert records[1]["argv"][
        records[1]["argv"].index("--session") + 1
    ] == first.session_id
    assert all(
        record["prompt"] not in record["argv"] for record in records
    )
    assert all(
        (
            "--dangerously-skip-permissions" in record["argv"]
        )
        is dangerous_flag_expected
        for record in records
    )
    assert all(
        "OPENAI_API_KEY" not in record["env_names"]
        for record in records
    )
    assert all(
        record["env"]
        == {
            "HOME": str(tmp_path / "mimo-runtime/home"),
            "XDG_DATA_HOME": str(
                tmp_path / "mimo-runtime/home/.local/share",
            ),
            "XDG_CONFIG_HOME": str(
                tmp_path / "mimo-runtime/home/.config",
            ),
            "XDG_CACHE_HOME": str(
                tmp_path / "mimo-runtime/home/.cache",
            ),
            "XDG_STATE_HOME": str(
                tmp_path / "mimo-runtime/home/.local/state",
            ),
            "MIMOCODE_DISABLE_CLAUDE_IMPORT": "1",
            "MIMOCODE_DISABLE_MODELS_FETCH": "1",
            "MIMOCODE_MIMO_ONLY": "1",
            "MIMOCODE_ENABLE_ANALYSIS": "0",
        }
        for record in records
    )
    assert (
        tmp_path
        / "mimo-runtime/home/.local/share/mimocode/auth.json"
    ).read_bytes() == b'{"opaque":"test-login"}'
    assert deltas == ["MiMo completed.", "MiMo completed."]
    assert activities == []
    assert runtime.inspect() == {
        "server_url": "http://127.0.0.1:49291",
        "server_pid": None,
        "server_process_running": False,
        "attached": True,
        "server_starts": 0,
        "turns_started": 2,
        "turns_active": 0,
        "turns_completed": 2,
        "turns_failed": 0,
        "session_count": 1,
        "sessions": {
            "tenant:test-thread": "ses_persistent_test_01",
        },
    }


def test_mimo_jsonl_is_normalized_to_codex_style_live_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, _observation, _aborts = _attached_runtime(
        tmp_path,
        monkeypatch,
        script_body="""
import json
import sys

sys.stdin.read()
session_id = "ses_presentation_adapter_01"
print(json.dumps({
    "type": "tool_use",
    "sessionID": session_id,
    "part": {
        "type": "tool",
        "tool": "bash",
        "callID": "call_pwd_01",
        "state": {
            "status": "completed",
            "input": {"command": "pwd"},
            "metadata": {"exit": 0},
            "time": {"start": 1000, "end": 1025},
        },
    },
}), flush=True)
print(json.dumps({
    "type": "text",
    "sessionID": session_id,
    "part": {"type": "text", "text": "NORMALIZED_OK"},
}), flush=True)
""",
    )
    deltas: list[str] = []
    activities: list[tuple[str, dict[str, object]]] = []

    result = runtime.complete(
        workspace_root=tmp_path,
        prompt="Run pwd.",
        run_id="run-presentation-adapter-01",
        conversation_key="tenant:presentation-thread",
        timeout=10,
        access_mode="full",
        on_delta=deltas.append,
        on_activity=lambda phase, item: activities.append((phase, item)),
    )

    assert result.text == "NORMALIZED_OK"
    assert deltas == ["NORMALIZED_OK"]
    assert [phase for phase, _item in activities] == [
        "started",
        "completed",
    ]
    started = activities[0][1]
    completed = activities[1][1]
    assert started["type"] == completed["type"] == "commandExecution"
    assert started["command"] == completed["command"] == "pwd"
    assert started["status"] == "inProgress"
    assert completed["status"] == "completed"
    assert completed["exitCode"] == 0
    assert completed["durationMs"] == 25


def test_runtime_starts_one_server_for_its_lifespan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "fake_mimo_server.py"
    observation = tmp_path / "server-observations.jsonl"
    script.write_text(
        """
import json
from pathlib import Path
import sys
import time

observation = Path(sys.argv[1])
with observation.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"argv": sys.argv[2:]}) + "\\n")
time.sleep(30)
""".strip(),
        encoding="utf-8",
    )
    runtime = MimoDeveloperServerRuntime(
        runtime_root=tmp_path / "mimo-runtime",
        command_prefix=(
            sys.executable,
            str(script),
            str(observation),
        ),
        port=49292,
        startup_timeout_seconds=1,
        auth_file=_fake_auth_file(tmp_path),
    )
    monkeypatch.setattr(runtime, "_server_is_healthy", lambda: True)

    runtime.start()
    first_pid = runtime._server_process.pid
    runtime.start()
    assert runtime._server_process.pid == first_pid
    deadline = time.monotonic() + 1
    while not observation.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    runtime.close()

    records = [
        json.loads(line)
        for line in observation.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["argv"][:2] == ["serve", "--hostname"]
    assert "--pure" not in records[0]["argv"]


@pytest.mark.parametrize(
    "attached_url",
    (
        "https://127.0.0.1:49291",
        "http://localhost:49291",
        "http://127.0.0.1",
        "http://user:password@127.0.0.1:49291",
        "http://127.0.0.1:49291/",
        "http://127.0.0.1:49291/session",
        "http://127.0.0.1:49291?next=example.test",
        "http://127.0.0.1:49291#fragment",
    ),
)
def test_attached_server_rejects_noncanonical_loopback_url(
    tmp_path: Path,
    attached_url: str,
) -> None:
    with pytest.raises(MimoDeveloperRuntimeError) as error:
        MimoDeveloperServerRuntime(
            runtime_root=tmp_path / "mimo-runtime",
            command_prefix=(sys.executable,),
            attached_url=attached_url,
            attached_password="test-password",
            auth_file=_fake_auth_file(tmp_path),
        )

    assert error.value.code == "mimo_developer_server_url_invalid"


def test_runtime_rejects_missing_or_public_auth_file(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing-auth.json"
    runtime = MimoDeveloperServerRuntime(
        runtime_root=tmp_path / "missing-runtime",
        command_prefix=(sys.executable,),
        attached_url="http://127.0.0.1:49291",
        attached_password="test-password",
        auth_file=missing,
    )
    with pytest.raises(MimoDeveloperRuntimeError) as missing_error:
        runtime.start()
    assert missing_error.value.code == "mimo_developer_login_required"

    public = tmp_path / "public-auth.json"
    public.write_text('{"opaque":"unsafe"}', encoding="utf-8")
    public.chmod(0o644)
    runtime = MimoDeveloperServerRuntime(
        runtime_root=tmp_path / "public-runtime",
        command_prefix=(sys.executable,),
        attached_url="http://127.0.0.1:49291",
        attached_password="test-password",
        auth_file=public,
    )
    with pytest.raises(MimoDeveloperRuntimeError) as public_error:
        runtime.start()
    assert public_error.value.code == "mimo_developer_auth_file_invalid"


def test_auto_mode_fails_closed_when_permission_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, observation, _aborts = _attached_runtime(
        tmp_path,
        monkeypatch,
        script_body="""
import json
from pathlib import Path
import sys

observation = Path(sys.argv[1])
argv = sys.argv[2:]
sys.stdin.read()
observation.write_text(json.dumps({"argv": argv}), encoding="utf-8")
print(json.dumps({
    "type": "error",
    "sessionID": "ses_permission_test_01",
    "error": {
        "data": {
            "message": "Permission request rejected",
        },
    },
}), flush=True)
""",
    )
    started_at = time.monotonic()

    with pytest.raises(MimoDeveloperRuntimeError) as error:
        runtime.complete(
            workspace_root=tmp_path,
            prompt="Attempt an operation requiring permission.",
            run_id="run-mimo-permission",
            conversation_key="tenant:permission-thread",
            timeout=2,
            access_mode="auto",
            on_delta=lambda _delta: None,
            on_activity=lambda _phase, _item: None,
        )

    assert error.value.code == "mimo_developer_failed"
    assert time.monotonic() - started_at < 2
    recorded = json.loads(observation.read_text(encoding="utf-8"))
    assert "--dangerously-skip-permissions" not in recorded["argv"]


def test_client_timeout_covers_blocked_stdin_and_aborts_server_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, _observation, aborts = _attached_runtime(
        tmp_path,
        monkeypatch,
        script_body="""
import json
import time

print(json.dumps({
    "type": "step_start",
    "sessionID": "ses_timeout_test_01",
}), flush=True)
time.sleep(30)
""",
    )
    started_at = time.monotonic()

    with pytest.raises(MimoDeveloperRuntimeError) as error:
        runtime.complete(
            workspace_root=tmp_path,
            prompt="x" * 190_000,
            run_id="run-mimo-timeout",
            conversation_key="tenant:timeout-thread",
            timeout=0.1,
            access_mode="auto",
            on_delta=lambda _delta: None,
            on_activity=lambda _phase, _item: None,
        )

    assert error.value.code == "mimo_developer_timeout"
    assert time.monotonic() - started_at < 3
    assert any("ses_timeout_test_01/abort" in path for path in aborts)
    assert runtime.inspect()["turns_failed"] == 1


def test_client_rejects_unbounded_output_and_aborts_server_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, _observation, aborts = _attached_runtime(
        tmp_path,
        monkeypatch,
        script_body="""
import json
import sys

sys.stdin.read()
print(json.dumps({
    "type": "step_start",
    "sessionID": "ses_output_test_01",
}), flush=True)
sys.stdout.buffer.write(b"x" * (2 * 1024 * 1024 + 1))
sys.stdout.flush()
""",
    )

    with pytest.raises(MimoDeveloperRuntimeError) as error:
        runtime.complete(
            workspace_root=tmp_path,
            prompt="Produce too much output.",
            run_id="run-mimo-output",
            conversation_key="tenant:output-thread",
            timeout=10,
            access_mode="full",
            on_delta=lambda _delta: None,
            on_activity=lambda _phase, _item: None,
        )

    assert error.value.code == "mimo_developer_output_limit"
    assert any("ses_output_test_01/abort" in path for path in aborts)


@pytest.mark.skipif(
    not hasattr(os, "fork"),
    reason="process-group descendant test requires POSIX fork",
)
def test_client_kills_descendant_that_keeps_output_pipe_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, observation, _aborts = _attached_runtime(
        tmp_path,
        monkeypatch,
        script_body="""
import json
import os
from pathlib import Path
import sys
import time

observation = Path(sys.argv[1])
sys.stdin.read()
child = os.fork()
if child == 0:
    time.sleep(30)
    raise SystemExit(0)
observation.write_text(str(child), encoding="utf-8")
print(json.dumps({
    "type": "text",
    "sessionID": "ses_descendant_test_01",
    "part": {"type": "text", "text": "parent exited"},
}), flush=True)
raise SystemExit(0)
""",
    )

    with pytest.raises(MimoDeveloperRuntimeError) as error:
        runtime.complete(
            workspace_root=tmp_path,
            prompt="Spawn a descendant.",
            run_id="run-mimo-descendant",
            conversation_key="tenant:descendant-thread",
            timeout=10,
            access_mode="auto",
            on_delta=lambda _delta: None,
            on_activity=lambda _phase, _item: None,
        )

    assert error.value.code == "mimo_developer_process_leaked"
    child_pid = int(observation.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail("MiMo descendant survived process-group cleanup")
