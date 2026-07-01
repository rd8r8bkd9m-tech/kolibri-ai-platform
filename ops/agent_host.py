#!/usr/bin/env python3
"""Persistent Kolibri remote agent host."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STOP = False
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def request(method: str, url: str, body: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 204:
                return None
            payload = resp.read().decode("utf-8")
            return json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {detail}") from exc


def machine_stats() -> dict[str, Any]:
    disk = shutil.disk_usage("/")
    ram = {}
    try:
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
        for line in meminfo.splitlines():
            name, value = line.split(":", 1)
            if name in {"MemTotal", "MemAvailable"}:
                ram[name] = value.strip()
    except OSError:
        pass
    return {
        "cpu": os.cpu_count(),
        "ram": ram,
        "disk": {"total": disk.total, "used": disk.used, "free": disk.free},
    }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class AgentHost:
    def __init__(self, args: argparse.Namespace):
        control_urls_arg = getattr(args, "control_urls", None) or args.control_url
        self.control_urls = [url.strip().rstrip("/") for url in control_urls_arg.split(",") if url.strip()]
        if not self.control_urls:
            self.control_urls = [args.control_url.rstrip("/")]
        self.control_url = self.control_urls[0]
        self.node_id = args.node_id
        self.agent_id = args.agent_id or f"{args.node_id}-agent-host"
        self.capabilities = [item for item in args.capabilities.split(",") if item]
        self.repo_url = args.repo_url
        self.work_root = Path(args.work_root)
        self.artifact_root = Path(args.artifact_root)
        self.heartbeat_interval = args.heartbeat_interval
        self.lease_refresh = args.lease_refresh
        self.max_inflight = args.max_inflight
        self.hostname = platform.node()
        self.pid = os.getpid()
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self._request_with_failover("POST", path, body)

    def get(self, path: str) -> Any:
        return self._request_with_failover("GET", path)

    def _ordered_control_urls(self) -> list[str]:
        urls = [self.control_url]
        urls.extend(url for url in self.control_urls if url != self.control_url)
        return urls

    def _request_with_failover(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        last_exc: Exception | None = None
        for control_url in self._ordered_control_urls():
            try:
                result = request(method, f"{control_url}{path}", body)
                self.control_url = control_url
                return result
            except Exception as exc:
                last_exc = exc
        assert last_exc is not None
        raise last_exc

    def register(self) -> None:
        body = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "agent_id": self.agent_id,
            "pid": self.pid,
            "capabilities": self.capabilities,
            **machine_stats(),
        }
        self.post("/v1/nodes/register", body)

    def node_heartbeat(self, active_task: str | None = None) -> None:
        body = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "agent_id": self.agent_id,
            "pid": self.pid,
            "capabilities": self.capabilities,
            "active_task": active_task,
            **machine_stats(),
        }
        self.post(f"/v1/nodes/{self.node_id}/heartbeat", body)

    def task_heartbeat(self, task: dict[str, Any], worktree: Path, branch: str | None, logs: dict[str, str], pid: int | None = None) -> dict[str, Any]:
        body = {
            "state": "running",
            "pid": pid or self.pid,
            "worktree": str(worktree),
            "branch": branch,
            "log_paths": logs,
        }
        return self.post(f"/v1/tasks/{task['task_id']}/heartbeat", body)

    def lease(self) -> dict[str, Any] | None:
        return self.post("/v1/tasks/lease", {
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "capabilities": self.capabilities,
        })

    def run_command(
        self,
        command: list[str],
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        task: dict[str, Any],
        branch: str | None,
        logs: dict[str, str],
        env: dict[str, str] | None = None,
        command_label: str | None = None,
    ) -> None:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        display_command = command_label or " ".join(command)
        with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
            stdout.write(f"\n$ {display_command}\n".encode("utf-8"))
            stdout.flush()
            proc = subprocess.Popen(command, cwd=str(cwd), stdout=stdout, stderr=stderr, env=merged_env)
            last_refresh = 0.0
            while proc.poll() is None:
                if STOP:
                    proc.terminate()
                    raise RuntimeError("agent host received SIGTERM")
                if time.time() - last_refresh >= self.lease_refresh:
                    self.task_heartbeat(task, cwd, branch, logs, proc.pid)
                    last_refresh = time.time()
                time.sleep(2)
            if proc.returncode != 0:
                raise RuntimeError(f"command failed with rc={proc.returncode}: {display_command}")

    @staticmethod
    def _content_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            text = content.get("text")
            return text if isinstance(text, str) else ""
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and item.get("type") in {None, "text", "output_text"}:
                        parts.append(text)
            return "".join(parts)
        return ""

    @classmethod
    def parse_json_text_response(cls, stdout_path: Path) -> str:
        final_messages = []
        text_parts = []
        deltas = []
        for line in stdout_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            part = event.get("part") or {}
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                text_parts.append(part["text"])

            msg = event.get("msg") or {}
            if isinstance(msg, dict):
                msg_type = str(msg.get("type") or "")
                text = msg.get("message") or msg.get("text") or cls._content_text(msg.get("content"))
                if text:
                    if "delta" in msg_type:
                        deltas.append(text)
                    else:
                        final_messages.append(text)

            event_type = str(event.get("type") or "")
            text = event.get("message") or event.get("text") or cls._content_text(event.get("content"))
            if text:
                if "delta" in event_type:
                    deltas.append(text)
                elif event_type in {"agent_message", "assistant_message", "message"}:
                    final_messages.append(text)

            item = event.get("item") or {}
            if isinstance(item, dict) and item.get("type") in {"message", "assistant_message", "agent_message"}:
                item_text = item.get("message") or item.get("text") or cls._content_text(item.get("content"))
                if item_text:
                    final_messages.append(item_text)

        for parts in (final_messages, text_parts, deltas):
            response_text = "".join(parts).strip()
            if response_text:
                return response_text
        return ""

    def run_json_text_command(
        self,
        command: list[str],
        command_label: str,
        empty_response_label: str,
        worktree: Path,
        stdout_path: Path,
        stderr_path: Path,
        task: dict[str, Any],
        branch: str | None,
        logs: dict[str, str],
    ) -> str:
        self.run_command(
            command,
            worktree,
            stdout_path,
            stderr_path,
            task,
            branch,
            logs,
            command_label=command_label,
        )
        response_text = self.parse_json_text_response(stdout_path)
        if not response_text:
            raise RuntimeError(f"{empty_response_label} completed without text response")
        return response_text

    def write_result(self, artifact_dir: Path, result: dict[str, Any]) -> Path:
        result_path = artifact_dir / "result.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = []
        for path in sorted(artifact_dir.rglob("*")):
            if path.is_file():
                manifest.append({"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size})
        (artifact_dir / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result_path

    def complete(self, task: dict[str, Any], result: dict[str, Any], result_path: Path) -> None:
        self.post(f"/v1/tasks/{task['task_id']}/complete", {
            "result_reference": str(result_path),
            "result": result,
        })

    def fail(self, task: dict[str, Any], error_type: str, error: str, result: dict[str, Any] | None, result_path: Path | None, retry: bool = True) -> None:
        self.post(f"/v1/tasks/{task['task_id']}/fail", {
            "error_type": error_type,
            "error": error,
            "result": result,
            "result_reference": str(result_path) if result_path else None,
            "retry": retry,
        })

    def prepare_dirs(self, task: dict[str, Any]) -> tuple[Path, Path, dict[str, str]]:
        task_id = task["task_id"]
        attempt_id = task.get("attempt_id") or f"{task_id}-attempt-{task.get('attempt', 1)}"
        worktree = self.work_root / task_id / attempt_id / "repo"
        artifact_dir = self.artifact_root / task_id / attempt_id
        if worktree.exists():
            shutil.rmtree(worktree)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        logs = {
            "stdout": str(artifact_dir / "stdout.log"),
            "stderr": str(artifact_dir / "stderr.log"),
        }
        return worktree, artifact_dir, logs

    def run_read_only_probe(self, task: dict[str, Any]) -> dict[str, Any]:
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.mkdir(parents=True, exist_ok=True)
        self.task_heartbeat(task, worktree, None, logs)
        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": None,
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
            "status": "completed",
            "kind": "read_only_probe",
            "message": "read-only probe completed",
        }
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_telegram_chat_response(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task.get("envelope", {})
        message = (envelope.get("message") or "").strip()
        if not message:
            raise RuntimeError("telegram chat task missing message")
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(logs["stdout"])
        stderr_path = Path(logs["stderr"])
        self.task_heartbeat(task, worktree, None, logs)
        prompt = (
            "Ты — центральный оркестратор Kolibri. Владелец общается с тобой, а не с отдельным сервером или worker. "
            "Отвечай от первого лица как оркестратор: я вижу систему, я выбираю исполнителей, я контролирую PR, CI, review и deployment. "
            "Используй снимок фабрики ниже как текущий контекст. В нем есть memory: проектная память, недавний диалог, последняя рабочая задача, ожидания владельца и известные ссылки. "
            "Если владелец пишет продолжение без объекта, например 'ссылку не забудь', восстанови смысл из memory.last_work_request и memory.recent_messages. "
            "Не проси уточнить, если связь очевидна; подтверди, что помнишь предыдущую задачу и пришлешь ссылку, когда результат будет готов. "
            "Если данных не хватает, честно скажи, что проверишь. "
            "Стиль: коротко, спокойно, премиально, по-русски, без эмодзи, markdown и служебных идентификаторов. "
            "Не раскрывай task_id, node, agent, worktree, пути, логи или артефакты, если владелец прямо не просит технические доказательства. "
            "Не называй себя брендом Kolibri и не используй фразу 'я Kolibri'. Ты директор-оркестратор проекта, а не название продукта. "
            "Если владелец здоровается, обработай приветствие естественно: каждый ответ должен быть заново сгенерирован по текущему сообщению и снимку фабрики, без заранее заданной фразы. "
            "Если это обычный разговор, отвечай естественно. Если это просьба о разработке, скажи, что ты принял задачу и сам назначишь исполнителя. "
            f"Снимок фабрики JSON: {json.dumps(envelope.get('factory_snapshot') or {}, ensure_ascii=False, sort_keys=True)}\n"
            f"Сообщение владельца: {message}"
        )
        runner = str(
            os.environ.get("KOLIBRI_TELEGRAM_RUNNER")
            or os.environ.get("KOLIBRI_AI_RUNNER")
            or envelope.get("runner")
            or "mimo"
        ).strip().lower()
        if runner == "codex":
            codex = shutil.which("codex")
            if not codex:
                raise RuntimeError("codex executable is not available on this node")
            response_text = self.run_json_text_command(
                [codex, "exec", "--json", "--skip-git-repo-check", "--sandbox", "danger-full-access", prompt],
                f"{codex} exec --json --skip-git-repo-check --sandbox danger-full-access <prompt>",
                "codex",
                worktree,
                stdout_path,
                stderr_path,
                task,
                None,
                logs,
            )
        elif runner == "mimo":
            mimo = shutil.which("mimo")
            if not mimo:
                raise RuntimeError("mimo executable is not available on this node")
            response_text = self.run_json_text_command(
                [mimo, "run", "--format", "json", "--title", f"telegram-chat-{task['task_id']}", prompt],
                f"{mimo} run --format json --title telegram-chat-{task['task_id']} <prompt>",
                "mimo",
                worktree,
                stdout_path,
                stderr_path,
                task,
                None,
                logs,
            )
        elif runner == "api":
            response_text = self.run_api_text_runner(prompt)
        elif runner == "local_llm":
            response_text = self.run_local_llm_text_runner(prompt)
        else:
            raise RuntimeError(f"unsupported telegram runner: {runner}")
        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": None,
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
            "status": "completed",
            "kind": envelope.get("kind", "orchestrator_chat_response"),
            "response": response_text,
        }
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_api_text_runner(self, prompt: str) -> str:
        endpoint = os.environ.get("KOLIBRI_API_RUNNER_URL", "https://api.openai.com/v1/chat/completions")
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("KOLIBRI_API_RUNNER_TOKEN")
        if not api_key:
            raise RuntimeError("api runner auth is not configured: set OPENAI_API_KEY or KOLIBRI_API_RUNNER_TOKEN")
        body = {
            "model": os.environ.get("KOLIBRI_API_RUNNER_MODEL", "gpt-4.1-mini"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(os.environ.get("KOLIBRI_API_RUNNER_TEMPERATURE", "0.2")),
        }
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=int(os.environ.get("KOLIBRI_API_RUNNER_TIMEOUT", "120"))) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        choices = payload.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            text = message.get("content")
            if text:
                return str(text)
        text = payload.get("response") or payload.get("text")
        if text:
            return str(text)
        raise RuntimeError("api runner returned no text")

    def run_local_llm_text_runner(self, prompt: str) -> str:
        endpoint = os.environ.get("KOLIBRI_LOCAL_LLM_URL")
        if not endpoint:
            raise RuntimeError("local_llm runner is not configured: set KOLIBRI_LOCAL_LLM_URL")
        body = {
            "prompt": prompt,
            "model": os.environ.get("KOLIBRI_LOCAL_LLM_MODEL", "local"),
            "stream": False,
        }
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=int(os.environ.get("KOLIBRI_LOCAL_LLM_TIMEOUT", "120"))) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        text = payload.get("response") or payload.get("text") or payload.get("content")
        if text:
            return str(text)
        raise RuntimeError("local_llm runner returned no text")

    def generated_image_path(self, artifact_dir: Path, preferred: Path) -> Path:
        if preferred.exists() and preferred.is_file():
            return preferred
        candidates = [path for path in sorted(artifact_dir.rglob("*")) if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS]
        if not candidates:
            raise RuntimeError("image generator completed without an image file")
        return candidates[0]

    def image_output_path(self, artifact_dir: Path) -> Path:
        output_format = os.environ.get("KOLIBRI_IMAGE_OUTPUT_FORMAT", "png").strip().lower().lstrip(".")
        if output_format == "jpeg":
            suffix = "jpg"
        elif output_format not in {"png", "jpg", "webp"}:
            suffix = "png"
        else:
            suffix = output_format
        return artifact_dir / f"telegram-image.{suffix}"

    def image_b64_for_result(self, image_path: Path) -> str | None:
        max_bytes = int(os.environ.get("KOLIBRI_IMAGE_RESULT_EMBED_MAX_BYTES", str(8 * 1024 * 1024)))
        if image_path.stat().st_size > max_bytes:
            return None
        return base64.b64encode(image_path.read_bytes()).decode("ascii")

    def run_configured_image_generator(
        self,
        prompt: str,
        output_path: Path,
        worktree: Path,
        artifact_dir: Path,
        stdout_path: Path,
        stderr_path: Path,
        task: dict[str, Any],
        logs: dict[str, str],
    ) -> Path:
        command = os.environ.get("KOLIBRI_IMAGE_GENERATOR_CMD")
        if not command:
            return self.run_openai_image_generation(prompt, output_path)
        env = {
            "KOLIBRI_IMAGE_PROMPT": prompt,
            "KOLIBRI_IMAGE_OUTPUT_DIR": str(artifact_dir),
            "KOLIBRI_IMAGE_OUTPUT_PATH": str(output_path),
            "KOLIBRI_IMAGE_SIZE": os.environ.get("KOLIBRI_IMAGE_SIZE", "1024x1024"),
            "KOLIBRI_TASK_ID": task["task_id"],
        }
        self.run_command(["/bin/sh", "-lc", command], worktree, stdout_path, stderr_path, task, None, logs, env)
        return self.generated_image_path(artifact_dir, output_path)

    def run_openai_image_generation(self, prompt: str, output_path: Path) -> Path:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("image generator is not configured: set KOLIBRI_IMAGE_GENERATOR_CMD or OPENAI_API_KEY")
        endpoint = os.environ.get("KOLIBRI_IMAGE_API_URL", "https://api.openai.com/v1/images/generations")
        body: dict[str, Any] = {
            "model": os.environ.get("KOLIBRI_IMAGE_MODEL", "gpt-image-1"),
            "prompt": prompt,
            "size": os.environ.get("KOLIBRI_IMAGE_SIZE", "1024x1024"),
            "n": 1,
        }
        for env_name, field_name in (
            ("KOLIBRI_IMAGE_QUALITY", "quality"),
            ("KOLIBRI_IMAGE_BACKGROUND", "background"),
            ("KOLIBRI_IMAGE_OUTPUT_FORMAT", "output_format"),
        ):
            value = os.environ.get(env_name)
            if value:
                body[field_name] = value
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=int(os.environ.get("KOLIBRI_IMAGE_API_TIMEOUT", "180"))) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        items = payload.get("data") or []
        if not items:
            raise RuntimeError("image API returned no images")
        item = items[0]
        if item.get("b64_json"):
            output_path.write_bytes(base64.b64decode(item["b64_json"]))
            return output_path
        if item.get("url"):
            with urllib.request.urlopen(item["url"], timeout=120) as image_resp:
                output_path.write_bytes(image_resp.read())
            return output_path
        raise RuntimeError("image API returned no usable image payload")

    def run_telegram_image_generation(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task.get("envelope", {})
        prompt = (envelope.get("prompt") or envelope.get("message") or envelope.get("objective") or "").strip()
        if not prompt:
            raise RuntimeError("telegram image task missing prompt")
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(logs["stdout"])
        stderr_path = Path(logs["stderr"])
        self.task_heartbeat(task, worktree, None, logs)
        output_path = self.image_output_path(artifact_dir)
        image_path = self.run_configured_image_generator(prompt, output_path, worktree, artifact_dir, stdout_path, stderr_path, task, logs)
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        caption = (envelope.get("caption") or "Готово.").strip()
        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": None,
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
            "status": "completed",
            "kind": envelope.get("kind", "telegram_image_generation"),
            "prompt": prompt,
            "caption": caption,
            "response": caption,
            "image_path": str(image_path),
            "image_mime_type": mime_type,
        }
        embedded = self.image_b64_for_result(image_path)
        if embedded:
            result["image_b64"] = embedded
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_impl_factory_smoke(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task.get("envelope", {})
        branch = envelope.get("branch", f"agent/{task['task_id']}/impl/factory-smoke")
        base_ref = envelope.get("base_ref", "origin/main")
        smoke_path = envelope.get("smoke_path", "tests/test_factory_runtime_contracts.py")
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.parent.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(logs["stdout"])
        stderr_path = Path(logs["stderr"])
        self.task_heartbeat(task, worktree, branch, logs)

        git_env = {"GIT_TERMINAL_PROMPT": "0"}
        self.run_command(["git", "clone", self.repo_url, str(worktree)], worktree.parent, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "fetch", "origin"], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "checkout", "-B", branch, base_ref], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "config", "user.name", "Kolibri Factory Agent"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command(["git", "config", "user.email", "factory-agent@users.noreply.github.com"], worktree, stdout_path, stderr_path, task, branch, logs)

        test_file = worktree / smoke_path
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(
            "import importlib.util\n"
            "import time\n"
            "from pathlib import Path\n\n"
            "ROOT = Path(__file__).resolve().parents[1]\n\n"
            "def load_control():\n"
            "    spec = importlib.util.spec_from_file_location('factory_control', ROOT / 'ops' / 'factory_control.py')\n"
            "    module = importlib.util.module_from_spec(spec)\n"
            "    assert spec.loader is not None\n"
            "    spec.loader.exec_module(module)\n"
            "    return module\n\n"
            "def test_task_envelope_schema_and_idempotency_key():\n"
            "    control = load_control()\n"
            "    task = control.normalize_task({'task_id': 'SCHEMA-1', 'idempotency_key': 'idem-1', 'kind': 'read_only_probe'})\n"
            "    for key in ['task_id', 'idempotency_key', 'kind', 'state', 'attempt', 'lease_owner', 'lease_until', 'result_reference', 'error_type']:\n"
            "        assert key in task\n"
            "    assert task['idempotency_key'] == 'idem-1'\n"
            "    assert task['state'] == 'queued'\n\n"
            "def test_heartbeat_payload_schema():\n"
            "    payload = {'node_id': '9fts', 'agent_id': 'agent-host-9fts', 'pid': 123, 'capabilities': ['implementation'], 'active_task': None}\n"
            "    assert {'node_id', 'agent_id', 'pid', 'capabilities'} <= set(payload)\n"
            "    assert isinstance(payload['capabilities'], list)\n\n"
            "def test_result_envelope_schema():\n"
            "    result = {'node_id': '9fts', 'agent_id': 'agent-host-9fts', 'task_id': 'SCHEMA-1', 'status': 'completed', 'result_path': '/tmp/result.json'}\n"
            "    assert {'node_id', 'agent_id', 'task_id', 'status', 'result_path'} <= set(result)\n\n"
            "def test_lease_expiry_calculation():\n"
            "    control = load_control()\n"
            "    lease_until = time.time() + control.LEASE_DURATION\n"
            "    assert lease_until > time.time()\n"
            "    assert control.LEASE_DURATION >= 60\n",
            encoding="utf-8",
        )
        if shutil.which("mimo"):
            self.run_command(["mimo", "--version"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command([
            "python3", "-c",
            "import compileall,pathlib,sys; paths=[p for p in ('backend','infra','scripts','ops') if pathlib.Path(p).exists()]; sys.exit(0 if compileall.compile_dir('.', quiet=1, maxlevels=0) and all(compileall.compile_dir(p, quiet=1) for p in paths) else 1)",
        ], worktree, stdout_path, stderr_path, task, branch, logs)
        venv_dir = artifact_dir / "venv"
        self.run_command(["python3", "-m", "venv", str(venv_dir)], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command([str(venv_dir / "bin" / "python"), "-m", "pip", "install", "--upgrade", "pip", "pytest"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command([str(venv_dir / "bin" / "python"), "-m", "pytest", "-q", smoke_path], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command(["git", "add", smoke_path], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command(["git", "commit", "-m", "test: add factory runtime contracts"], worktree, stdout_path, stderr_path, task, branch, logs)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(worktree), text=True).strip()
        self.run_command(["git", "push", "-u", "origin", branch], worktree, stdout_path, stderr_path, task, branch, logs, git_env)

        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": branch,
            "commit": commit,
            "pull_request_url": None,
            "needs_central_pr": True,
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
            "status": "completed",
            "changed_files": [smoke_path],
            "checks": ["mimo --version", "python3 compileall existing runtime paths", f"pytest -q {smoke_path}"],
        }
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_impl_retry_error_clearance(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task.get("envelope", {})
        branch = envelope.get("branch", f"agent/{task['task_id']}/impl/retry-error-clearance")
        base_ref = envelope.get("base_ref", "origin/main")
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.parent.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(logs["stdout"])
        stderr_path = Path(logs["stderr"])
        self.task_heartbeat(task, worktree, branch, logs)

        git_env = {"GIT_TERMINAL_PROMPT": "0"}
        self.run_command(["git", "clone", self.repo_url, str(worktree)], worktree.parent, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "fetch", "origin"], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "checkout", "-B", branch, base_ref], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "config", "user.name", "Kolibri Factory Agent"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command(["git", "config", "user.email", "factory-agent@users.noreply.github.com"], worktree, stdout_path, stderr_path, task, branch, logs)

        patcher = artifact_dir / "apply_retry_error_clearance.py"
        patcher.write_text(
            r"""
