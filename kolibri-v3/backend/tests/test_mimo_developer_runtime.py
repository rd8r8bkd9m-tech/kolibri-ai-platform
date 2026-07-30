from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import pytest

from app.mimo_developer_runtime import (
    _MimoEventBridge,
    _ParsedClientOutput,
    MimoDeveloperRuntimeError,
    MimoDeveloperServerRuntime,
)


def _fake_auth_file(tmp_path: Path) -> Path:
    auth_file = tmp_path / "source-auth.json"
    auth_file.write_bytes(b'{"opaque":"test-login"}')
    auth_file.chmod(0o600)
    return auth_file


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


def test_live_event_bridge_streams_text_and_tool_lifecycle(
    tmp_path: Path,
) -> None:
    deltas: list[str] = []
    activities: list[tuple[str, dict[str, Any]]] = []
    bridge = _MimoEventBridge(
        server_url="http://127.0.0.1:49291",
        authorization_header="Basic test",
        workspace_root=tmp_path,
        session_id=None,
        session_title="kolibri-thread-test",
        on_delta=deltas.append,
        on_activity=lambda phase, item: activities.append(
            (phase, item)
        ),
    )
    session_id = "ses_live_stream_test_01"
    message_id = "msg_assistant_01"
    bridge._handle_event(
        {
            "type": "session.created",
            "properties": {
                "sessionID": session_id,
                "info": {
                    "id": session_id,
                    "title": "kolibri-thread-test",
                    "directory": str(tmp_path),
                },
            },
        }
    )
    bridge._handle_event(
        {
            "type": "message.updated",
            "properties": {
                "sessionID": session_id,
                "info": {
                    "id": message_id,
                    "role": "assistant",
                },
            },
        }
    )
    bridge._handle_event(
        {
            "type": "message.part.updated",
            "properties": {
                "sessionID": session_id,
                "part": {
                    "id": "prt_text_01",
                    "messageID": message_id,
                    "type": "text",
                    "text": "",
                },
            },
        }
    )
    for delta in ("MiMo ", "streamed."):
        bridge._handle_event(
            {
                "type": "message.part.delta",
                "properties": {
                    "sessionID": session_id,
                    "messageID": message_id,
                    "partID": "prt_text_01",
                    "field": "text",
                    "delta": delta,
                },
            }
        )
    bridge._handle_event(
        {
            "type": "message.part.updated",
            "properties": {
                "sessionID": session_id,
                "part": {
                    "id": "prt_tool_01",
                    "messageID": message_id,
                    "type": "tool",
                    "tool": "bash",
                    "state": {
                        "status": "completed",
                        "input": {"command": "/bin/pwd"},
                        "output": f"{tmp_path}\n",
                        "metadata": {"exit": 0},
                        "time": {"start": 1_000, "end": 1_025},
                    },
                },
            },
        }
    )

    assert deltas == ["MiMo ", "streamed."]
    assert bridge.streamed_text == "MiMo streamed."
    assert [phase for phase, _item in activities] == [
        "started",
        "completed",
    ]
    started = activities[0][1]
    completed = activities[1][1]
    assert started == {
        "schemaId": "kolibri.agent-activity",
        "schemaVersion": "1.0",
        "id": "mimo-tool-prt_tool_01",
        "type": "commandExecution",
        "command": "/bin/pwd",
        "cwd": str(tmp_path),
        "status": "inProgress",
    }
    assert completed["status"] == "completed"
    assert completed["exitCode"] == 0
    assert completed["durationMs"] == 25
    assert completed["output"] == str(tmp_path)


def test_runtime_uses_live_stream_as_final_text_when_cli_omits_duplicate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = MimoDeveloperServerRuntime(
        runtime_root=tmp_path / "runtime",
        command_prefix=(sys.executable,),
        auth_file=_fake_auth_file(tmp_path),
    )
    monkeypatch.setattr(runtime, "_executable", lambda: Path(sys.executable))
    monkeypatch.setattr(runtime, "_ensure_started", lambda: None)
    monkeypatch.setattr(runtime, "_discover_session", lambda **_kwargs: None)
    monkeypatch.setattr(
        runtime,
        "_run_client",
        lambda **_kwargs: _ParsedClientOutput(
            text="Ответ из SSE",
            session_id="ses_stream_only_01",
            error_message=None,
            streamed_text="Ответ из SSE",
        ),
    )
    deltas: list[str] = []

    result = runtime.complete(
        workspace_root=tmp_path,
        prompt="Ответь.",
        run_id="run-stream-only",
        conversation_key="tenant:stream-only",
        timeout=10,
        access_mode="auto",
        on_delta=deltas.append,
        on_activity=lambda _phase, _item: None,
    )

    assert result.text == "Ответ из SSE"
    assert deltas == []


