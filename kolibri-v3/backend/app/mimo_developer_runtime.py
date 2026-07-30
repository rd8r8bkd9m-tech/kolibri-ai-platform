"""Persistent local MiMo Code server adapter for owner developer runs."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import stat
import subprocess
import tempfile
import threading
import time
from typing import Any, Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .agent_runtime import canonical_runtime_activity


_CLIENT_STDOUT_LIMIT = 2 * 1024 * 1024
_CLIENT_STDERR_LIMIT = 256 * 1024
_SERVER_LOG_TAIL_LIMIT = 128 * 1024
_PROMPT_LIMIT = 200_000
_SESSION_ID_PREFIX = "ses_"
_AUTH_FILE_LIMIT = 1024 * 1024
_SESSION_ID_PATTERN = re.compile(r"ses_[A-Za-z0-9_-]{1,124}")
_EVENT_LINE_LIMIT = 256 * 1024
_EVENT_CONNECT_TIMEOUT_SECONDS = 3.0
_EVENT_DRAIN_TIMEOUT_SECONDS = 1.0
_TERMINAL_TOOL_STATES = frozenset(
    {"completed", "error", "failed", "cancelled"}
)
_FILE_TOOL_NAMES = frozenset(
    {
        "apply_patch",
        "edit",
        "multiedit",
        "patch",
        "write",
    }
)
_PATCH_FILE_PATTERN = re.compile(
    r"(?m)^\*\*\* (?:Add|Delete|Update) File: (.+?)\s*$"
)


class MimoDeveloperRuntimeError(RuntimeError):
    """Public-safe MiMo developer runtime failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class MimoDeveloperResult:
    text: str
    session_id: str


@dataclass(frozen=True, slots=True)
class _ParsedClientOutput:
    text: str
    session_id: str | None
    error_message: str | None
    streamed_text: str = ""


class _ByteBuffer:
    def __init__(self, *, limit: int, rolling: bool = False) -> None:
        self._limit = limit
        self._rolling = rolling
        self._value = bytearray()
        self._lock = threading.Lock()
        self.overflow = threading.Event()

    def append(self, chunk: bytes) -> None:
        with self._lock:
            if self._rolling:
                self._value.extend(chunk)
                extra = len(self._value) - self._limit
                if extra > 0:
                    del self._value[:extra]
                return
            remaining = self._limit - len(self._value)
            if remaining > 0:
                self._value.extend(chunk[:remaining])
            if len(chunk) > remaining:
                self.overflow.set()

    def bytes(self) -> bytes:
        with self._lock:
            return bytes(self._value)


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        text = content.get("text")
        return text if isinstance(text, str) else ""
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if (
                    isinstance(text, str)
                    and item.get("type") in {None, "text", "output_text"}
                ):
                    parts.append(text)
        return "".join(parts)
    return ""


def _parse_client_output(raw: bytes) -> _ParsedClientOutput:
    final_messages: list[str] = []
    text_parts: list[str] = []
    deltas: list[str] = []
    session_id: str | None = None
    observed_session_ids: set[str] = set()
    error_message: str | None = None
    for raw_line in raw.decode("utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            event: Any = json.loads(line)
        except (TypeError, ValueError):
            continue
        if not isinstance(event, dict):
            continue
        if "sessionID" in event:
            candidate_session_id = _valid_session_id(
                event.get("sessionID"),
            )
            if candidate_session_id is None:
                error_message = (
                    "MiMo Code returned invalid session metadata."
                )
            else:
                observed_session_ids.add(candidate_session_id)
                session_id = candidate_session_id
        if event.get("type") == "error":
            error = event.get("error")
            if isinstance(error, dict):
                data = error.get("data")
                if isinstance(data, dict) and isinstance(
                    data.get("message"),
                    str,
                ):
                    error_message = str(data["message"])[:500]
                elif isinstance(error.get("message"), str):
                    error_message = str(error["message"])[:500]
            if error_message is None:
                error_message = "MiMo Code reported an execution error."
        part = event.get("part")
        if (
            isinstance(part, dict)
            and part.get("type") == "text"
            and isinstance(part.get("text"), str)
        ):
            text_parts.append(str(part["text"]))
        message = event.get("msg")
        if isinstance(message, dict):
            text = (
                message.get("message")
                or message.get("text")
                or _content_text(message.get("content"))
            )
            if isinstance(text, str) and text:
                if "delta" in str(message.get("type") or ""):
                    deltas.append(text)
                else:
                    final_messages.append(text)
        event_text = (
            event.get("message")
            or event.get("text")
            or _content_text(event.get("content"))
        )
        if isinstance(event_text, str) and event_text:
            event_type = str(event.get("type") or "")
            if "delta" in event_type:
                deltas.append(event_text)
            elif event_type in {
                "agent_message",
                "assistant_message",
                "message",
            }:
                final_messages.append(event_text)
        item = event.get("item")
        if (
            isinstance(item, dict)
            and item.get("type")
            in {"message", "assistant_message", "agent_message"}
        ):
            item_text = (
                item.get("message")
                or item.get("text")
                or _content_text(item.get("content"))
            )
            if isinstance(item_text, str) and item_text:
                final_messages.append(item_text)
    if len(observed_session_ids) > 1:
        session_id = None
        error_message = "MiMo Code returned mixed session metadata."
    text = ""
    for candidates in (final_messages, text_parts, deltas):
        text = "".join(candidates).strip()
        if text:
            break
    return _ParsedClientOutput(
        text=text[:200_000],
        session_id=session_id,
        error_message=error_message,
    )


def _read_stream(stream: Any, destination: _ByteBuffer) -> None:
    try:
        while True:
            # BufferedReader.read(size) may wait for the entire requested
            # amount while the attached MiMo client is still running. read1
            # returns the bytes already available, so session identifiers are
            # observable in time to abort a timed-out server turn.
            read1 = getattr(stream, "read1", None)
            chunk = (
                read1(65_536)
                if callable(read1)
                else stream.read(65_536)
            )
            if not chunk:
                return
            destination.append(chunk)
    except (OSError, ValueError):
        return


def _write_prompt(stream: Any, prompt: bytes) -> None:
    try:
        stream.write(prompt)
        stream.flush()
    except (BrokenPipeError, OSError, ValueError):
        pass
    finally:
        try:
            stream.close()
        except (OSError, ValueError):
            pass


def _process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_group(
    process: subprocess.Popen[bytes],
    *,
    grace_seconds: float = 2.0,
) -> None:
    process_group_id = process.pid
    group_signal_permitted = True
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError:
        # A short-lived leader can exit before cleanup and its pid may already
        # identify a process group that does not belong to this runtime. Never
        # signal that group. Fall back to the exact child process when it is
        # still alive.
        group_signal_permitted = False
        if process.poll() is None:
            try:
                process.terminate()
            except (OSError, ProcessLookupError):
                pass
    deadline = time.monotonic() + grace_seconds
    while (
        group_signal_permitted
        and _process_group_exists(process_group_id)
        and time.monotonic() < deadline
    ):
        if process.poll() is None:
            try:
                process.wait(timeout=0.05)
            except subprocess.TimeoutExpired:
                pass
        else:
            time.sleep(0.05)
    if group_signal_permitted and _process_group_exists(process_group_id):
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    if process.poll() is None:
        try:
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except (OSError, ProcessLookupError):
                pass
            try:
                process.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                pass


def _close_pipe(stream: Any) -> None:
    try:
        stream.close()
    except (OSError, ValueError):
        pass


def _available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _valid_session_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    if _SESSION_ID_PATTERN.fullmatch(value) is None:
        return None
    return value


def _validate_loopback_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise MimoDeveloperRuntimeError(
            "mimo_developer_server_url_invalid",
            "Адрес локального сервера MiMo Code недействителен.",
        ) from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or port is None
        or not 1 <= port <= 65_535
        or parsed.netloc != f"127.0.0.1:{port}"
    ):
        raise MimoDeveloperRuntimeError(
            "mimo_developer_server_url_invalid",
            "Адрес локального сервера MiMo Code недействителен.",
        )
    return f"http://127.0.0.1:{port}"