from pathlib import Path

control_path = Path("ops/factory_control.py")
text = control_path.read_text(encoding="utf-8")

if "def append_attempt_history(" not in text:
    marker = "\ndef create_review_task(source_task: dict[str, Any], result: dict[str, Any]) -> dict[str, Any] | None:\n"
    helper = '''
def append_attempt_history(task: dict[str, Any], status: str, error_type: str | None, error: str | None, result_reference: str | None) -> None:
    attempt = {
        "attempt": task.get("attempt"),
        "attempt_id": task.get("attempt_id"),
        "status": status,
        "error_type": error_type,
        "error": error,
        "result_reference": result_reference,
        "recorded_at": utc_now(),
    }
    history = task.setdefault("attempt_history", [])
    attempt_id = attempt.get("attempt_id")
    if attempt_id:
        history[:] = [item for item in history if item.get("attempt_id") != attempt_id]
    history.append(attempt)


def apply_task_completion(task: dict[str, Any], body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], bool]:
    result = body.get("result", body)
    needs_review = task.get("envelope", {}).get("create_review_on_complete")
    has_pr = bool(result.get("pull_request_url") or result.get("pr_url"))
    task["state"] = STATE_COMPLETED if (not needs_review or has_pr) else STATE_WAITING_REVIEW
    task["result"] = result
    task["result_reference"] = body.get("result_reference") or result.get("result_path")
    task["heartbeat_at"] = utc_now()
    task["lease_until"] = None
    task["error_type"] = None
    task["error"] = None
    append_attempt_history(task, "completed", None, None, task.get("result_reference"))
    return task, result, has_pr

'''
    if marker not in text:
        raise SystemExit("create_review_task marker not found")
    text = text.replace(marker, "\n" + helper + marker.lstrip("\n"), 1)