def test_live_event_bridge_maps_file_tools_to_file_changes(
    tmp_path: Path,
) -> None:
    activities: list[tuple[str, dict[str, object]]] = []
    bridge = _MimoEventBridge(
        server_url="http://127.0.0.1:49291",
        authorization_header="Basic test",
        workspace_root=tmp_path,
        session_id="ses_test_file",
        session_title="Kolibri test",
        on_delta=lambda _delta: None,
        on_activity=lambda phase, item: activities.append((phase, item)),
    )
    bridge._assistant_message_ids.add("msg_assistant_file")

    bridge._handle_event(
        {
            "type": "message.part.updated",
            "properties": {
                "sessionID": "ses_test_file",
                "part": {
                    "id": "prt_tool_file",
                    "messageID": "msg_assistant_file",
                    "type": "tool",
                    "tool": "edit",
                    "state": {
                        "status": "running",
                        "input": {
                            "filePath": str(tmp_path / "app.py"),
                            "oldString": "before",
                            "newString": "after",
                        },
                    },
                },
            },
        }
    )
    bridge._handle_event(
        {
            "type": "message.part.updated",
            "properties": {
                "sessionID": "ses_test_file",
                "part": {
                    "id": "prt_tool_file",
                    "messageID": "msg_assistant_file",
                    "type": "tool",
                    "tool": "edit",
                    "state": {
                        "status": "completed",
                        "input": {
                            "filePath": str(tmp_path / "app.py"),
                            "oldString": "before",
                            "newString": "after",
                        },
                        "metadata": {
                            "diff": "-before\n+after",
                        },
                    },
                },
            },
        }
    )

    assert activities == [
        (
            "started",
            {
                "schemaId": "kolibri.agent-activity",
                "schemaVersion": "1.0",
                "id": "mimo-tool-prt_tool_file",
                "type": "fileChange",
                "status": "inProgress",
                "changes": [
                    {
                        "path": str(tmp_path / "app.py"),
                        "kind": "update",
                        "diff": "",
                    }
                ],
            },
        ),
        (
            "completed",
            {
                "schemaId": "kolibri.agent-activity",
                "schemaVersion": "1.0",
                "id": "mimo-tool-prt_tool_file",
                "type": "fileChange",
                "status": "completed",
                "changes": [
                    {
                        "path": str(tmp_path / "app.py"),
                        "kind": "update",
                        "diff": "-before\n+after",
                    }
                ],
            },
        ),
    ]


def test_live_event_bridge_extracts_paths_from_apply_patch(
    tmp_path: Path,
) -> None:
    activities: list[tuple[str, dict[str, object]]] = []
    bridge = _MimoEventBridge(
        server_url="http://127.0.0.1:49291",
        authorization_header="Basic test",
        workspace_root=tmp_path,
        session_id="ses_test_patch",
        session_title="Kolibri test",
        on_delta=lambda _delta: None,
        on_activity=lambda phase, item: activities.append((phase, item)),
    )
    bridge._assistant_message_ids.add("msg_assistant_patch")
    patch = (
        "*** Begin Patch\n"
        "*** Update File: src/a.py\n"
        "@@\n-old\n+new\n"
        "*** Add File: src/b.py\n"
        "+created\n"
        "*** End Patch"
    )

    bridge._handle_event(
        {
            "type": "message.part.updated",
            "properties": {
                "sessionID": "ses_test_patch",
                "part": {
                    "id": "prt_tool_patch",
                    "messageID": "msg_assistant_patch",
                    "type": "tool",
                    "tool": "apply_patch",
                    "state": {
                        "status": "completed",
                        "input": {"patchText": patch},
                    },
                },
            },
        }
    )

    assert activities[0][1]["type"] == "fileChange"
    assert [
        change["path"]
        for change in activities[1][1]["changes"]
    ] == ["src/a.py", "src/b.py"]
    assert all(
        change["diff"] == patch
        for change in activities[1][1]["changes"]
    )


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
    assert records[0]["argv"][:2] == ["serve", "--pure"]


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
