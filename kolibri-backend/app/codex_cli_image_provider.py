"""Bounded Codex CLI image worker for the Home-authorized session.

The public Kolibri API never receives a browser credential or an OpenAI REST
key.  This adapter launches the explicit Home Codex binary in an empty,
per-attempt workspace and accepts success only when exactly one regular raster
file survives strict byte, media type, dimension, size, and digest checks.
Model prose and JSONL path claims are never artifacts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import signal
import stat
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.codex_cli_provider import CodexCLISettings, _resolve_binary, _safe_environment
from app.image_validation import DEFAULT_MAX_IMAGE_BYTES, InvalidImageBytes, inspect_image_bytes


_TRUE_VALUES = {"1", "true", "yes", "on"}
_RUN_ID = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
_MODEL_ID = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")


class CodexCLIImageError(RuntimeError):
    """Sanitised image-worker failure safe for gateway classification."""

    failure_kind = "codex_cli_image_failed"

    def __init__(self, failure_kind: str | None = None):
        self.failure_kind = failure_kind or self.failure_kind
        super().__init__(self.failure_kind)


class CodexCLIImageUnavailable(CodexCLIImageError):
    failure_kind = "codex_cli_image_unavailable"


class CodexCLIImageInvalidArtifact(CodexCLIImageError):
    failure_kind = "codex_cli_image_invalid_artifact"


class CodexCLIImageTimeout(CodexCLIImageError):
    failure_kind = "codex_cli_image_timeout"


class CodexCLIImageCancelled(CodexCLIImageError):
    failure_kind = "codex_cli_image_cancelled"


class CodexCLIImageCapacityExhausted(CodexCLIImageError):
    failure_kind = "codex_cli_image_capacity_exhausted"


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in _TRUE_VALUES


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _public_model_label(value: str) -> str:
    if _MODEL_ID.fullmatch(value):
        return value
    return "configured-model" if value else "account-default"


@dataclass(frozen=True)
class CodexCLIImageSettings:
    enabled: bool
    cli: CodexCLISettings
    model: str
    max_concurrency: int = 2
    queue_timeout_seconds: float = 15.0
    attempt_timeout_seconds: float = 600.0
    terminate_grace_seconds: float = 2.0
    max_line_bytes: int = 1024 * 1024
    max_output_bytes: int = 16 * 1024 * 1024
    max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES
    max_workspace_entries: int = 64
    temp_root: Path | None = None

    @classmethod
    def from_env(cls) -> "CodexCLIImageSettings":
        cli = CodexCLISettings.from_env()
        raw_temp_root = os.getenv("CODEX_CLI_IMAGE_TEMP_ROOT", "").strip()
        return cls(
            enabled=_bool_env("CODEX_CLI_IMAGE_ENABLED", True) and cli.enabled,
            cli=cli,
            model=os.getenv("CODEX_CLI_IMAGE_MODEL", cli.model).strip(),
            max_concurrency=_bounded_int("CODEX_CLI_IMAGE_MAX_CONCURRENCY", 2, 1, 8),
            queue_timeout_seconds=_bounded_float(
                "CODEX_CLI_IMAGE_QUEUE_TIMEOUT_SECONDS", 15.0, 0.1, 300.0
            ),
            attempt_timeout_seconds=_bounded_float(
                "CODEX_CLI_IMAGE_TIMEOUT_SECONDS", 600.0, 1.0, 1800.0
            ),
            terminate_grace_seconds=_bounded_float(
                "CODEX_CLI_IMAGE_TERMINATE_GRACE_SECONDS", 2.0, 0.05, 15.0
            ),
            max_line_bytes=_bounded_int(
                "CODEX_CLI_IMAGE_MAX_LINE_BYTES", 1024 * 1024, 4096, 8 * 1024 * 1024
            ),
            max_output_bytes=_bounded_int(
                "CODEX_CLI_IMAGE_MAX_OUTPUT_BYTES",
                16 * 1024 * 1024,
                64 * 1024,
                64 * 1024 * 1024,
            ),
            max_image_bytes=_bounded_int(
                "CODEX_CLI_IMAGE_MAX_BYTES",
                DEFAULT_MAX_IMAGE_BYTES,
                1024,
                50 * 1024 * 1024,
            ),
            max_workspace_entries=_bounded_int(
                "CODEX_CLI_IMAGE_MAX_WORKSPACE_ENTRIES", 64, 1, 512
            ),
            temp_root=Path(raw_temp_root).expanduser() if raw_temp_root else None,
        )


@dataclass(frozen=True)
class CodexCLIImageResult:
    data: bytes
    mime_type: str
    width: int
    height: int
    sha256: str
    model: str


@dataclass(frozen=True)
class _CodexCLIImageTurn:
    thread_id: str | None
    candidate_paths: tuple[str, ...]


def _generated_path_candidates(value: Any, generated_root: Path) -> list[str]:
    """Extract only path-shaped strings inside the trusted image root.

    Codex JSONL may put the generated path in an image-tool item or embed it
    in an otherwise human-readable completed message.  Prose is never treated
    as evidence: a candidate must be an absolute descendant of the resolved
    ``CODEX_HOME/generated_images`` root and later passes the fd-based byte
    verifier.
    """

    root_text = str(generated_root)
    path_pattern = re.compile(
        rf"{re.escape(root_text)}/[A-Za-z0-9._/-]{{1,4096}}"
    )
    candidates: list[str] = []
    pending: list[Any] = [value]
    visited = 0
    while pending and visited < 512:
        current = pending.pop()
        visited += 1
        if isinstance(current, str):
            candidates.extend(
                candidate.rstrip(".,;:")
                for candidate in path_pattern.findall(current)
            )
        elif isinstance(current, Mapping):
            pending.extend(current.values())
        elif isinstance(current, (list, tuple)):
            pending.extend(current)
    return candidates


def _image_prompt(
    prompt: str,
    *,
    size: str,
    quality: str,
    source_image_path: Path | None = None,
) -> str:
    instructions = [
            "Ты — изолированный внутренний исполнитель изображений Kolibri.",
            "Используй встроенный инструмент генерации изображений.",
            "Создай ровно одно итоговое растровое изображение PNG, JPEG или WebP.",
            "Не используй shell, команды, файловый редактор, поиск файлов или другие инструменты.",
            "В финальном сообщении верни только точный абсолютный путь файла, созданного встроенным image_generation.",
            "Не добавляй Markdown, пояснения, кавычки или другой текст.",
            "Путь и утверждение об успехе не считаются результатом без независимой проверки реальных байтов.",
            "Не раскрывай рассуждения, команды, credentials, локальные пути или внутреннюю топологию.",
            f"Желаемый размер: {size}. Качество: {quality}.",
    ]
    if source_image_path is not None:
        instructions.extend(
            [
                "Это задача редактирования существующего изображения, а не генерация с нуля.",
                "Передай встроенному image_generation ровно один referenced_image_path, указанный ниже.",
                "Не изменяй и не копируй исходный файл; создай новый итоговый файл.",
                "Путь к исходному изображению задаётся доверенным host-процессом:",
                "<kolibri_source_image_path>",
                str(source_image_path),
                "</kolibri_source_image_path>",
            ]
        )
    instructions.extend(
        [
            "Пользовательское описание находится только между маркерами ниже:",
            "<kolibri_image_request>",
            prompt,
            "</kolibri_image_request>",
            "После сохранения файла заверши задачу без дополнительного текста.",
            "",
        ]
    )
    return "\n".join(instructions)


class CodexCLIImageProvider:
    def __init__(self, settings: CodexCLIImageSettings | None = None):
        self.settings = settings or CodexCLIImageSettings.from_env()
        self._semaphore = asyncio.Semaphore(self.settings.max_concurrency)
        self._active: dict[str, asyncio.subprocess.Process] = {}
        self._cancelled: set[str] = set()
        self._active_lock = asyncio.Lock()

    def configuration_snapshot(self) -> dict[str, Any]:
        env = _safe_environment(self.settings.cli)
        binary = _resolve_binary(self.settings.cli, env)
        temp_root_ok = self.settings.temp_root is None or self.settings.temp_root.is_dir()
        configured = bool(self.settings.enabled and binary and temp_root_ok)
        return {
            "configured": configured,
            "enabled": self.settings.enabled,
            "binary_available": bool(binary),
            "temp_root_available": temp_root_ok,
            "provider": "codex_cli",
            "model": _public_model_label(self.settings.model),
            "max_concurrency": self.settings.max_concurrency,
            "proxy_configured": bool(
                self.settings.cli.http_proxy
                or self.settings.cli.https_proxy
                or self.settings.cli.all_proxy
            ),
        }

    def _argv(self, binary: str, workspace: Path) -> list[str]:
        argv = [
            binary,
            "exec",
            "--json",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "--color",
            "never",
            "-C",
            str(workspace),
            "-c",
            "hide_agent_reasoning=true",
            "-c",
            "show_raw_agent_reasoning=false",
            "--enable",
            "image_generation",
            "--disable",
            "shell_tool",
            "--disable",
            "apps",
            "--disable",
            "remote_plugin",
            "--disable",
            "multi_agent",
            "--disable",
            "browser_use",
            "--disable",
            "computer_use",
            "-c",
            'web_search="disabled"',
        ]
        if self.settings.cli.respect_system_proxy:
            argv.extend(["--enable", "respect_system_proxy"])
        if self.settings.cli.oss:
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
            await asyncio.wait_for(
                process.wait(), timeout=self.settings.terminate_grace_seconds
            )
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
        if not _RUN_ID.fullmatch(run_id):
            return False
        async with self._active_lock:
            process = self._active.get(run_id)
            if process is None:
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

    async def _consume_jsonl(
        self,
        process: asyncio.subprocess.Process,
        *,
        run_id: str,
        generated_root: Path,
    ) -> _CodexCLIImageTurn:
        if process.stdout is None:
            raise CodexCLIImageUnavailable()
        output_bytes = 0
        turn_completed = False
        turn_failed = False
        thread_id: str | None = None
        artifact_paths: list[str] = []
        while True:
            try:
                raw = await process.stdout.readline()
            except (ValueError, asyncio.LimitOverrunError) as exc:
                raise CodexCLIImageError("codex_cli_image_invalid_jsonl") from exc
            if not raw:
                break
            output_bytes += len(raw)
            if len(raw) > self.settings.max_line_bytes or output_bytes > self.settings.max_output_bytes:
                raise CodexCLIImageError("codex_cli_image_output_limit")
            try:
                event = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CodexCLIImageError("codex_cli_image_invalid_jsonl") from exc
            if not isinstance(event, Mapping):
                raise CodexCLIImageError("codex_cli_image_invalid_jsonl")
            event_type = str(event.get("type") or "")
            if event_type == "thread.started":
                candidate_thread_id = str(event.get("thread_id") or "")
                if candidate_thread_id:
                    thread_id = candidate_thread_id
            elif event_type == "turn.completed":
                turn_completed = True
            elif event_type == "turn.failed":
                turn_failed = True
            elif event_type == "item.completed":
                item = event.get("item")
                if isinstance(item, Mapping):
                    artifact_paths.extend(
                        _generated_path_candidates(item, generated_root)
                    )

            # Codex may emit a recoverable top-level ``error`` (or an
            # ``item.completed`` whose item type is ``error``) for an optional
            # under-development feature and still complete the turn after its
            # fallback path succeeds. The process exit status plus the
            # terminal turn event are authoritative; provider prose/errors are
            # never trusted as artifact evidence either way.

        return_code = await process.wait()
        if run_id in self._cancelled:
            raise CodexCLIImageCancelled()
        if return_code != 0 or turn_failed:
            raise CodexCLIImageError()
        if not turn_completed:
            raise CodexCLIImageError("codex_cli_image_incomplete_turn")
        return _CodexCLIImageTurn(
            thread_id=thread_id,
            candidate_paths=tuple(dict.fromkeys(artifact_paths)),
        )

    def _thread_artifact_paths(
        self,
        *,
        generated_root: Path,
        thread_id: str | None,
    ) -> list[str]:
        if not thread_id:
            return []
        try:
            normalized_thread_id = str(uuid.UUID(thread_id))
            root = generated_root.resolve(strict=True)
            thread_root = (root / normalized_thread_id).resolve(strict=True)
            thread_root.relative_to(root)
        except (ValueError, FileNotFoundError, OSError):
            return []
        if not thread_root.is_dir():
            return []
        paths: list[str] = []
        for index, candidate in enumerate(thread_root.rglob("*"), start=1):
            if index > self.settings.max_workspace_entries:
                raise CodexCLIImageInvalidArtifact("codex_cli_image_entry_limit")
            try:
                mode = candidate.lstat().st_mode
            except OSError as exc:
                raise CodexCLIImageInvalidArtifact() from exc
            if stat.S_ISREG(mode):
                paths.append(str(candidate))
        return paths

    def _verified_turn_image(
        self,
        turn: _CodexCLIImageTurn,
        *,
        generated_root: Path,
        not_before_ns: int,
    ) -> CodexCLIImageResult:
        candidates = list(turn.candidate_paths)
        if not candidates:
            # Built-in $imagegen stores output below a directory named after
            # the Codex thread.  Bind the fallback scan to that exact thread;
            # never scan the shared root where concurrent attempts live.
            candidates = self._thread_artifact_paths(
                generated_root=generated_root,
                thread_id=turn.thread_id,
            )
        if not candidates:
            raise CodexCLIImageInvalidArtifact()
        if len(candidates) == 1:
            return self._read_verified_image(
                candidates[0],
                generated_root=generated_root,
                not_before_ns=not_before_ns,
            )

        # Current image_generation may return two visual variants even when
        # the request asks for one.  Accept the first provider-ordered variant
        # only when every candidate is a fresh, valid raster inside the exact
        # Codex thread directory.  Multiple unbound/shared-root paths remain a
        # hard failure, so one attempt cannot claim another attempt's output.
        try:
            normalized_thread_id = str(uuid.UUID(str(turn.thread_id or "")))
            root = generated_root.resolve(strict=True)
            thread_root = (root / normalized_thread_id).resolve(strict=True)
            thread_root.relative_to(root)
        except (ValueError, FileNotFoundError, OSError):
            raise CodexCLIImageInvalidArtifact() from None

        verified: list[CodexCLIImageResult] = []
        for candidate in candidates:
            try:
                Path(candidate).resolve(strict=True).relative_to(thread_root)
            except (ValueError, FileNotFoundError, OSError):
                raise CodexCLIImageInvalidArtifact() from None
            verified.append(
                self._read_verified_image(
                    candidate,
                    generated_root=generated_root,
                    not_before_ns=not_before_ns,
                )
            )
        return verified[0]

    def _read_verified_image(
        self,
        claimed_path: str,
        *,
        generated_root: Path,
        not_before_ns: int,
    ) -> CodexCLIImageResult:
        # The model only nominates a candidate.  The trusted host process owns
        # every path, freshness, inode and byte-level check below.
        if not claimed_path or "\n" in claimed_path or "\r" in claimed_path:
            raise CodexCLIImageInvalidArtifact()
        raw_path = Path(claimed_path)
        if not raw_path.is_absolute() or len(claimed_path.encode("utf-8")) > 4096:
            raise CodexCLIImageInvalidArtifact()
        try:
            root = generated_root.resolve(strict=True)
            path = raw_path.resolve(strict=True)
            relative = path.relative_to(root)
            file_stat = path.lstat()
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise CodexCLIImageInvalidArtifact() from exc
        if not relative.parts or len(relative.parts) > 8:
            raise CodexCLIImageInvalidArtifact()
        if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
            raise CodexCLIImageInvalidArtifact()
        if file_stat.st_nlink != 1 or file_stat.st_size <= 0:
            raise CodexCLIImageInvalidArtifact()
        if file_stat.st_size > self.settings.max_image_bytes:
            raise CodexCLIImageInvalidArtifact("codex_cli_image_size_limit")
        # A stale path from an earlier conversation can never satisfy a new
        # response.  One second accommodates coarse filesystem timestamp
        # precision while the inode checks below close replacement races.
        if max(file_stat.st_mtime_ns, file_stat.st_ctime_ns) < not_before_ns - 1_000_000_000:
            raise CodexCLIImageInvalidArtifact("codex_cli_image_stale_artifact")

        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
            try:
                opened_stat = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(opened_stat.st_mode)
                    or opened_stat.st_nlink != 1
                    or opened_stat.st_ino != file_stat.st_ino
                    or opened_stat.st_dev != file_stat.st_dev
                    or opened_stat.st_size != file_stat.st_size
                ):
                    raise CodexCLIImageInvalidArtifact()
                chunks: list[bytes] = []
                remaining = self.settings.max_image_bytes + 1
                while remaining > 0:
                    chunk = os.read(descriptor, min(65_536, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
            finally:
                os.close(descriptor)
        except OSError as exc:
            raise CodexCLIImageInvalidArtifact() from exc
        data = b"".join(chunks)
        try:
            details = inspect_image_bytes(data, max_bytes=self.settings.max_image_bytes)
        except InvalidImageBytes as exc:
            raise CodexCLIImageInvalidArtifact() from exc
        return CodexCLIImageResult(
            data=data,
            mime_type=details.mime_type,
            width=details.width,
            height=details.height,
            sha256=hashlib.sha256(data).hexdigest(),
            model=f"codex-cli:{_public_model_label(self.settings.model)}",
        )

    async def generate(
        self,
        prompt: str,
        *,
        size: str = "1024x1024",
        quality: str = "high",
        run_id: str | None = None,
        source_image: bytes | None = None,
    ) -> CodexCLIImageResult:
        run_id = run_id or f"codex_image_{uuid.uuid4().hex}"
        if not _RUN_ID.fullmatch(run_id):
            raise CodexCLIImageError("codex_cli_image_invalid_run_id")
        source_details = None
        if source_image is not None:
            try:
                source_details = inspect_image_bytes(
                    source_image,
                    max_bytes=self.settings.max_image_bytes,
                )
            except InvalidImageBytes as exc:
                raise CodexCLIImageInvalidArtifact(
                    "codex_cli_image_invalid_source"
                ) from exc
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(), timeout=self.settings.queue_timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            raise CodexCLIImageCapacityExhausted() from exc

        process: asyncio.subprocess.Process | None = None
        stderr_task: asyncio.Task[None] | None = None
        try:
            snapshot = self.configuration_snapshot()
            if not snapshot["configured"]:
                raise CodexCLIImageUnavailable()
            env = _safe_environment(self.settings.cli)
            binary = _resolve_binary(self.settings.cli, env)
            if not binary:
                raise CodexCLIImageUnavailable()
            generated_root = Path(env.get("CODEX_HOME", env["HOME"] + "/.codex")) / "generated_images"
            generated_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            generated_root = generated_root.resolve(strict=True)
            with tempfile.TemporaryDirectory(
                prefix="kolibri-codex-image-",
                dir=str(self.settings.temp_root) if self.settings.temp_root else None,
            ) as attempt_root_raw:
                attempt_root = Path(attempt_root_raw).resolve()
                os.chmod(attempt_root, 0o700)

                # Codex/bwrap may materialise private runtime bookkeeping below
                # TMPDIR (for example ``codex-bwrap-synthetic-mount-targets-*``).
                # Keep that scratch state outside the empty output workspace so
                # artifact verification sees only files intentionally written as
                # the final result.  Scratch is never scanned or returned.
                workspace = attempt_root / "final"
                scratch = attempt_root / "scratch"
                workspace.mkdir(mode=0o700)
                scratch.mkdir(mode=0o700)
                source_path: Path | None = None
                if source_details is not None and source_image is not None:
                    source_path = workspace / f"source{source_details.extension}"
                    descriptor = os.open(
                        source_path,
                        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                        0o600,
                    )
                    try:
                        view = memoryview(source_image)
                        written = 0
                        while written < len(view):
                            written += os.write(descriptor, view[written:])
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                prompt_bytes = _image_prompt(
                    prompt,
                    size=size,
                    quality=quality,
                    source_image_path=source_path,
                ).encode("utf-8")
                if len(prompt_bytes) > self.settings.cli.max_prompt_bytes:
                    raise CodexCLIImageError("codex_cli_image_prompt_too_large")
                env.update(
                    {
                        "TMPDIR": str(scratch),
                        "TMP": str(scratch),
                        "TEMP": str(scratch),
                    }
                )
                attempt_started_ns = time.time_ns()
                process = await asyncio.create_subprocess_exec(
                    *self._argv(binary, workspace),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(workspace),
                    env=env,
                    start_new_session=sys.platform != "win32",
                    limit=self.settings.max_line_bytes + 1,
                )
                async with self._active_lock:
                    if run_id in self._active:
                        await self._terminate(process)
                        raise CodexCLIImageError("codex_cli_image_duplicate_run_id")
                    self._active[run_id] = process
                stderr_task = asyncio.create_task(self._drain_stderr(process.stderr))
                if process.stdin is None:
                    raise CodexCLIImageUnavailable()
                process.stdin.write(prompt_bytes)
                await process.stdin.drain()
                process.stdin.close()
                if hasattr(process.stdin, "wait_closed"):
                    await process.stdin.wait_closed()
                try:
                    async with asyncio.timeout(self.settings.attempt_timeout_seconds):
                        turn = await self._consume_jsonl(
                            process,
                            run_id=run_id,
                            generated_root=generated_root,
                        )
                except TimeoutError as exc:
                    await self._terminate(process)
                    raise CodexCLIImageTimeout() from exc
                return self._verified_turn_image(
                    turn,
                    generated_root=generated_root,
                    not_before_ns=attempt_started_ns,
                )
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


_default_provider: CodexCLIImageProvider | None = None
_default_settings: CodexCLIImageSettings | None = None


def get_codex_cli_image_provider() -> CodexCLIImageProvider:
    global _default_provider, _default_settings
    settings = CodexCLIImageSettings.from_env()
    if _default_provider is None or _default_settings != settings:
        _default_settings = settings
        _default_provider = CodexCLIImageProvider(settings)
    return _default_provider


def codex_cli_image_configuration() -> dict[str, Any]:
    return get_codex_cli_image_provider().configuration_snapshot()


async def generate_codex_cli_image(
    prompt: str,
    *,
    size: str = "1024x1024",
    quality: str = "high",
    run_id: str | None = None,
) -> CodexCLIImageResult:
    return await get_codex_cli_image_provider().generate(
        prompt, size=size, quality=quality, run_id=run_id
    )


async def edit_codex_cli_image(
    prompt: str,
    source_image: bytes,
    *,
    size: str = "1024x1024",
    quality: str = "high",
    run_id: str | None = None,
) -> CodexCLIImageResult:
    return await get_codex_cli_image_provider().generate(
        prompt,
        size=size,
        quality=quality,
        run_id=run_id,
        source_image=source_image,
    )


async def cancel_codex_cli_image_run(run_id: str) -> bool:
    return await get_codex_cli_image_provider().cancel(run_id)