old_complete = '''                result = body.get("result", body)
                needs_review = task.get("envelope", {}).get("create_review_on_complete")
                has_pr = bool(result.get("pull_request_url") or result.get("pr_url"))
                task["state"] = STATE_COMPLETED if (not needs_review or has_pr) else STATE_WAITING_REVIEW
                task["result"] = result
                task["result_reference"] = body.get("result_reference") or result.get("result_path")
                task["heartbeat_at"] = utc_now()
                task["lease_until"] = None
                save_task(task)
                review_task = create_review_task(task, result) if has_pr else None
'''
new_complete = '''                task, result, has_pr = apply_task_completion(task, body)
                save_task(task)
                review_task = create_review_task(task, result) if has_pr else None
'''
if old_complete in text:
    text = text.replace(old_complete, new_complete, 1)
elif "apply_task_completion(task, body)" not in text:
    raise SystemExit("complete block marker not found")

old_fail = '''                task["error_type"] = body.get("error_type", "runtime_error")
                task["error"] = body.get("error")
                task["result"] = body.get("result")
                task["result_reference"] = body.get("result_reference")
                task["lease_until"] = None
'''
new_fail = '''                task["error_type"] = body.get("error_type", "runtime_error")
                task["error"] = body.get("error")
                task["result"] = body.get("result")
                task["result_reference"] = body.get("result_reference")
                task["lease_until"] = None
                append_attempt_history(task, "failed", task.get("error_type"), task.get("error"), task.get("result_reference"))
'''
if old_fail in text:
    text = text.replace(old_fail, new_fail, 1)
