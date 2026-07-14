"""Home-first Codex CLI execution provider.

The public API remains OpenAI-compatible, while this adapter executes a turn
through the owner's already-authenticated ``codex exec --json`` installation
on Home.  It deliberately does not copy browser sessions or turn the Codex
login into an API key.

Security properties:

* argv is built as a list and launched without a shell;
* the user prompt is sent on stdin, never interpolated into argv;
* every run is ephemeral and read-only;
* only JSONL stdout events are accepted;
* reasoning items, raw stderr, commands, paths and provider internals are not
  forwarded to the browser;
* cancellation and attempt timeouts terminate the whole process group;
* concurrency is bounded independently from the HTTP request lifecycle.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import signal
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Mapping


_TRUE_VALUES = {"1", "true", "yes", "on"}
_SAFE_ENV_NAMES = {
    "PATH",
    "HOME",
    "CODEX_HOME",
    "USER",
    "LOGNAME",
    "TMPDIR",
    "TEMP",
    "TMP",
    "LANG",
    "LC_ALL",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
}
_SECRET_PATTERNS = (
    re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\b(?:bearer|api[_-]?key|access[_-]?token|password)\s*[:=]\s*[^\s,;]+"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
)
_TOOL_TYPES: dict[str, tuple[str, str]] = {
    "command_execution": ("codex.readonly_command", "Проверяю данные"),
    "mcp_tool_call": ("codex.mcp", "Использую подключённый инструмент"),
    "web_search": ("codex.web_search", "Ищу актуальные источники"),
    "file_change": ("codex.file_check", "Проверяю изменения"),
}


class CodexCLIError(RuntimeError):
    """Sanitised provider failure safe to classify at the gateway boundary."""

    failure_kind = "codex_cli_failed"

    def __init__(self, failure_kind: str | None = None):
        self.failure_kind = failure_kind or self.failure_kind
        super().__init__(self.failure_kind)


class CodexCLIUnavailable(CodexCLIError):
    failure_kind = "codex_cli_unavailable"


class CodexCLIInvalidOutput(CodexCLIError):
    failure_kind = "codex_cli_invalid_jsonl"


class CodexCLITimeout(CodexCLIError):
    failure_kind = "codex_cli_timeout"


class CodexCLICancelled(CodexCLIError):
    failure_kind = "codex_cli_cancelled"


class CodexCLICapacityExhausted(CodexCLIError):
    failure_kind = "codex_cli_capacity_exhausted"


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in _TRUE_VALUES


def _first_env(*names: str, default: str = "") -> str:
    """Return the first non-empty environment value without exposing it."""

    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def _bool_env_alias(primary: str, legacy: str, default: bool) -> bool:
    if os.getenv(primary) is not None:
        return _bool_env(primary, default)
    return _bool_env(legacy, default)


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class CodexCLISettings:
    enabled: bool = True
    # Resolve the account-authorized CLI from the service PATH unless the
    # deployment pins an absolute path.  Linux Home units continue to pin
    # /usr/local/bin/codex, while Homebrew installs on Apple workers resolve
    # /opt/homebrew/bin/codex without a machine-specific source change.
    binary: str = "codex"
    model: str = ""
    oss: bool = False
    cwd: Path = Path(".")
    max_concurrency: int = 4
    queue_timeout_seconds: float = 15.0
    attempt_timeout_seconds: float = 3_600.0
    terminate_grace_seconds: float = 2.0
    health_timeout_seconds: float = 8.0
    max_prompt_bytes: int = 256 * 1024
    max_line_bytes: int = 1024 * 1024
    max_output_bytes: int = 16 * 1024 * 1024
    web_search: str = "live"
    respect_system_proxy: bool = True
    http_proxy: str = ""
    https_proxy: str = ""
    all_proxy: str = ""
    no_proxy: str = ""

    @classmethod
    def from_env(cls) -> "CodexCLISettings":
        cwd = Path(os.getenv("CODEX_CLI_CWD", os.getcwd())).expanduser()
        shared_proxy = _first_env("KOLIBRI_CODEX_CLI_HTTP_PROXY")
        explicit_proxy = _first_env(
            "CODEX_CLI_HTTP_PROXY",
            "CODEX_CLI_HTTPS_PROXY",
            "KOLIBRI_CODEX_CLI_HTTP_PROXY",
            "KOLIBRI_CODEX_CLI_HTTPS_PROXY",
        )
        return cls(
            enabled=_bool_env("CODEX_CLI_ENABLED", True),
            binary=_first_env(
                "CODEX_CLI_BINARY",
                "KOLIBRI_CODEX_CLI_BINARY",
                default="codex",
            ),
            model=_first_env("CODEX_CLI_MODEL", "KOLIBRI_CODEX_MODEL"),
            oss=_bool_env_alias("CODEX_CLI_OSS", "KOLIBRI_CODEX_OSS", False),
            cwd=cwd,
            max_concurrency=_bounded_int("CODEX_CLI_MAX_CONCURRENCY", 4, 1, 32),
            queue_timeout_seconds=_bounded_float("CODEX_CLI_QUEUE_TIMEOUT_SECONDS", 15.0, 0.1, 300.0),
            attempt_timeout_seconds=_bounded_float(
                "CODEX_CLI_ATTEMPT_TIMEOUT_SECONDS",
                3_600.0,
                1.0,
                86_400.0,
            ),
            terminate_grace_seconds=_bounded_float("CODEX_CLI_TERMINATE_GRACE_SECONDS", 2.0, 0.05, 15.0),
            health_timeout_seconds=_bounded_float("CODEX_CLI_HEALTH_TIMEOUT_SECONDS", 8.0, 0.5, 30.0),
            max_prompt_bytes=_bounded_int("CODEX_CLI_MAX_PROMPT_BYTES", 256 * 1024, 1024, 4 * 1024 * 1024),
            max_line_bytes=_bounded_int("CODEX_CLI_MAX_LINE_BYTES", 1024 * 1024, 4096, 8 * 1024 * 1024),
            max_output_bytes=_bounded_int("CODEX_CLI_MAX_OUTPUT_BYTES", 16 * 1024 * 1024, 64 * 1024, 64 * 1024 * 1024),
            web_search=os.getenv("CODEX_CLI_WEB_SEARCH", "live").strip().lower(),
            respect_system_proxy=_bool_env("CODEX_CLI_RESPECT_SYSTEM_PROXY", True),
            http_proxy=_first_env(
                "CODEX_CLI_HTTP_PROXY",
                "KOLIBRI_CODEX_CLI_HTTP_PROXY",
                "HTTP_PROXY",
                "http_proxy",
            ),
            https_proxy=_first_env(
                "CODEX_CLI_HTTPS_PROXY",
                "KOLIBRI_CODEX_CLI_HTTPS_PROXY",
                default=shared_proxy,
            ) or _first_env("HTTPS_PROXY", "https_proxy"),
            all_proxy=_first_env(
                "CODEX_CLI_ALL_PROXY",
                "KOLIBRI_CODEX_CLI_ALL_PROXY",
            ) or ("" if explicit_proxy else _first_env("ALL_PROXY", "all_proxy")),
            no_proxy=_first_env(
                "CODEX_CLI_NO_PROXY",
                "KOLIBRI_CODEX_CLI_NO_PROXY",
                "NO_PROXY",
                "no_proxy",
            ),
        )


def _sanitize_text(value: Any, *, limit: int = 64_000) -> str:
    text = str(value or "").replace("\x00", "")[:limit]
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _normalise_messages(messages: Iterable[Mapping[str, Any]]) -> str:
    lines = [
        "Ты работаешь как внутренний исполнитель Kolibri.",
        "Верни только полезный пользователю результат на русском языке.",
        "Не раскрывай private chain-of-thought, локальные пути, команды, credentials или внутреннюю топологию.",
        "Не утверждай, что изображение, документ или другой файл создан, если transport не передал реальный artifact bytes/hash contract.",
        "Не представляйся Codex или сторонним провайдером.",
        "",
        "Контекст диалога:",
    ]
    for message in messages:
        role = str(message.get("role") or "user").lower()
        if role not in {"system", "developer", "user", "assistant"}:
            role = "user"
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(
                str(part.get("text") or "")
                for part in content
                if isinstance(part, Mapping) and part.get("type") in {"text", "input_text", "output_text"}
            )
        lines.append(f"[{role}]\n{str(content or '')}")
    return "\n\n".join(lines).strip() + "\n"


def _resolve_binary(settings: CodexCLISettings, env: Mapping[str, str]) -> str | None:
    candidate = os.path.expanduser(settings.binary)
    if os.path.sep in candidate or (os.path.altsep and os.path.altsep in candidate):
        path = Path(candidate)
        return str(path.resolve()) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(candidate, path=env.get("PATH"))


def _safe_environment(settings: CodexCLISettings) -> dict[str, str]:
    env = {name: value for name in _SAFE_ENV_NAMES if (value := os.getenv(name))}
    env.setdefault("PATH", os.defpath)
    env.setdefault("HOME", str(Path.home()))
    env["PYTHONUNBUFFERED"] = "1"
    proxy_values = {
        "HTTP_PROXY": settings.http_proxy,
        "HTTPS_PROXY": settings.https_proxy,
        "ALL_PROXY": settings.all_proxy,
        "NO_PROXY": settings.no_proxy,
    }
    for name, value in proxy_values.items():
        if value:
            env[name] = value
            env[name.lower()] = value
    return env


def _tool_event(item: Mapping[str, Any], phase: str) -> dict[str, Any] | None:
    mapped = _TOOL_TYPES.get(str(item.get("type") or ""))
    if not mapped:
        return None
    tool, label = mapped
    return {
        "content": "",
        "done": False,
        "tool_event": {
            "type": f"tool.{phase}",
            "tool": tool,
            "label": label,
            "status": "active" if phase == "started" else "completed",
        },
    }


class CodexCLIProvider:
    def __init__(self, settings: CodexCLISettings | None = None):
        self.settings = settings or CodexCLISettings.from_env()
        self._semaphore = asyncio.Semaphore(self.settings.max_concurrency)
        self._active: dict[str, asyncio.subprocess.Process] = {}
        self._cancelled: set[str] = set()
        self._active_lock = asyncio.Lock()
        self._last_health: dict[str, Any] | None = None

    def configuration_snapshot(self) -> dict[str, Any]:
        env = _safe_environment(self.settings)
        binary = _resolve_binary(self.settings, env)
        cwd_ok = self.settings.cwd.expanduser().is_dir()
        configured = bool(self.settings.enabled and binary and cwd_ok)
        return {
            "configured": configured,
            "enabled": self.settings.enabled,
            "binary_available": bool(binary),
            "cwd_available": cwd_ok,
            "model": self.settings.model or "account-default",
            "max_concurrency": self.settings.max_concurrency,
            "proxy_configured": bool(
                self.settings.http_proxy or self.settings.https_proxy or self.settings.all_proxy
            ),
            "status": (self._last_health or {}).get("status", "unverified" if configured else "unavailable"),
            "verified_at": (self._last_health or {}).get("checked_at"),
        }

    def _argv(self, binary: str) -> list[str]:
        argv = [
            binary,
            "exec",
            "--json",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--color",
            "never",
            "-c",
            "hide_agent_reasoning=true",
            "-c",
            "show_raw_agent_reasoning=false",
            "-c",
            "features.apps=false",
            "-c",
            "features.remote_plugin=false",
            "-c",
            "features.multi_agent=false",
        ]
        if self.settings.respect_system_proxy:
            argv.extend(["--enable", "respect_system_proxy"])
        if self.settings.web_search in {"disabled", "cached", "indexed", "live"}:
            argv.extend(["-c", f'web_search="{self.settings.web_search}"'])
        if self.settings.oss:
            argv.append("--oss")
        if self.settings.model:
            argv.extend(["--model", self.settings.model])
        argv.append("-")
        return argv

    async def _terminate(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            if sys.platform != "win32" and process.pid:
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=self.settings.terminate_grace_seconds)
            return
        except asyncio.TimeoutError:
            pass
        try:
            if sys.platform != "win32" and process.pid:
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            return
        await process.wait()

    async def cancel(self, run_id: str) -> bool:
        async with self._active_lock:
            process = self._active.get(run_id)
            if not process:
                return False
            self._cancelled.add(run_id)
        await self._terminate(process)
        return True

    async def _drain_stderr(self, stream: asyncio.StreamReader | None) -> None:
        if stream is None:
            return
        remaining = min(self.settings.max_output_bytes, 1024 * 1024)
        while remaining > 0:
            chunk = await stream.read(min(65_536, remaining))
            if not chunk:
                return
            remaining -= len(chunk)
        while await stream.read(65_536):
            pass

    async def _normalised_events(
        self,
        process: asyncio.subprocess.Process,
        run_id: str,
    ) -> AsyncIterator[dict[str, Any]]:
        if process.stdout is None:
            raise CodexCLIUnavailable()
        seen_agent_text: dict[str, str] = {}
        emitted_text = False
        output_bytes = 0
        turn_failed = False
        turn_completed = False
        while True:
            try:
                raw = await process.stdout.readline()
            except (ValueError, asyncio.LimitOverrunError) as exc:
                raise CodexCLIInvalidOutput() from exc
            if not raw:
                break
            output_bytes += len(raw)
            if len(raw) > self.settings.max_line_bytes or output_bytes > self.settings.max_output_bytes:
                raise CodexCLIInvalidOutput("codex_cli_output_limit")
            try:
                event = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CodexCLIInvalidOutput() from exc
            if not isinstance(event, dict):
                raise CodexCLIInvalidOutput()
            event_type = str(event.get("type") or "")
            if event_type == "thread.started":
                yield {
                    "content": "",
                    "done": False,
                    "response_meta": {"status": "in_progress", "run_id": run_id},
                }
            elif event_type == "turn.started":
                yield {
                    "content": "",
                    "done": False,
                    "work_summary": {
                        "stage": "codex_turn",
                        "summary": "Codex начал выполнение",
                        "status": "active",
                    },
                }
            elif event_type in {"item.started", "item.updated", "item.completed"}:
                item = event.get("item")
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "")
                if item_type == "reasoning":
                    continue
                if item_type == "agent_message":
                    text = _sanitize_text(item.get("text"))
                    item_id = str(item.get("id") or "agent")
                    previous = seen_agent_text.get(item_id, "")
                    if text.startswith(previous):
                        delta = text[len(previous):]
                    elif event_type == "item.completed" and not previous:
                        delta = text
                    else:
                        delta = ""
                    if len(text) >= len(previous):
                        seen_agent_text[item_id] = text
                    if delta:
                        emitted_text = True
                        yield {"content": delta, "done": False}
                    continue
                phase = "started" if event_type == "item.started" else "completed" if event_type == "item.completed" else ""
                if phase:
                    tool = _tool_event(item, phase)
                    if tool:
                        yield tool
                if item_type == "plan" and event_type == "item.completed":
                    yield {
                        "content": "",
                        "done": False,
                        "work_summary": {
                            "stage": "plan_updated",
                            "summary": "План выполнения обновлён",
                            "status": "completed",
                        },
                    }
            elif event_type == "turn.completed":
                turn_completed = True
                yield {
                    "content": "",
                    "done": False,
                    "work_summary": {
                        "stage": "codex_turn",
                        "summary": "Codex завершил выполнение",
                        "status": "completed",
                    },
                }
            elif event_type == "turn.failed":
                turn_failed = True

        return_code = await process.wait()
        if run_id in self._cancelled:
            raise CodexCLICancelled()
        if return_code != 0 or turn_failed:
            raise CodexCLIError()
        if not turn_completed:
            raise CodexCLIInvalidOutput("codex_cli_incomplete_turn")
        if not emitted_text:
            raise CodexCLIInvalidOutput("codex_cli_empty_response")
        yield {"content": "", "done": True, "run_id": run_id}

    async def stream(
        self,
        messages: Iterable[Mapping[str, Any]],
        *,
        policy: Mapping[str, Any] | None = None,
        run_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        del policy  # Policy affects routing; Codex remains locked to read-only here.
        run_id = run_id or f"codex_{uuid.uuid4().hex}"
        prompt = _normalise_messages(messages)
        prompt_bytes = prompt.encode("utf-8")
        if len(prompt_bytes) > self.settings.max_prompt_bytes:
            raise CodexCLIError("codex_cli_prompt_too_large")
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self.settings.queue_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise CodexCLICapacityExhausted() from exc

        process: asyncio.subprocess.Process | None = None
        stderr_task: asyncio.Task[None] | None = None
        try:
            snapshot = self.configuration_snapshot()
            if not snapshot["configured"]:
                raise CodexCLIUnavailable()
            env = _safe_environment(self.settings)
            binary = _resolve_binary(self.settings, env)
            if not binary:
                raise CodexCLIUnavailable()
            process = await asyncio.create_subprocess_exec(
                *self._argv(binary),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.settings.cwd.expanduser()),
                env=env,
                start_new_session=sys.platform != "win32",
                limit=self.settings.max_line_bytes + 1,
            )
            async with self._active_lock:
                if run_id in self._active:
                    await self._terminate(process)
                    raise CodexCLIError("codex_cli_duplicate_run_id")
                self._active[run_id] = process
            stderr_task = asyncio.create_task(self._drain_stderr(process.stderr))
            if process.stdin is None:
                raise CodexCLIUnavailable()
            process.stdin.write(prompt_bytes)
            await process.stdin.drain()
            process.stdin.close()
            if hasattr(process.stdin, "wait_closed"):
                await process.stdin.wait_closed()

            try:
                async with asyncio.timeout(self.settings.attempt_timeout_seconds):
                    async for event in self._normalised_events(process, run_id):
                        yield event
            except TimeoutError as exc:
                await self._terminate(process)
                raise CodexCLITimeout() from exc
        except asyncio.CancelledError:
            if process is not None:
                await self._terminate(process)
            raise
        except Exception:
            if process is not None:
                await self._terminate(process)
            raise
        finally:
            if stderr_task is not None:
                await stderr_task
            async with self._active_lock:
                self._active.pop(run_id, None)
                self._cancelled.discard(run_id)
            self._semaphore.release()

    async def invoke(
        self,
        messages: Iterable[Mapping[str, Any]],
        *,
        policy: Mapping[str, Any] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        content: list[str] = []
        tool_events: list[dict[str, Any]] = []
        work_summaries: list[dict[str, Any]] = []
        async for event in self.stream(messages, policy=policy, run_id=run_id):
            if event.get("content"):
                content.append(str(event["content"]))
            if isinstance(event.get("tool_event"), dict):
                tool_events.append(dict(event["tool_event"]))
            if isinstance(event.get("work_summary"), dict):
                work_summaries.append(dict(event["work_summary"]))
        return {
            "content": "".join(content),
            "tool_events": tool_events,
            "work_summaries": work_summaries,
            "model": self.settings.model or "account-default",
        }

    async def _probe_command(self, argv: list[str]) -> tuple[bool, str]:
        env = _safe_environment(self.settings)
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.settings.cwd.expanduser()),
            env=env,
            start_new_session=sys.platform != "win32",
        )
        try:
            stdout, _stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.settings.health_timeout_seconds,
            )
        except asyncio.TimeoutError:
            await self._terminate(process)
            return False, ""
        return process.returncode == 0, _sanitize_text(stdout.decode("utf-8", "replace"), limit=256).strip()

    async def probe_health(self) -> dict[str, Any]:
        checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        snapshot = self.configuration_snapshot()
        base = {
            "provider": "codex_cli",
            "checked_at": checked_at,
            "credential_source": "home_codex_cli_login",
            "secret_exposed": False,
            "model": self.settings.model or "account-default",
            "tests": {
                "binary": {"ok": snapshot["binary_available"]},
                "cwd": {"ok": snapshot["cwd_available"]},
            },
        }
        if not snapshot["configured"]:
            result = {
                **base,
                "status": "unavailable",
                "entitlement": "unverified",
                "error_code": "codex_cli_not_configured",
            }
            self._last_health = result
            return result
        env = _safe_environment(self.settings)
        binary = _resolve_binary(self.settings, env)
        if not binary:
            result = {
                **base,
                "status": "unavailable",
                "entitlement": "unverified",
                "error_code": "codex_cli_binary_missing",
            }
            self._last_health = result
            return result
        version_ok, version = await self._probe_command([binary, "--version"])
        login_ok, _login_output = await self._probe_command([binary, "login", "status"])
        base["tests"].update({
            "version": {"ok": version_ok},
            "login": {"ok": login_ok},
        })
        if version_ok:
            base["version"] = version
        result = (
            {
                **base,
                "status": "live",
                "entitlement": "granted",
                "error_code": None,
            }
            if version_ok and login_ok
            else {
                **base,
                "status": "unavailable",
                "entitlement": "denied" if version_ok and not login_ok else "unverified",
                "error_code": "codex_cli_login_required" if version_ok and not login_ok else "codex_cli_probe_failed",
            }
        )
        self._last_health = result
        return result


_default_provider: CodexCLIProvider | None = None
_default_settings: CodexCLISettings | None = None


def get_codex_cli_provider() -> CodexCLIProvider:
    global _default_provider, _default_settings
    settings = CodexCLISettings.from_env()
    if _default_provider is None or _default_settings != settings:
        _default_settings = settings
        _default_provider = CodexCLIProvider(settings)
    return _default_provider


def codex_cli_configuration() -> dict[str, Any]:
    return get_codex_cli_provider().configuration_snapshot()


async def probe_codex_cli() -> dict[str, Any]:
    return await get_codex_cli_provider().probe_health()


async def cancel_codex_cli_run(run_id: str) -> bool:
    return await get_codex_cli_provider().cancel(run_id)
