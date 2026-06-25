"""Persistent owner-facing memory for the Kolibri Telegram orchestrator."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


MAX_RECENT_MESSAGES = 16
MAX_EXPECTATIONS = 12
MAX_KNOWN_RESULTS = 12

DEFAULT_PROJECT_CONTEXT = {
    "identity": "Удаленный директор-оркестратор Kolibri живет на control node и отвечает владельцу даже при закрытом MacBook.",
    "owner_interface": "Владелец пишет обычным русским языком в Telegram; служебные команды не требуются.",
    "current_focus": "Factory MVP, Telegram -> Factory, удаленные исполнители, premium miniapp/webapp и прозрачная разработка.",
    "operating_model": [
        "Директор держит общий контекст разработки и решает, кому отдавать задачи.",
        "Инженер выполняет изменения в отдельном worktree.",
        "Ревьюер независимо проверяет изменения.",
        "Владелец получает человеческие статусы, ссылки и результат, а не внутренние артефакты.",
    ],
    "stable_services": [
        "kolibri-factory-control.service на control node",
        "kolibri-telegram-gateway.service на control node",
        "kolibri-agent-host.service на 9fts и new",
    ],
}


def empty_memory() -> dict[str, Any]:
    return {
        "version": 1,
        "project": deepcopy(DEFAULT_PROJECT_CONTEXT),
        "recent_messages": [],
        "last_work_request": None,
        "open_expectations": [],
        "known_results": [],
    }


def ensure_memory(root: dict[str, Any]) -> dict[str, Any]:
    memory = root.get("memory")
    if not isinstance(memory, dict):
        memory = empty_memory()
        root["memory"] = memory
    memory.setdefault("version", 1)
    project = memory.setdefault("project", {})
    for key, value in DEFAULT_PROJECT_CONTEXT.items():
        project.setdefault(key, deepcopy(value))
    memory.setdefault("recent_messages", [])
    memory.setdefault("last_work_request", None)
    memory.setdefault("open_expectations", [])
    memory.setdefault("known_results", [])
    return memory


def infer_expectations(text: str) -> list[dict[str, str]]:
    lowered = text.lower()
    expectations: list[dict[str, str]] = []
    if any(word in lowered for word in ["ссыл", "url", "линк", "link"]):
        expectations.append({"kind": "link", "text": "не забыть прислать владельцу ссылку на результат"})
    if any(word in lowered for word in ["запусти", "разверни", "деплой", "deploy", "вебприлож", "миниапп", "miniapp", "preview"]):
        expectations.append({"kind": "preview", "text": "после запуска вернуть владельцу preview/staging ссылку"})
    if any(word in lowered for word in ["скрин", "screenshot", "визуал"]):
        expectations.append({"kind": "screenshot", "text": "после UI-изменения показать визуальное подтверждение"})
    seen = set()
    unique = []
    for item in expectations:
        if item["kind"] not in seen:
            seen.add(item["kind"])
            unique.append(item)
    return unique


def _trim(items: list[Any], limit: int) -> list[Any]:
    return items[-limit:]


def _append_unique_expectations(memory: dict[str, Any], expectations: list[dict[str, str]], source_text: str, at: str) -> None:
    existing = {item.get("kind") for item in memory.get("open_expectations", [])}
    for item in expectations:
        if item["kind"] in existing:
            continue
        memory.setdefault("open_expectations", []).append({
            "kind": item["kind"],
            "text": item["text"],
            "source_text": source_text,
            "status": "open",
            "created_at": at,
        })
        existing.add(item["kind"])
    memory["open_expectations"] = _trim(memory.get("open_expectations", []), MAX_EXPECTATIONS)


def record_owner_message(memory: dict[str, Any], text: str, intent: str, at: str) -> None:
    memory.setdefault("recent_messages", []).append({
        "role": "owner",
        "intent": intent,
        "text": text,
        "at": at,
    })
    memory["recent_messages"] = _trim(memory["recent_messages"], MAX_RECENT_MESSAGES)
    _append_unique_expectations(memory, infer_expectations(text), text, at)


def record_orchestrator_message(memory: dict[str, Any], text: str, at: str) -> None:
    memory.setdefault("recent_messages", []).append({
        "role": "orchestrator",
        "intent": "reply",
        "text": text,
        "at": at,
    })
    memory["recent_messages"] = _trim(memory["recent_messages"], MAX_RECENT_MESSAGES)


def record_work_task(memory: dict[str, Any], text: str, task_id: str, state: str, at: str) -> None:
    expectations = infer_expectations(text)
    memory["last_work_request"] = {
        "text": text,
        "task_id": task_id,
        "state": state,
        "accepted_at": at,
        "updated_at": at,
        "expectations": expectations,
    }
    _append_unique_expectations(memory, expectations, text, at)


def record_task_transition(memory: dict[str, Any], task: dict[str, Any], label: str, at: str) -> None:
    task_id = task.get("task_id")
    last = memory.get("last_work_request")
    if isinstance(last, dict) and last.get("task_id") == task_id:
        last["state"] = task.get("state")
        last["last_transition"] = label
        last["updated_at"] = at
    result = task.get("result") or {}
    urls = []
    for key in ["pull_request_url", "pr_url", "preview_url", "staging_url", "health_url", "url"]:
        value = result.get(key)
        if value:
            urls.append({"kind": key, "url": value, "task_id": task_id, "captured_at": at})
    if urls:
        memory.setdefault("known_results", []).extend(urls)
        memory["known_results"] = _trim(memory["known_results"], MAX_KNOWN_RESULTS)


def memory_snapshot(memory: dict[str, Any]) -> dict[str, Any]:
    return {
        "project": memory.get("project") or deepcopy(DEFAULT_PROJECT_CONTEXT),
        "last_work_request": memory.get("last_work_request"),
        "open_expectations": list(memory.get("open_expectations", []))[-MAX_EXPECTATIONS:],
        "known_results": list(memory.get("known_results", []))[-MAX_KNOWN_RESULTS:],
        "recent_messages": list(memory.get("recent_messages", []))[-MAX_RECENT_MESSAGES:],
    }
