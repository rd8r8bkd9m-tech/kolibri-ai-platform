"""Direct DeepSeek Responses-API developer agent (no Codex CLI required).

The Codex CLI app-server is one possible transport for the owner-facing
developer mode.  DeepSeek's own Responses-compatible endpoint natively
supports parallel function calling, so the same developer loop (bash, file
read/write, glob, grep) can run directly from the Kolibri backend.  That
removes the local CLI dependency and works on any server that can reach the
DeepSeek API.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Mapping

import httpx

from .agent_runtime import (
    AgentRuntimeError,
    AgentRuntimeRequest,
    AgentRuntimeResult,
)
from .config import Settings


LOGGER = logging.getLogger(__name__)

def _developer_agent_iteration_limit() -> int:
    raw = os.environ.get("KOLIBRI_V3_DEVELOPER_AGENT_MAX_ITERATIONS", "40")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 40
    return min(200, max(1, value))


MAX_AGENT_ITERATIONS = _developer_agent_iteration_limit()
MAX_TOOL_OUTPUT_CHARS = 60_000
MAX_READ_BYTES = 256 * 1024
MAX_GLOB_RESULTS = 200
MAX_GREP_LINES = 200
BASH_TIMEOUT_SECONDS = 30.0
HTTP_TIMEOUT_SECONDS = 120.0

_SENSITIVE_ACTIVITY = re.compile(
    r"(?i)(authorization:\s*bearer\s+\S+|"
    r"(?:api[_-]?key|token|password|secret)\s*[=:]\s*\S+|"
    r"sk-[A-Za-z0-9_-]{12,})"
)
_SENSITIVE_PATH_PART = re.compile(
    r"(?i)(^|[/.])(?:\.env(?:\.|$)|\.ssh(?:/|$)|"
    r"credentials?(?:[./_-]|$)|secrets?(?:[./_-]|$)|"
    r"tokens?(?:[./_-]|$))"
)


def _redact(value: object, *, limit: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return _SENSITIVE_ACTIVITY.sub("[REDACTED]", text)[:limit]


def _tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": "bash",
            "description": (
                "Run a shell command inside the workspace. Prefer safe, "
                "scoped commands; the environment is a real macOS/Linux shell."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute.",
                    },
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "read_file",
            "description": "Read a UTF-8 text file inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path inside the workspace.",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "write_file",
            "description": "Create or overwrite a UTF-8 text file inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path inside the workspace.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file content to write.",
                    },
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "glob",
            "description": "List files inside the workspace matching a glob pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern, e.g. **/*.py.",
                    },
                },
                "required": ["pattern"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "grep",
            "description": "Search file contents inside the workspace with a regex.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regular expression to search for.",
                    },
                    "path": {
                        "type": "string",
                        "description": (
                            "Optional relative path; when omitted the whole "
                            "workspace is searched."
                        ),
                    },
                },
                "required": ["pattern"],
                "additionalProperties": False,
            },
        },
    ]


def _resolve_workspace_path(
    workspace: Path,
    value: object,
) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("path is required")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ValueError("path escapes the workspace") from exc
    return resolved


def _emit_activity(
    callback: Callable[[str, dict[str, Any]], None] | None,
    *,
    phase: str,
    item: dict[str, Any],
) -> None:
    if callback is None:
        return
    try:
        callback(phase, item)
    except Exception:
        LOGGER.exception("developer activity callback failed")


def _run_bash(
    workspace: Path,
    arguments: Mapping[str, Any],
    timeout: float,
    *,
    item_id: str,
    on_activity: Callable[[str, dict[str, Any]], None] | None,
) -> str:
    command = str(arguments.get("command") or "").strip()
    if not command:
        return _redact({"error": "command is required"}, limit=2_000)
    started_at = time.monotonic()
    _emit_activity(
        on_activity,
        phase="started",
        item={
            "id": item_id,
            "type": "commandExecution",
            "command": command,
            "cwd": str(workspace),
        },
    )
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = _redact(exc.output, limit=20_000)
        payload = {
            "status": "timeout",
            "exitCode": None,
            "durationMs": int((time.monotonic() - started_at) * 1000),
            "output": f"Команда превысила таймаут {int(timeout)} с.\n{output}",
        }
        _emit_activity(
            on_activity,
            phase="completed",
            item={
                "id": item_id,
                "type": "commandExecution",
                "command": command,
                "cwd": str(workspace),
                **payload,
            },
        )
        return _redact(payload, limit=20_000)
    except OSError as exc:
        payload = {"status": "error", "output": f"Не удалось запустить команду: {exc}"}
        _emit_activity(
            on_activity,
            phase="completed",
            item={
                "id": item_id,
                "type": "commandExecution",
                "command": command,
                "cwd": str(workspace),
                **payload,
            },
        )
        return _redact(payload, limit=2_000)
    aggregated = "\n".join(
        part
        for part in (completed.stdout, completed.stderr)
        if part and part.strip()
    )
    payload = {
        "status": "completed" if completed.returncode == 0 else "failed",
        "exitCode": completed.returncode,
        "durationMs": int((time.monotonic() - started_at) * 1000),
        "output": _redact(aggregated, limit=40_000),
    }
    _emit_activity(
        on_activity,
        phase="completed",
        item={
            "id": item_id,
            "type": "commandExecution",
            "command": command,
            "cwd": str(workspace),
            **payload,
        },
    )
    return _redact(payload, limit=40_000)


def _run_read_file(
    workspace: Path,
    arguments: Mapping[str, Any],
    *,
    timeout: float = BASH_TIMEOUT_SECONDS,
    item_id: str,
    on_activity: Callable[[str, dict[str, Any]], None] | None,
) -> str:
    try:
        path = _resolve_workspace_path(workspace, arguments.get("path"))
    except ValueError as exc:
        return _redact({"error": str(exc)}, limit=2_000)
    _emit_activity(
        on_activity,
        phase="started",
        item={
            "id": item_id,
            "type": "fileChange",
            "changes": [{"path": str(path), "kind": "read"}],
        },
    )
    try:
        if not path.is_file():
            return _redact({"error": f"файл не найден: {path}"}, limit=2_000)
        if path.stat().st_size > MAX_READ_BYTES:
            return _redact(
                {"error": f"файл больше {MAX_READ_BYTES} байт: {path}"},
                limit=2_000,
            )
        text = path.read_text(encoding="utf-8", errors="replace")
        payload = {"path": str(path), "content": _redact(text, limit=80_000)}
        _emit_activity(
            on_activity,
            phase="completed",
            item={
                "id": item_id,
                "type": "fileChange",
                "changes": [{"path": str(path), "kind": "read"}],
            },
        )
        return _redact(payload, limit=80_000)
    except OSError as exc:
        return _redact({"error": f"не удалось прочитать файл: {exc}"}, limit=2_000)


def _run_write_file(
    workspace: Path,
    arguments: Mapping[str, Any],
    *,
    timeout: float = BASH_TIMEOUT_SECONDS,
    item_id: str,
    on_activity: Callable[[str, dict[str, Any]], None] | None,
) -> str:
    try:
        path = _resolve_workspace_path(workspace, arguments.get("path"))
    except ValueError as exc:
        return _redact({"error": str(exc)}, limit=2_000)
    content = str(arguments.get("content") or "")
    sensitive = bool(_SENSITIVE_PATH_PART.search(str(path)))
    _emit_activity(
        on_activity,
        phase="started",
        item={
            "id": item_id,
            "type": "fileChange",
            "changes": [{"path": str(path), "kind": "write"}],
        },
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.kolibri-tmp-{os.getpid()}")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
        payload = {
            "path": str(path),
            "bytes": len(content.encode("utf-8")),
        }
        diff = (
            "[REDACTED: sensitive path]"
            if sensitive
            else _redact(content, limit=12_000)
        )
        _emit_activity(
            on_activity,
            phase="completed",
            item={
                "id": item_id,
                "type": "fileChange",
                "changes": [
                    {"path": str(path), "kind": "write", "diff": diff}
                ],
            },
        )
        return _redact(payload, limit=2_000)
    except OSError as exc:
        return _redact({"error": f"не удалось записать файл: {exc}"}, limit=2_000)


def _run_glob(
    workspace: Path,
    arguments: Mapping[str, Any],
    *,
    timeout: float = BASH_TIMEOUT_SECONDS,
    item_id: str,
    on_activity: Callable[[str, dict[str, Any]], None] | None,
) -> str:
    pattern = str(arguments.get("pattern") or "").strip()
    if not pattern:
        return _redact({"error": "pattern is required"}, limit=2_000)
    _emit_activity(
        on_activity,
        phase="started",
        item={
            "id": item_id,
            "type": "fileChange",
            "changes": [{"path": pattern, "kind": "glob"}],
        },
    )
    matches: list[str] = []
    try:
        for candidate in workspace.glob(pattern):
            if len(matches) >= MAX_GLOB_RESULTS:
                break
            try:
                relative = candidate.resolve().relative_to(workspace.resolve())
            except ValueError:
                continue
            matches.append(str(relative))
    except (OSError, ValueError) as exc:
        return _redact({"error": f"glob не удался: {exc}"}, limit=2_000)
    payload = {"pattern": pattern, "matches": sorted(matches)}
    _emit_activity(
        on_activity,
        phase="completed",
        item={
            "id": item_id,
            "type": "fileChange",
            "changes": [{"path": pattern, "kind": "glob"}],
        },
    )
    return _redact(payload, limit=20_000)


def _run_grep(
    workspace: Path,
    arguments: Mapping[str, Any],
    *,
    timeout: float = BASH_TIMEOUT_SECONDS,
    item_id: str,
    on_activity: Callable[[str, dict[str, Any]], None] | None,
) -> str:
    pattern = str(arguments.get("pattern") or "").strip()
    if not pattern:
        return _redact({"error": "pattern is required"}, limit=2_000)
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return _redact({"error": f"некорректный regex: {exc}"}, limit=2_000)
    try:
        search_root = (
            _resolve_workspace_path(workspace, arguments.get("path"))
            if arguments.get("path")
            else workspace
        )
    except ValueError as exc:
        return _redact({"error": str(exc)}, limit=2_000)
    _emit_activity(
        on_activity,
        phase="started",
        item={
            "id": item_id,
            "type": "fileChange",
            "changes": [{"path": str(search_root), "kind": "grep"}],
        },
    )
    matches: list[str] = []
    workspace_root = workspace.resolve()
    try:
        for root, _directories, files in os.walk(search_root):
            root_path = Path(root)
            try:
                root_path.resolve().relative_to(workspace_root)
            except ValueError:
                continue
            for filename in files:
                if len(matches) >= MAX_GREP_LINES:
                    break
                candidate = root_path / filename
                try:
                    candidate.resolve().relative_to(workspace_root)
                except ValueError:
                    continue
                try:
                    if candidate.stat().st_size > MAX_READ_BYTES:
                        continue
                    text = candidate.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
                except (OSError, UnicodeError):
                    continue
                for line_number, line in enumerate(text.splitlines(), 1):
                    if len(matches) >= MAX_GREP_LINES:
                        break
                    if regex.search(line):
                        relative = candidate.resolve().relative_to(workspace_root)
                        matches.append(f"{relative}:{line_number}:{_redact(line, limit=400)}")
    except OSError as exc:
        return _redact({"error": f"grep не удался: {exc}"}, limit=2_000)
    payload = {"pattern": pattern, "matches": matches}
    _emit_activity(
        on_activity,
        phase="completed",
        item={
            "id": item_id,
            "type": "fileChange",
            "changes": [{"path": str(search_root), "kind": "grep"}],
        },
    )
    return _redact(payload, limit=30_000)


_TOOL_EXECUTORS = {
    "bash": _run_bash,
    "read_file": _run_read_file,
    "write_file": _run_write_file,
    "glob": _run_glob,
    "grep": _run_grep,
}


def _responses_payload(
    *,
    api_model: str,
    instructions: str,
    input_items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "model": api_model,
        "instructions": instructions[:100_000],
        "input": input_items,
        "tools": _tool_schemas(),
        "tool_choice": "auto",
        "stream": False,
    }


def _post_responses(
    settings: Settings,
    *,
    api_key: str,
    base_url: str,
    payload: dict[str, Any],
) -> httpx.Response:
    url = f"{base_url.rstrip('/')}/v1/responses"
    return httpx.post(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=httpx.Timeout(HTTP_TIMEOUT_SECONDS, connect=15),
        follow_redirects=False,
        trust_env=False,
    )


def _responses_error(code: str, message: str) -> AgentRuntimeError:
    return AgentRuntimeError(code, message, category="unavailable")


def _execute_tool(
    workspace: Path,
    item: Mapping[str, Any],
    *,
    item_id: str,
    timeout: float,
    on_activity: Callable[[str, dict[str, Any]], None] | None,
) -> tuple[str, str]:
    name = str(item.get("name") or "")
    try:
        arguments = json.loads(str(item.get("arguments") or "{}"))
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be an object")
    except (TypeError, ValueError):
        arguments = {"error": "invalid arguments json"}
    executor = _TOOL_EXECUTORS.get(name)
    if executor is None:
        return name, _redact(
            {"error": f"неизвестный инструмент: {name}"},
            limit=2_000,
        )
    output = executor(
        workspace,
        arguments,
        timeout=timeout,
        item_id=item_id,
        on_activity=on_activity,
    )
    return name, output


def execute_deepseek_developer_agent(
    settings: Settings,
    *,
    api_key: str,
    base_url: str,
    api_model: str,
    request: AgentRuntimeRequest,
) -> AgentRuntimeResult:
    """Run the owner developer loop directly on DeepSeek's Responses API."""

    workspace = request.configuration.workspace.root
    if workspace is None:
        raise AgentRuntimeError(
            "developer_workspace_required",
            "Для developer-режима не задан workspace.",
            category="configuration",
        )
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise AgentRuntimeError(
            "developer_workspace_missing",
            "Workspace разработчика не существует.",
            category="configuration",
        )

    input_items: list[dict[str, Any]] = []
    for message in request.messages:
        role = message.role
        content = message.content
        if role in {"user", "assistant", "system", "developer"}:
            input_items.append({"role": role, "content": content})
    if not input_items or input_items[-1]["role"] != "user":
        input_items.append(
            {"role": "user", "content": request.followup_prompt}
        )

    instructions = "\n\n".join(
        part
        for part in (request.instructions, request.guidance or "")
        if part and part.strip()
    )
    if not instructions.strip():
        instructions = AGENT_DEVELOPER_INSTRUCTIONS_FALLBACK

    on_delta = request.on_delta
    on_activity = request.on_activity
    cancellation_signal = request.cancellation_signal
    deadline = time.monotonic() + max(
        request.timeout_seconds,
        60.0,
    )

    for iteration in range(1, MAX_AGENT_ITERATIONS + 1):
        if cancellation_signal is not None and cancellation_signal.is_set():
            raise AgentRuntimeError(
                "run_cancelled",
                "Задача остановлена пользователем.",
                category="cancelled",
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AgentRuntimeError(
                "developer_agent_timeout",
                "Время выполнения задачи истекло.",
                category="timeout",
            )
        try:
            response = _post_responses(
                settings,
                api_key=api_key,
                base_url=base_url,
                payload=_responses_payload(
                    api_model=api_model,
                    instructions=instructions,
                    input_items=input_items,
                ),
            )
        except httpx.HTTPError as exc:
            LOGGER.warning("DeepSeek developer request failed: %s", exc)
            raise _responses_error(
                "deepseek_request_failed",
                "DeepSeek API сейчас недоступен. Повторите запрос.",
            ) from None
        if response.status_code == 401:
            response.close()
            raise _responses_error(
                "deepseek_api_key_rejected",
                "DeepSeek отклонил ключ. Проверьте ключ модели в админке.",
            )
        if response.status_code == 429:
            response.close()
            raise _responses_error(
                "deepseek_rate_limited",
                "Превышен лимит запросов DeepSeek. Повторите позже.",
            )
        if response.status_code != 200:
            status_code = response.status_code
            body = _redact(response.text, limit=500)
            response.close()
            LOGGER.warning(
                "DeepSeek developer HTTP %s: %s",
                status_code,
                body,
            )
            raise _responses_error(
                "deepseek_request_failed",
                f"DeepSeek API недоступен (HTTP {status_code}). Повторите.",
            )
        try:
            value = response.json()
        except (TypeError, ValueError):
            response.close()
            raise _responses_error(
                "deepseek_response_invalid",
                "DeepSeek вернул некорректный ответ.",
            ) from None
        finally:
            response.close()

        output_items = value.get("output")
        if not isinstance(output_items, list):
            raise _responses_error(
                "deepseek_response_invalid",
                "DeepSeek вернул некорректный ответ.",
            )

        reasoning_parts: list[str] = []
        for item in output_items:
            if not isinstance(item, dict) or item.get("type") != "reasoning":
                continue
            for content in item.get("content") or []:
                if not isinstance(content, dict):
                    continue
                if content.get("type") not in {"reasoning_text", "text"}:
                    continue
                text = str(content.get("text") or "")
                if text:
                    reasoning_parts.append(text)
        if reasoning_parts and request.on_reasoning is not None:
            request.on_reasoning("".join(reasoning_parts))

        function_calls = [
            item
            for item in output_items
            if isinstance(item, dict) and item.get("type") == "function_call"
        ]
        if function_calls:
            tool_timeout = min(
                BASH_TIMEOUT_SECONDS,
                max(2.0, deadline - time.monotonic()),
            )
            tool_outputs: list[dict[str, Any]] = []
            for call in function_calls:
                if cancellation_signal is not None and cancellation_signal.is_set():
                    raise AgentRuntimeError(
                        "run_cancelled",
                        "Задача остановлена пользователем.",
                        category="cancelled",
                    )
                call_id = str(call.get("call_id") or call.get("id") or "")
                item_id = str(call.get("id") or f"tool_{iteration}_{len(tool_outputs)}")
                _name, output = _execute_tool(
                    workspace,
                    call,
                    item_id=item_id,
                    timeout=tool_timeout,
                    on_activity=on_activity,
                )
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": output,
                    }
                )
            input_items.extend(function_calls)
            input_items.extend(tool_outputs)
            continue

        text_parts: list[str] = []
        for item in output_items:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message":
                for content in item.get("content") or []:
                    if (
                        isinstance(content, dict)
                        and content.get("type") == "output_text"
                    ):
                        text = str(content.get("text") or "")
                        if text:
                            text_parts.append(text)
        text = "\n".join(text_parts).strip()
        if text:
            if on_delta is not None:
                on_delta(text)
            return AgentRuntimeResult(text=text[:200_000])
        raise AgentRuntimeError(
            "developer_agent_empty",
            "Агент не сформировал ответ. Повторите задачу.",
            category="unavailable",
        )

    raise AgentRuntimeError(
        "developer_agent_iteration_limit",
        "Агент превысил лимит шагов. Сократите задачу и повторите.",
        category="timeout",
    )


AGENT_DEVELOPER_INSTRUCTIONS_FALLBACK = """
Ты — встроенный агент-разработчик KolibriAI. Работай внутри переданного
репозитория: исследуй execution path, редактируй нужные файлы, запускай
локальные тесты и показывай проверяемый результат. Не публикуй ключи,
cookies, токены или private keys. Не выводи chain-of-thought. В финале кратко
перечисли изменённые файлы, существенные решения, выполненные проверки и
оставшиеся ограничения.
""".strip()
