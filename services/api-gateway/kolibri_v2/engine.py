from __future__ import annotations

import asyncio
import re
from typing import Any

from .estimates import calculate
from .store import Store, json_loads


def input_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                content = item.get("content")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") in {"input_text", "text"}:
                            parts.append(str(block.get("text", "")))
        return "\n".join(part for part in parts if part).strip()
    return str(value or "").strip()


class DeterministicEngine:
    def __init__(self, store: Store):
        self.store = store
        self._running: set[str] = set()

    async def reconcile(self) -> None:
        for response in self.store.incomplete_responses():
            if response["status"] in {"planning", "running", "verifying"}:
                self.store.update_response(response["id"], status="queued")
                self.store.append_response_event(response["id"], "response.status.updated", {"status": "queued", "recovered": True})
            self.schedule(response["id"])

    def schedule(self, response_id: str) -> None:
        if response_id in self._running:
            return
        self._running.add(response_id)
        asyncio.create_task(self._run_guarded(response_id))

    async def _run_guarded(self, response_id: str) -> None:
        try:
            await self.run(response_id)
        finally:
            self._running.discard(response_id)

    async def run(self, response_id: str) -> None:
        response = self.store.get_response(response_id)
        if not response or response["status"] in {"completed", "cancelled", "failed"}:
            return
        project_id = response["project_id"]
        session_id = response["session_id"]
        text = input_text(json_loads(response["input_json"], ""))
        self.store.update_response(response_id, status="planning")
        self.store.append_response_event(response_id, "response.status.updated", {"status": "planning"})
        self.store.append_response_event(response_id, "response.work_summary.updated", {"summary": "Понимаю задачу и проверяю доступные инструменты."})
        await asyncio.sleep(0.02)
        if self.store.get_response(response_id)["status"] == "cancelled":
            return
        self.store.update_response(response_id, status="running")
        self.store.append_response_event(response_id, "response.status.updated", {"status": "running"})

        lower = text.lower()
        estimate = None
        if any(word in lower for word in ["смет", "ремонт", "строительств", "дом"]):
            title = self._estimate_title(text)
            existing = self.store.list_estimates(session_id, project_id)
            estimate = existing[0] if existing else self.store.create_estimate(session_id, project_id, title)
            estimate = calculate(estimate)
            self.store.set_estimate_totals(estimate["id"], estimate["status"], estimate["subtotal"], estimate["total"])
            output = (
                "Создала структуру сметы в текущем проекте. "
                "Она пока предварительная: добавьте объёмы, цены и источники — после этого я пересчитаю итог и сформирую проверенные PDF/XLSX."
            )
            self.store.append_response_event(response_id, "response.artifact.ready", {"kind": "estimate", "estimate_id": estimate["id"], "status": estimate["status"]})
        elif any(word in lower for word in ["привет", "здравств"]):
            output = "Привет. Я Kolibri — продолжаю работу внутри текущего проекта. Что нужно сделать?"
        elif "документ" in lower or "кп" in lower:
            existing = self.store.list_estimates(session_id, project_id)
            if existing:
                estimate = calculate(existing[0])
                output = "Открываю документы текущей сметы. Экспорт доступен только из сохранённой серверной версии."
                self.store.append_response_event(response_id, "response.artifact.ready", {"kind": "estimate_documents", "estimate_id": estimate["id"]})
            else:
                output = "В этом проекте ещё нет сметы. Сначала опишите объект и объёмы работ."
        else:
            output = "Приняла задачу. В этой V2.1-сборке доказаны чат, история, сметы, документы и файлы; неподключённые инструменты не показываются."

        for chunk in self._chunks(output):
            current = self.store.get_response(response_id)
            if not current or current["status"] == "cancelled":
                return
            self.store.append_response_event(response_id, "response.output_text.delta", {"delta": chunk})
            await asyncio.sleep(0.006)
        self.store.update_response(response_id, status="verifying", output_text=output)
        self.store.update_message_for_response(response_id, output)
        self.store.append_response_event(response_id, "response.verification.updated", {"verdict": "accepted", "checks": ["non_empty_output", "single_assistant_message"]})
        self.store.update_response(response_id, status="completed", output_text=output)
        self.store.append_response_event(response_id, "response.completed", {"status": "completed", "output_text": output})

    @staticmethod
    def _chunks(text: str) -> list[str]:
        words = text.split(" ")
        chunks: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) >= 24:
                chunks.append(candidate + " ")
                current = ""
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _estimate_title(text: str) -> str:
        area = re.search(r"(\d{2,4})\s*(?:м2|м²|кв\.?\s*м)", text.lower())
        suffix = f" {area.group(1)} м²" if area else ""
        region = ""
        for candidate in ["Лениногорск", "Москва", "Казань", "Татарстан"]:
            if candidate.lower() in text.lower():
                region = f" — {candidate}"
                break
        return f"Смета: объект{suffix}{region}"