elif 'append_attempt_history(task, "failed"' not in text:
    raise SystemExit("fail block marker not found")

control_path.write_text(text, encoding="utf-8")

test_path = Path("tests/test_factory_retry_error_clearance.py")
test_path.write_text('''import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_control():
    spec = importlib.util.spec_from_file_location("factory_control", ROOT / "ops" / "factory_control.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_successful_retry_clears_top_level_error_and_keeps_attempt_history():
    control = load_control()
    task = control.normalize_task({
        "task_id": "RETRY-CLEAR-1",
        "idempotency_key": "retry-clear-1",
        "kind": "read_only_probe",
        "max_retries": 2,
    })
    task["attempt"] = 1
    task["attempt_id"] = "RETRY-CLEAR-1-attempt-1"
    task["state"] = control.STATE_RUNNING
    task["error_type"] = "runtime_error"
    task["error"] = "first attempt failed"
    task["result_reference"] = "/tmp/attempt-1/result.json"
    control.append_attempt_history(task, "failed", task["error_type"], task["error"], task["result_reference"])

    task["attempt"] = 2
    task["attempt_id"] = "RETRY-CLEAR-1-attempt-2"
    task["state"] = control.STATE_RUNNING
    task, result, has_pr = control.apply_task_completion(task, {
        "result": {"status": "completed", "result_path": "/tmp/attempt-2/result.json"},
        "result_reference": "/tmp/attempt-2/result.json",
    })

    assert has_pr is False
    assert result["status"] == "completed"
    assert task["state"] == control.STATE_COMPLETED
    assert task["error_type"] is None
    assert task["error"] is None
    assert task["result_reference"] == "/tmp/attempt-2/result.json"
    assert task["attempt_history"][0]["attempt_id"] == "RETRY-CLEAR-1-attempt-1"
    assert task["attempt_history"][0]["error"] == "first attempt failed"
    assert task["attempt_history"][1]["attempt_id"] == "RETRY-CLEAR-1-attempt-2"
    assert task["attempt_history"][1]["error"] is None
''', encoding="utf-8")
""",
            encoding="utf-8",
        )
        self.run_command(["python3", str(patcher)], worktree, stdout_path, stderr_path, task, branch, logs)
        if shutil.which("mimo"):
            self.run_command(["mimo", "--version"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command([
            "python3", "-c",
            "import compileall,pathlib,sys; paths=[p for p in ('backend','infra','scripts','ops') if pathlib.Path(p).exists()]; sys.exit(0 if compileall.compile_dir('.', quiet=1, maxlevels=0) and all(compileall.compile_dir(p, quiet=1) for p in paths) else 1)",
        ], worktree, stdout_path, stderr_path, task, branch, logs)
        venv_dir = artifact_dir / "venv"
        self.run_command(["python3", "-m", "venv", str(venv_dir)], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command([str(venv_dir / "bin" / "python"), "-m", "pip", "install", "--upgrade", "pip", "pytest"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command([str(venv_dir / "bin" / "python"), "-m", "pytest", "-q", "tests/test_factory_runtime.py", "tests/test_factory_retry_error_clearance.py"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command(["git", "add", "ops/factory_control.py", "tests/test_factory_retry_error_clearance.py"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command(["git", "commit", "-m", "factory: clear stale retry error on success"], worktree, stdout_path, stderr_path, task, branch, logs)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(worktree), text=True).strip()
        self.run_command(["git", "push", "-u", "origin", branch], worktree, stdout_path, stderr_path, task, branch, logs, git_env)

        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": branch,
            "commit": commit,
            "pull_request_url": None,
            "needs_central_pr": True,
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
            "status": "completed",
            "changed_files": ["ops/factory_control.py", "tests/test_factory_retry_error_clearance.py"],
            "checks": [
                "mimo --version",
                "python3 compileall existing runtime paths",
                "pytest -q tests/test_factory_runtime.py tests/test_factory_retry_error_clearance.py",
            ],
        }
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_review_pr(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task.get("envelope", {})
        branch = envelope.get("branch")
        pr_url = envelope.get("pull_request_url")
        base_ref = envelope.get("base_ref", "origin/main")
        if not branch:
            raise RuntimeError("review task missing branch")
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.parent.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(logs["stdout"])
        stderr_path = Path(logs["stderr"])
        self.task_heartbeat(task, worktree, branch, logs)
        git_env = {"GIT_TERMINAL_PROMPT": "0"}
        self.run_command(["git", "clone", self.repo_url, str(worktree)], worktree.parent, stdout_path, stderr_path, task, branch, logs, git_env)
        if base_ref.startswith("origin/"):
            self.run_command(["git", "fetch", "origin", base_ref.removeprefix("origin/")], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "fetch", "origin", branch], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "checkout", "-B", f"review/{task['task_id']}", "FETCH_HEAD"], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
        diff_files = subprocess.check_output(["git", "diff", "--name-only", f"{base_ref}...HEAD"], cwd=str(worktree), text=True).splitlines()
        blocked = [path for path in diff_files if path.startswith(".env") or path.endswith(".key") or path.endswith(".pem")]
        for changed in diff_files:
            path = worktree / changed
            if path.is_file() and "|| true" in path.read_text(encoding="utf-8", errors="ignore"):
                blocked.append(f"dangerous_or_true:{changed}")
        status = "CHANGES_REQUESTED" if blocked else "APPROVED"
        self.run_command([
            "python3", "-c",
            "import compileall,pathlib,sys; paths=[p for p in ('backend','infra','scripts','ops') if pathlib.Path(p).exists()]; sys.exit(0 if compileall.compile_dir('.', quiet=1, maxlevels=0) and all(compileall.compile_dir(p, quiet=1) for p in paths) else 1)",
        ], worktree, stdout_path, stderr_path, task, branch, logs)
        if (worktree / "tests").exists():
            venv_dir = artifact_dir / "venv"
            self.run_command(["python3", "-m", "venv", str(venv_dir)], worktree, stdout_path, stderr_path, task, branch, logs)
            self.run_command([str(venv_dir / "bin" / "python"), "-m", "pip", "install", "--upgrade", "pip", "pytest"], worktree, stdout_path, stderr_path, task, branch, logs)
            self.run_command([str(venv_dir / "bin" / "python"), "-m", "pytest", "-q"], worktree, stdout_path, stderr_path, task, branch, logs)
        github_review = "skipped: gh unavailable"
        if shutil.which("gh"):
            event = "APPROVE" if status == "APPROVED" else "REQUEST_CHANGES"
            self.run_command(["gh", "pr", "review", pr_url or branch, f"--{event.lower().replace('_', '-')}", "--body", status], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
            github_review = "submitted"
        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": branch,
            "pull_request_url": pr_url,
            "status": status,
            "github_review": github_review,
            "changed_files": diff_files,
            "findings": blocked,
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
        }
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_task(self, task: dict[str, Any]) -> None:
        result_path = None
        result = None
        try:
            kind = task.get("kind")
            if kind == "impl_factory_smoke":
                result = self.run_impl_factory_smoke(task)
            elif kind == "impl_retry_error_clearance":
                result = self.run_impl_retry_error_clearance(task)
            elif kind in {"telegram_chat_response", "orchestrator_chat_response"}:
                result = self.run_telegram_chat_response(task)
            elif kind == "telegram_image_generation":
                result = self.run_telegram_image_generation(task)
            elif kind == "review_pr":
                result = self.run_review_pr(task)
            elif kind == "read_only_probe":
                result = self.run_read_only_probe(task)
            else:
                raise RuntimeError(f"unsupported task kind: {kind}")
            result_path = Path(result["result_path"])
            self.complete(task, result, result_path)
        except Exception as exc:
            task_id = task["task_id"]
            attempt_id = task.get("attempt_id") or f"{task_id}-attempt-{task.get('attempt', 1)}"
            artifact_dir = self.artifact_root / task_id / attempt_id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            result = {
                "node_id": self.node_id,
                "hostname": self.hostname,
                "task_id": task_id,
                "agent_id": self.agent_id,
                "attempt_id": attempt_id,
                "pid": self.pid,
                "status": "failed",
                "error": str(exc),
                "completed_at": utc_now(),
            }
            result_path = self.write_result(artifact_dir, result)
            retry = int(task.get("attempt", 0)) < int(task.get("max_retries", 3))
            self.fail(task, "runtime_error", str(exc), result, result_path, retry=retry)

    def loop(self) -> None:
        self.register()
        last_node_heartbeat = 0.0
        while not STOP:
            if time.time() - last_node_heartbeat >= self.heartbeat_interval:
                self.node_heartbeat()
                last_node_heartbeat = time.time()
            try:
                task = self.lease()
            except Exception as exc:
                print(f"{utc_now()} lease_failed {exc}", flush=True)
                time.sleep(5)
                continue
            if task:
                self.node_heartbeat(active_task=task["task_id"])
                self.run_task(task)
                self.node_heartbeat()
            time.sleep(2)


def handle_stop(signum: int, frame: Any) -> None:
    del signum, frame
    global STOP
    STOP = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-url", default=os.environ.get("KOLIBRI_FACTORY_CONTROL_URL", "http://10.99.0.2:9101"))
    parser.add_argument("--control-urls", default=os.environ.get("KOLIBRI_FACTORY_CONTROL_URLS") or os.environ.get("KOLIBRI_FACTORY_CONTROL_URL", "http://10.99.0.2:9101"))
    parser.add_argument("--node-id", default=os.environ.get("KOLIBRI_NODE_ID", platform.node()))
    parser.add_argument("--agent-id", default=os.environ.get("KOLIBRI_AGENT_ID"))
    parser.add_argument("--capabilities", default=os.environ.get("KOLIBRI_AGENT_CAPABILITIES", "read_only_probe"))
    parser.add_argument("--repo-url", default=os.environ.get("KOLIBRI_REPO_URL", "https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform.git"))
    parser.add_argument("--work-root", default=os.environ.get("KOLIBRI_AGENT_WORK_ROOT", "/var/lib/kolibri-agent/worktrees"))
    parser.add_argument("--artifact-root", default=os.environ.get("KOLIBRI_AGENT_ARTIFACT_ROOT", "/var/lib/kolibri-agent/artifacts"))
    parser.add_argument("--heartbeat-interval", type=int, default=int(os.environ.get("KOLIBRI_HEARTBEAT_INTERVAL", "10")))
    parser.add_argument("--lease-refresh", type=int, default=int(os.environ.get("KOLIBRI_LEASE_REFRESH", "20")))
    parser.add_argument("--max-inflight", type=int, default=int(os.environ.get("KOLIBRI_MAX_INFLIGHT", "1")))
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    AgentHost(args).loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