def _safe_environment(
    *,
    server_password: str,
    runtime_home: Path,
) -> dict[str, str]:
    data_home = runtime_home / ".local/share"
    config_home = runtime_home / ".config"
    cache_home = runtime_home / ".cache"
    state_home = runtime_home / ".local/state"
    environment = {
        "HOME": str(runtime_home),
        "PATH": os.getenv("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "LANG": os.getenv("LANG", "C.UTF-8"),
        "LC_ALL": os.getenv("LC_ALL", "C.UTF-8"),
        "NO_COLOR": "1",
        "MIMOCODE_SERVER_PASSWORD": server_password,
        "XDG_DATA_HOME": str(data_home),
        "XDG_CONFIG_HOME": str(config_home),
        "XDG_CACHE_HOME": str(cache_home),
        "XDG_STATE_HOME": str(state_home),
        "MIMOCODE_DISABLE_CLAUDE_IMPORT": "1",
        "MIMOCODE_DISABLE_MODELS_FETCH": "1",
        "MIMOCODE_MIMO_ONLY": "1",
        "MIMOCODE_ENABLE_ANALYSIS": "0",
    }
    for name in ("TMPDIR",):
        value = os.getenv(name)
        if value:
            environment[name] = value
    return environment


def _event_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _event_text(value: object, *, limit: int = 16_000) -> str:
    return str(value or "").strip()[:limit]


def _mimo_file_changes(
    *,
    tool_name: str,
    tool_input: dict[str, Any],
    state: dict[str, Any],
    metadata: dict[str, Any],
) -> list[dict[str, str]]:
    raw_path = next(
        (
            tool_input.get(key)
            for key in ("filePath", "filepath", "path", "file", "filename")
            if tool_input.get(key)
        ),
        None,
    )
    patch = _event_text(
        tool_input.get("patch")
        or tool_input.get("patchText")
        or tool_input.get("diff"),
        limit=64_000,
    )
    paths: list[str] = []
    if raw_path is not None:
        paths.append(_event_text(raw_path, limit=4_096))
    if patch:
        for match in _PATCH_FILE_PATTERN.finditer(patch):
            candidate = _event_text(match.group(1), limit=4_096)
            if candidate and candidate not in paths:
                paths.append(candidate)
    if not paths:
        return []

    diff = _event_text(
        metadata.get("diff")
        or state.get("diff")
        or patch,
        limit=64_000,
    )
    kind = {
        "write": "create",
        "edit": "update",
        "multiedit": "update",
        "patch": "update",
        "apply_patch": "update",
    }.get(tool_name, "update")
    return [
        {
            "path": path,
            "kind": kind,
            "diff": diff,
        }
        for path in paths[:40]
    ]


class _MimoEventBridge:
    """Translate MiMo's live SSE protocol into the shared agent callbacks."""

    def __init__(
        self,
        *,
        server_url: str,
        authorization_header: str,
        workspace_root: Path,
        session_id: str | None,
        session_title: str,
        on_delta: Callable[[str], None],
        on_activity: Callable[[str, dict[str, Any]], None],
    ) -> None:
        self._server_url = server_url
        self._authorization_header = authorization_header
        self._workspace_root = workspace_root
        self._target_session_id = session_id
        self._session_title = session_title
        self._on_delta = on_delta
        self._on_activity = on_activity
        self._ready = threading.Event()
        self._idle = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._response: Any | None = None
        self._state_lock = threading.Lock()
        self._assistant_message_ids: set[str] = set()
        self._part_types: dict[str, str] = {}
        self._part_text: dict[str, str] = {}
        self._started_tools: set[str] = set()
        self._completed_tools: set[str] = set()
        self._streamed_parts: list[str] = []
        self._callback_error: str | None = None
        self._connection_error: str | None = None

    @property
    def streamed_text(self) -> str:
        with self._state_lock:
            return "".join(self._streamed_parts)

    @property
    def callback_error(self) -> str | None:
        with self._state_lock:
            return self._callback_error

    @property
    def connection_error(self) -> str | None:
        with self._state_lock:
            return self._connection_error

    def start(self) -> bool:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._ready.wait(_EVENT_CONNECT_TIMEOUT_SECONDS):
            self.close()
            return False
        return self.connection_error is None

    def close(self, *, drain: bool = False) -> None:
        if drain:
            self._idle.wait(_EVENT_DRAIN_TIMEOUT_SECONDS)
        self._stop.set()
        response = self._response
        if response is not None:
            try:
                response.close()
            except (OSError, ValueError):
                pass
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)

    def _set_connection_error(self, message: str) -> None:
        with self._state_lock:
            self._connection_error = message

    def _set_callback_error(self, message: str) -> None:
        with self._state_lock:
            self._callback_error = message
        self._stop.set()

    def _emit_delta(self, delta: str) -> None:
        if not delta:
            return
        try:
            self._on_delta(delta)
        except Exception:
            self._set_callback_error(
                "Kolibri could not persist the streamed MiMo response."
            )
            return
        with self._state_lock:
            self._streamed_parts.append(delta)

    def _emit_activity(self, phase: str, item: dict[str, Any]) -> None:
        try:
            canonical = canonical_runtime_activity(phase, item)
            self._on_activity(phase, canonical)
        except Exception:
            self._set_callback_error(
                "Kolibri could not persist MiMo developer activity."
            )

    def _run(self) -> None:
        query = urlencode({"directory": str(self._workspace_root)})
        request = Request(
            f"{self._server_url}/event?{query}",
            method="GET",
            headers={
                "Accept": "text/event-stream",
                "Authorization": self._authorization_header,
            },
        )
        try:
            with urlopen(
                request,
                timeout=max(15.0, _EVENT_CONNECT_TIMEOUT_SECONDS),
            ) as response:
                self._response = response
                if (
                    response.status != 200
                    or response.headers.get_content_type()
                    != "text/event-stream"
                ):
                    self._set_connection_error(
                        "MiMo event stream returned an invalid response."
                    )
                    return
                self._ready.set()
                while not self._stop.is_set():
                    raw_line = response.readline(_EVENT_LINE_LIMIT + 1)
                    if not raw_line:
                        return
                    if len(raw_line) > _EVENT_LINE_LIMIT:
                        self._set_connection_error(
                            "MiMo event stream exceeded the line limit."
                        )
                        return
                    if not raw_line.startswith(b"data:"):
                        continue
                    try:
                        event = json.loads(
                            raw_line[5:].strip().decode("utf-8", "strict")
                        )
                    except (UnicodeDecodeError, ValueError, TypeError):
                        continue
                    if isinstance(event, dict):
                        self._handle_event(event)
        except (
            AttributeError,
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            ValueError,
        ) as exc:
            if not self._stop.is_set():
                self._set_connection_error(type(exc).__name__)
        finally:
            self._response = None
            self._ready.set()

    def _select_session(
        self,
        event_type: str,
        properties: dict[str, Any],
    ) -> None:
        if self._target_session_id is not None:
            return
        if event_type != "session.created":
            return
        info = properties.get("info")
        if not isinstance(info, dict):
            return
        if (
            info.get("title") != self._session_title
            or info.get("directory") != str(self._workspace_root)
        ):
            return
        self._target_session_id = _valid_session_id(info.get("id"))

    def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        properties = event.get("properties")
        if not isinstance(event_type, str) or not isinstance(properties, dict):
            return
        self._select_session(event_type, properties)
        session_id = _valid_session_id(properties.get("sessionID"))
        if (
            self._target_session_id is None
            or session_id != self._target_session_id
        ):
            return

        if event_type == "message.updated":
            info = properties.get("info")
            if (
                isinstance(info, dict)
                and info.get("role") == "assistant"
                and isinstance(info.get("id"), str)
            ):
                self._assistant_message_ids.add(str(info["id"]))
            return
        if event_type == "message.part.updated":
            part = properties.get("part")
            if isinstance(part, dict):
                self._handle_part_updated(part)
            return
        if event_type == "message.part.delta":
            self._handle_part_delta(properties)
            return
        if event_type == "session.status":
            status = properties.get("status")
            if isinstance(status, dict) and status.get("type") == "idle":
                self._idle.set()

    def _handle_part_updated(self, part: dict[str, Any]) -> None:
        part_id = part.get("id")
        message_id = part.get("messageID")
        part_type = part.get("type")
        if (
            not isinstance(part_id, str)
            or not isinstance(message_id, str)
            or not isinstance(part_type, str)
        ):
            return
        self._part_types[part_id] = part_type
        if message_id not in self._assistant_message_ids:
            return
        if part_type == "text":
            text = part.get("text")
            if not isinstance(text, str):
                return
            previous = self._part_text.get(part_id, "")
            if text.startswith(previous):
                self._emit_delta(text[len(previous) :])
            self._part_text[part_id] = text
            return
        if part_type == "tool":
            self._handle_tool_part(part)

    def _handle_part_delta(self, properties: dict[str, Any]) -> None:
        message_id = properties.get("messageID")
        part_id = properties.get("partID")
        delta = properties.get("delta")
        if (
            message_id not in self._assistant_message_ids
            or not isinstance(part_id, str)
            or self._part_types.get(part_id) != "text"
            or properties.get("field") != "text"
            or not isinstance(delta, str)
        ):
            return
        self._part_text[part_id] = self._part_text.get(part_id, "") + delta
        self._emit_delta(delta)

    @staticmethod
    def _activity_id(part_id: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", part_id)[:120]
        return f"mimo-tool-{safe}"

    def _handle_tool_part(self, part: dict[str, Any]) -> None:
        part_id = part.get("id")
        state = part.get("state")
        if not isinstance(part_id, str) or not isinstance(state, dict):
            return
        activity_id = self._activity_id(part_id)
        status = str(state.get("status") or "")
        tool_input = (
            state["input"] if isinstance(state.get("input"), dict) else {}
        )
        metadata = (
            state["metadata"]
            if isinstance(state.get("metadata"), dict)
            else {}
        )
        tool_name = _event_text(part.get("tool"), limit=80) or "tool"
        file_changes = (
            _mimo_file_changes(
                tool_name=tool_name.lower(),
                tool_input=tool_input,
                state=state,
                metadata=metadata,
            )
            if tool_name.lower() in _FILE_TOOL_NAMES
            else []
        )
        command = (
            _event_text(tool_input.get("command"))
            or _event_text(state.get("title"), limit=800)
            or tool_name
        )
        timing = state["time"] if isinstance(state.get("time"), dict) else {}
        started_at = _event_int(timing.get("start"))
        ended_at = _event_int(timing.get("end"))
        item: dict[str, Any] = {
            "id": activity_id,
            "type": "fileChange" if file_changes else "commandExecution",
            "status": "inProgress",
        }
        if file_changes:
            item["changes"] = [
                {
                    "path": change["path"],
                    "kind": change["kind"],
                    "diff": "",
                }
                for change in file_changes
            ]
        else:
            item.update(
                {
                    "command": command,
                    "cwd": str(self._workspace_root),
                }
            )
        if activity_id not in self._started_tools:
            self._started_tools.add(activity_id)
            self._emit_activity("started", dict(item))
        if (
            status not in _TERMINAL_TOOL_STATES
            or activity_id in self._completed_tools
        ):
            return
        self._completed_tools.add(activity_id)
        item["status"] = (
            "completed" if status == "completed" else "failed"
        )
        if file_changes:
            item["changes"] = file_changes
        else:
            item.update(
                {
                    "exitCode": _event_int(
                        metadata.get("exit")
                        if "exit" in metadata
                        else metadata.get("exitCode")
                    ),
                    "durationMs": (
                        ended_at - started_at
                        if started_at is not None
                        and ended_at is not None
                        and ended_at >= started_at
                        else None
                    ),
                    "output": _event_text(
                        state.get("output") or metadata.get("output")
                    ),
                }
            )
        self._emit_activity("completed", item)


class MimoDeveloperServerRuntime:
    """One MiMo server with durable sessions keyed by product chat thread."""

    def __init__(
        self,
        *,
        runtime_root: Path | None = None,
        command_prefix: Sequence[str] | None = None,
        port: int | None = None,
        startup_timeout_seconds: float = 15.0,
        attached_url: str | None = None,
        attached_password: str | None = None,
        auth_file: Path | None = None,
    ) -> None:
        if attached_url is not None:
            attached_url = _validate_loopback_url(attached_url)
            if (
                not attached_password
                or len(attached_password) > 1024
                or "\x00" in attached_password
            ):
                raise MimoDeveloperRuntimeError(
                    "mimo_developer_server_auth_invalid",
                    "Доступ к локальному серверу MiMo Code не настроен.",
                )
        if port is not None and not 1 <= port <= 65_535:
            raise MimoDeveloperRuntimeError(
                "mimo_developer_server_url_invalid",
                "Порт локального сервера MiMo Code недействителен.",
            )
        if startup_timeout_seconds <= 0:
            raise MimoDeveloperRuntimeError(
                "mimo_developer_timeout_invalid",
                "Таймаут запуска MiMo Code недействителен.",
            )
        if runtime_root is None and attached_url is None:
            raise MimoDeveloperRuntimeError(
                "mimo_developer_runtime_root_invalid",
                "Рабочее хранилище MiMo Code не настроено.",
            )
        self._temporary_runtime_root: (
            tempfile.TemporaryDirectory[str] | None
        ) = None
        if runtime_root is None:
            self._temporary_runtime_root = tempfile.TemporaryDirectory(
                prefix="kolibri-mimo-attached-",
            )
            runtime_root = Path(self._temporary_runtime_root.name)
        self._runtime_root = runtime_root.resolve()
        if self._runtime_root in {Path("/"), Path.home().resolve()}:
            raise MimoDeveloperRuntimeError(
                "mimo_developer_runtime_root_invalid",
                "Рабочее хранилище MiMo Code настроено неверно.",
            )
        self._runtime_home = self._runtime_root / "home"
        configured_auth_file = os.getenv(
            "KOLIBRI_V3_MIMO_AUTH_FILE",
            "",
        ).strip()
        selected_auth_file = (
            auth_file
            if auth_file is not None
            else (
                Path(configured_auth_file)
                if configured_auth_file
                else Path.home()
                / ".local/share/mimocode/auth.json"
            )
        )
        if not selected_auth_file.is_absolute():
            raise MimoDeveloperRuntimeError(
                "mimo_developer_auth_file_invalid",
                "Хранилище входа MiMo Code настроено неверно.",
            )
        self._auth_file = selected_auth_file
        configured = os.getenv("KOLIBRI_V3_MIMO_CLI_PATH", "").strip()
        executable = (
            Path(configured)
            if configured
            else Path.home() / ".mimocode/bin/mimo"
        )
        self._command_prefix = tuple(
            command_prefix or (str(executable),)
        )
        if (
            not self._command_prefix
            or any(
                not isinstance(part, str) or not part
                for part in self._command_prefix
            )
        ):
            raise MimoDeveloperRuntimeError(
                "mimo_developer_cli_unavailable",
                "Команда запуска MiMo Code недействительна.",
            )
        self._configured_port = port
        self._startup_timeout_seconds = startup_timeout_seconds
        self._attached_url = attached_url
        self._server_password = (
            attached_password or secrets.token_urlsafe(32)
        )
        self._server_process: subprocess.Popen[bytes] | None = None
        self._server_url: str | None = attached_url
        self._server_readers: tuple[threading.Thread, ...] = ()
        self._server_stdout = _ByteBuffer(
            limit=_SERVER_LOG_TAIL_LIMIT,
            rolling=True,
        )
        self._server_stderr = _ByteBuffer(
            limit=_SERVER_LOG_TAIL_LIMIT,
            rolling=True,
        )
        self._lifecycle_lock = threading.RLock()
        self._session_lock = threading.Lock()
        self._sessions: dict[str, str] = {}
        self._thread_locks: dict[str, threading.Lock] = {}
        self._stats_lock = threading.Lock()
        self._server_starts = 0
        self._turns_started = 0
        self._turns_active = 0
        self._turns_completed = 0
        self._turns_failed = 0

    @property
    def server_url(self) -> str | None:
        return self._server_url

    def inspect(self) -> dict[str, Any]:
        """Return a secret-free runtime snapshot for superadmin diagnostics."""

        process = self._server_process
        with self._session_lock:
            sessions = dict(self._sessions)
        with self._stats_lock:
            stats = {
                "server_starts": self._server_starts,
                "turns_started": self._turns_started,
                "turns_active": self._turns_active,
                "turns_completed": self._turns_completed,
                "turns_failed": self._turns_failed,
            }
        return {
            "server_url": self._server_url,
            "server_pid": process.pid if process is not None else None,
            "server_process_running": (
                process is not None and process.poll() is None
            ),
            "attached": self._attached_url is not None,
            **stats,
            "session_count": len(sessions),
            "sessions": sessions,
        }

    @staticmethod
    def _ensure_private_directory(path: Path) -> None:
        try:
            path.mkdir(mode=0o700, exist_ok=True)
            metadata = os.lstat(path)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or path.resolve(strict=True) != path
            ):
                raise OSError("unsafe runtime directory")
            os.chmod(path, 0o700)
        except OSError as exc:
            raise MimoDeveloperRuntimeError(
                "mimo_developer_runtime_root_invalid",
                "Рабочее хранилище MiMo Code недоступно.",
            ) from exc

    def _copy_auth_file(self, destination: Path) -> None:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            source_fd = os.open(self._auth_file, flags)
        except FileNotFoundError as exc:
            raise MimoDeveloperRuntimeError(
                "mimo_developer_login_required",
                "Войдите в MiMo Code перед запуском агента.",
            ) from exc
        except OSError as exc:
            raise MimoDeveloperRuntimeError(
                "mimo_developer_auth_file_invalid",
                "Хранилище входа MiMo Code недоступно.",
            ) from exc
        temporary = destination.with_name(
            f".auth.{secrets.token_hex(12)}.tmp",
        )
        destination_fd: int | None = None
        try:
            source_metadata = os.fstat(source_fd)
            if (
                not stat.S_ISREG(source_metadata.st_mode)
                or source_metadata.st_size <= 0
                or source_metadata.st_size > _AUTH_FILE_LIMIT
                or stat.S_IMODE(source_metadata.st_mode) & 0o077
                or source_metadata.st_nlink != 1
                or (
                    hasattr(os, "getuid")
                    and source_metadata.st_uid != os.getuid()
                )
            ):
                raise MimoDeveloperRuntimeError(
                    "mimo_developer_auth_file_invalid",
                    "Хранилище входа MiMo Code небезопасно.",
                )
            destination_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                destination_flags |= os.O_NOFOLLOW
            destination_fd = os.open(
                temporary,
                destination_flags,
                0o600,
            )
            total = 0
            while True:
                chunk = os.read(source_fd, 65_536)
                if not chunk:
                    break
                total += len(chunk)
                if total > _AUTH_FILE_LIMIT:
                    raise MimoDeveloperRuntimeError(
                        "mimo_developer_auth_file_invalid",
                        "Хранилище входа MiMo Code слишком велико.",
                    )
                view = memoryview(chunk)
                while view:
                    written = os.write(destination_fd, view)
                    view = view[written:]
            current_metadata = os.fstat(source_fd)
            if (
                total != source_metadata.st_size
                or current_metadata.st_size != source_metadata.st_size
                or current_metadata.st_mtime_ns
                != source_metadata.st_mtime_ns
            ):
                raise MimoDeveloperRuntimeError(
                    "mimo_developer_auth_file_invalid",
                    "Хранилище входа MiMo Code изменилось при запуске.",
                )
            os.fchmod(destination_fd, 0o600)
            os.fsync(destination_fd)
            os.close(destination_fd)
            destination_fd = None
            os.replace(temporary, destination)
            os.chmod(destination, 0o600)
            directory_fd = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except MimoDeveloperRuntimeError:
            raise
        except OSError as exc:
            raise MimoDeveloperRuntimeError(
                "mimo_developer_auth_file_invalid",
                "Не удалось подготовить вход MiMo Code.",
            ) from exc
        finally:
            os.close(source_fd)
            if destination_fd is not None:
                os.close(destination_fd)
            try:
                temporary.unlink()
            except OSError:
                pass

    def _prepare_runtime_home(self) -> None:
        paths = (
            self._runtime_root,
            self._runtime_home,
            self._runtime_home / ".local",
            self._runtime_home / ".local/share",
            self._runtime_home / ".local/share/mimocode",
            self._runtime_home / ".local/state",
            self._runtime_home / ".config",
            self._runtime_home / ".cache",
        )
        for path in paths:
            self._ensure_private_directory(path)
        self._copy_auth_file(
            self._runtime_home
            / ".local/share/mimocode/auth.json",
        )

    def _executable(self) -> Path:
        executable = Path(self._command_prefix[0])
        if (
            not executable.is_absolute()
            or not executable.is_file()
            or not os.access(executable, os.X_OK)
        ):
            raise MimoDeveloperRuntimeError(
                "mimo_developer_cli_unavailable",
                "Локальный MiMo Code CLI недоступен.",
            )
        return executable

    def _authorization_header(self) -> str:
        credentials = base64.b64encode(
            f"mimocode:{self._server_password}".encode("utf-8"),
        ).decode("ascii")
        return f"Basic {credentials}"

    def _request_json(
        self,
        path: str,
        *,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        timeout: float = 3.0,
    ) -> Any:
        server_url = self._server_url
        if server_url is None:
            raise MimoDeveloperRuntimeError(
                "mimo_developer_server_unavailable",
                "Локальный сервер MiMo Code недоступен.",
            )
        payload = (
            json.dumps(
                body,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            if body is not None
            else None
        )
        request = Request(
            f"{server_url}{path}",
            data=payload,
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": self._authorization_header(),
                **(
                    {"Content-Type": "application/json"}
                    if payload is not None
                    else {}
                ),
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise MimoDeveloperRuntimeError(
                "mimo_developer_server_unavailable",
                "Локальный сервер MiMo Code недоступен.",
            ) from exc
        if len(raw) > 2 * 1024 * 1024:
            raise MimoDeveloperRuntimeError(
                "mimo_developer_server_invalid",
                "Локальный сервер MiMo Code вернул слишком большой ответ.",
            )
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise MimoDeveloperRuntimeError(
                "mimo_developer_server_invalid",
                "Локальный сервер MiMo Code вернул неверный ответ.",
            ) from exc

    def _server_is_healthy(self) -> bool:
        try:
            payload = self._request_json(
                "/global/health",
                timeout=0.5,
            )
        except MimoDeveloperRuntimeError:
            return False
        if not isinstance(payload, dict) or payload.get("healthy") is not True:
            return False
        version = payload.get("version")
        return (
            isinstance(version, str)
            and re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", version)
            is not None
        )

    def _cleanup_server_process(self) -> None:
        process = self._server_process
        if process is not None:
            _terminate_process_group(process)
            if process.stdout is not None:
                _close_pipe(process.stdout)
            if process.stderr is not None:
                _close_pipe(process.stderr)
        for reader in self._server_readers:
            reader.join(timeout=2)
        self._server_process = None
        self._server_readers = ()
        if self._attached_url is None:
            self._server_url = None

    def start(self) -> None:
        with self._lifecycle_lock:
            self._prepare_runtime_home()
            if self._attached_url is not None:
                self._server_url = self._attached_url
                if not self._server_is_healthy():
                    raise MimoDeveloperRuntimeError(
                        "mimo_developer_server_unavailable",
                        "Локальный сервер MiMo Code недоступен.",
                    )
                return
            if (
                self._server_process is not None
                and self._server_process.poll() is None
                and self._server_is_healthy()
            ):
                return
            self._cleanup_server_process()
            self._executable()
            attempts = 1 if self._configured_port is not None else 3
            last_error: MimoDeveloperRuntimeError | None = None
            for _attempt in range(attempts):
                port = self._configured_port or _available_loopback_port()
                server_url = f"http://127.0.0.1:{port}"
                command = [
                    *self._command_prefix,
                    "serve",
                    "--pure",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ]
                try:
                    process = subprocess.Popen(
                        command,
                        env=_safe_environment(
                            server_password=self._server_password,
                            runtime_home=self._runtime_home,
                        ),
                        cwd=self._runtime_root,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        start_new_session=True,
                    )
                except OSError as exc:
                    raise MimoDeveloperRuntimeError(
                        "mimo_developer_cli_unavailable",
                        "Локальный сервер MiMo Code не запускается.",
                    ) from exc
                assert process.stdout is not None
                assert process.stderr is not None
                self._server_process = process
                self._server_url = server_url
                self._server_stdout = _ByteBuffer(
                    limit=_SERVER_LOG_TAIL_LIMIT,
                    rolling=True,
                )
                self._server_stderr = _ByteBuffer(
                    limit=_SERVER_LOG_TAIL_LIMIT,
                    rolling=True,
                )
                self._server_readers = (
                    threading.Thread(
                        target=_read_stream,
                        args=(process.stdout, self._server_stdout),
                        daemon=True,
                    ),
                    threading.Thread(
                        target=_read_stream,
                        args=(process.stderr, self._server_stderr),
                        daemon=True,
                    ),
                )
                for reader in self._server_readers:
                    reader.start()
                deadline = (
                    time.monotonic() + self._startup_timeout_seconds
                )
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    if self._server_is_healthy():
                        with self._stats_lock:
                            self._server_starts += 1
                        return
                    time.sleep(0.05)
                last_error = MimoDeveloperRuntimeError(
                    "mimo_developer_server_unavailable",
                    "Локальный сервер MiMo Code не запустился.",
                )
                self._cleanup_server_process()
            assert last_error is not None
            raise last_error

    def close(self) -> None:
        with self._lifecycle_lock:
            if self._attached_url is None:
                self._cleanup_server_process()
            temporary_runtime_root = self._temporary_runtime_root
            self._temporary_runtime_root = None
            if temporary_runtime_root is not None:
                temporary_runtime_root.cleanup()

    def _ensure_started(self) -> None:
        self.start()

    def _thread_lock(self, conversation_key: str) -> threading.Lock:
        with self._session_lock:
            return self._thread_locks.setdefault(
                conversation_key,
                threading.Lock(),
            )

    @staticmethod
    def _session_title(conversation_key: str) -> str:
        digest = hashlib.sha256(
            conversation_key.encode("utf-8", "strict"),
        ).hexdigest()
        return f"kolibri-thread-{digest[:40]}"

    def _discover_session(
        self,
        *,
        conversation_key: str,
        workspace_root: Path,
    ) -> str | None:
        with self._session_lock:
            cached = self._sessions.get(conversation_key)
        query = urlencode({"directory": str(workspace_root)})
        payload = self._request_json(f"/session?{query}")
        if not isinstance(payload, list):
            raise MimoDeveloperRuntimeError(
                "mimo_developer_server_invalid",
                "Локальный сервер MiMo Code вернул неверный список сессий.",
            )
        available_ids = {
            session_id
            for item in payload
            if isinstance(item, dict)
            and (
                session_id := _valid_session_id(item.get("id"))
            )
            is not None
        }
        if cached in available_ids:
            return cached
        title = self._session_title(conversation_key)
        candidates = [
            item
            for item in payload
            if isinstance(item, dict)
            and item.get("title") == title
            and item.get("directory") == str(workspace_root)
            and _valid_session_id(item.get("id")) is not None
        ]
        if not candidates:
            with self._session_lock:
                self._sessions.pop(conversation_key, None)
            return None
        candidates.sort(
            key=lambda item: (
                int(
                    item.get("time", {}).get("updated", 0)
                    if isinstance(item.get("time"), dict)
                    else 0
                ),
                str(item["id"]),
            ),
            reverse=True,
        )
        session_id = _valid_session_id(candidates[0]["id"])
        assert session_id is not None
        with self._session_lock:
            self._sessions[conversation_key] = session_id
        return session_id

    def _abort_session(
        self,
        *,
        session_id: str | None,
        workspace_root: Path,
    ) -> None:
        session_id = _valid_session_id(session_id)
        if session_id is None:
            return
        query = urlencode({"directory": str(workspace_root)})
        try:
            self._request_json(
                f"/session/{session_id}/abort?{query}",
                method="POST",
                timeout=2,
            )
        except MimoDeveloperRuntimeError:
            pass

    def _run_client(
        self,
        *,
        workspace_root: Path,
        prompt: str,
        run_id: str,
        conversation_key: str,
        session_id: str | None,
        timeout: float,
        access_mode: str,
        on_delta: Callable[[str], None],
        on_activity: Callable[[str, dict[str, Any]], None],
        cancellation_signal: threading.Event | None = None,
    ) -> _ParsedClientOutput:
        server_url = self._server_url
        assert server_url is not None
        session_title = self._session_title(conversation_key)
        command = [
            *self._command_prefix,
            "run",
            "--pure",
            "--format",
            "json",
            "--attach",
            server_url,
            "--dir",
            str(workspace_root),
        ]
        model = os.getenv(
            "KOLIBRI_V3_MIMO_DEVELOPER_MODEL",
            "xiaomi-token-plan-sgp/mimo-v2.5-pro",
        ).strip()
        if model:
            command.extend(("--model", model))
        if session_id is None:
            command.extend(
                ("--title", session_title),
            )
        else:
            command.extend(("--session", session_id))
        if access_mode == "full":
            # The attach client handles permission.asked events for this turn
            # and replies "once"; the long-lived server is never globally
            # placed in bypass mode.
            command.append("--dangerously-skip-permissions")
        started_at = time.monotonic()
        event_bridge = _MimoEventBridge(
            server_url=server_url,
            authorization_header=self._authorization_header(),
            workspace_root=workspace_root,
            session_id=session_id,
            session_title=session_title,
            on_delta=on_delta,
            on_activity=on_activity,
        )
        event_bridge.start()
        try:
            process = subprocess.Popen(
                command,
                cwd=workspace_root,
                env=_safe_environment(
                    server_password=self._server_password,
                    runtime_home=self._runtime_home,
                ),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as exc:
            event_bridge.close()
            raise MimoDeveloperRuntimeError(
                "mimo_developer_cli_unavailable",
                "Локальный клиент MiMo Code не запускается.",
            ) from exc
        stdout = _ByteBuffer(limit=_CLIENT_STDOUT_LIMIT)
        stderr = _ByteBuffer(limit=_CLIENT_STDERR_LIMIT)
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        readers = (
            threading.Thread(
                target=_read_stream,
                args=(process.stdout, stdout),
                daemon=True,
            ),
            threading.Thread(
                target=_read_stream,
                args=(process.stderr, stderr),
                daemon=True,
            ),
        )
        writer = threading.Thread(
            target=_write_prompt,
            args=(process.stdin, prompt.encode("utf-8", "strict")),
            daemon=True,
        )
        for worker in (*readers, writer):
            worker.start()
        deadline = started_at + timeout
        failure_code: str | None = None
        while process.poll() is None:
            if (
                cancellation_signal is not None
                and cancellation_signal.is_set()
            ):
                failure_code = "mimo_developer_cancelled"
                break
            if stdout.overflow.is_set() or stderr.overflow.is_set():
                failure_code = "mimo_developer_output_limit"
                break
            if time.monotonic() >= deadline:
                failure_code = "mimo_developer_timeout"
                break
            stdout.overflow.wait(timeout=0.05)
        partial = _parse_client_output(stdout.bytes())
        if failure_code is not None:
            self._abort_session(
                session_id=partial.session_id or session_id,
                workspace_root=workspace_root,
            )
            _terminate_process_group(process)
        writer.join(timeout=2)
        for reader in readers:
            reader.join(timeout=2)
        if writer.is_alive() or any(reader.is_alive() for reader in readers):
            self._abort_session(
                session_id=partial.session_id or session_id,
                workspace_root=workspace_root,
            )
            _terminate_process_group(process)
            _close_pipe(process.stdin)
            _close_pipe(process.stdout)
            _close_pipe(process.stderr)
            writer.join(timeout=1)
            for reader in readers:
                reader.join(timeout=1)
            if failure_code is None:
                failure_code = "mimo_developer_process_leaked"
        if (
            (stdout.overflow.is_set() or stderr.overflow.is_set())
            and failure_code is None
        ):
            failure_code = "mimo_developer_output_limit"
        return_code = process.poll()
        event_bridge.close(
            drain=failure_code is None and return_code == 0,
        )
        if event_bridge.callback_error is not None and failure_code is None:
            failure_code = "mimo_developer_stream_persist_failed"
        if failure_code == "mimo_developer_output_limit":
            raise MimoDeveloperRuntimeError(
                failure_code,
                "MiMo Code превысил допустимый размер вывода.",
            )
        if failure_code == "mimo_developer_timeout":
            raise MimoDeveloperRuntimeError(
                failure_code,
                "MiMo Code не завершил задачу вовремя.",
            )
        if failure_code == "mimo_developer_cancelled":
            raise MimoDeveloperRuntimeError(
                failure_code,
                "Задача MiMo Code остановлена пользователем.",
            )
        if failure_code == "mimo_developer_process_leaked":
            raise MimoDeveloperRuntimeError(
                failure_code,
                "Процесс MiMo Code не завершился корректно.",
            )
        if failure_code == "mimo_developer_stream_persist_failed":
            raise MimoDeveloperRuntimeError(
                failure_code,
                "Не удалось сохранить поток выполнения MiMo Code.",
            )
        if return_code != 0:
            raise MimoDeveloperRuntimeError(
                "mimo_developer_failed",
                "MiMo Code не завершил задачу.",
            )
        parsed = _parse_client_output(stdout.bytes())
        streamed_text = event_bridge.streamed_text
        return _ParsedClientOutput(
            text=parsed.text or streamed_text.strip(),
            session_id=parsed.session_id,
            error_message=parsed.error_message,
            streamed_text=streamed_text,
        )

    def complete(
        self,
        *,
        workspace_root: Path,
        prompt: str,
        run_id: str,
        conversation_key: str,
        timeout: float,
        access_mode: str,
        on_delta: Callable[[str], None],
        on_activity: Callable[[str, dict[str, Any]], None],
        cancellation_signal: threading.Event | None = None,
    ) -> MimoDeveloperResult:
        resolved_workspace = workspace_root.resolve()
        if (
            not resolved_workspace.is_absolute()
            or not resolved_workspace.is_dir()
        ):
            raise MimoDeveloperRuntimeError(
                "mimo_developer_workspace_invalid",
                "Рабочая папка MiMo Code недоступна.",
            )
        if access_mode not in {"auto", "full"}:
            raise MimoDeveloperRuntimeError(
                "mimo_developer_access_invalid",
                "Режим доступа MiMo Code недействителен.",
            )
        if not prompt.strip() or len(prompt) > _PROMPT_LIMIT:
            raise MimoDeveloperRuntimeError(
                "mimo_developer_prompt_invalid",
                "Задача MiMo Code имеет неверный размер.",
            )
        if (
            not conversation_key
            or len(conversation_key) > 512
            or "\x00" in conversation_key
        ):
            raise MimoDeveloperRuntimeError(
                "mimo_developer_session_invalid",
                "Контекст сессии MiMo Code недействителен.",
            )
        self._executable()
        self._ensure_started()
        with self._thread_lock(conversation_key):
            with self._stats_lock:
                self._turns_started += 1
                self._turns_active += 1
            try:
                session_id = self._discover_session(
                    conversation_key=conversation_key,
                    workspace_root=resolved_workspace,
                )
                parsed = self._run_client(
                    workspace_root=resolved_workspace,
                    prompt=prompt,
                    run_id=run_id,
                    conversation_key=conversation_key,
                    session_id=session_id,
                    timeout=timeout,
                    access_mode=access_mode,
                    on_delta=on_delta,
                    on_activity=on_activity,
                    cancellation_signal=cancellation_signal,
                )
                resolved_session_id = parsed.session_id or session_id
                if resolved_session_id is None:
                    raise MimoDeveloperRuntimeError(
                        "mimo_developer_session_missing",
                        "MiMo Code не вернул идентификатор сессии.",
                    )
                with self._session_lock:
                    self._sessions[conversation_key] = (
                        resolved_session_id
                    )
                if parsed.error_message is not None:
                    raise MimoDeveloperRuntimeError(
                        "mimo_developer_failed",
                        "MiMo Code не завершил задачу.",
                    )
                if not parsed.text:
                    raise MimoDeveloperRuntimeError(
                        "mimo_developer_response_empty",
                        "MiMo Code завершился без итогового ответа.",
                    )
                if not parsed.streamed_text:
                    on_delta(parsed.text)
                result = MimoDeveloperResult(
                    text=parsed.text,
                    session_id=resolved_session_id,
                )
            except Exception:
                with self._stats_lock:
                    self._turns_active -= 1
                    self._turns_failed += 1
                raise
            with self._stats_lock:
                self._turns_active -= 1
                self._turns_completed += 1
            return result


# Kept as a compatibility alias for existing imports while the runtime changes
# from one process per turn to one persistent server per backend lifespan.
MimoDeveloperCliRuntime = MimoDeveloperServerRuntime
