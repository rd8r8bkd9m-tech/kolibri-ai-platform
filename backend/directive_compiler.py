from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def detect_language(text: str) -> str:
    cyrillic = sum(1 for char in text if "а" <= char.lower() <= "я")
    latin = sum(1 for char in text if "a" <= char.lower() <= "z")
    if cyrillic > latin:
        return "ru"
    return "en"


def header_value(text: str, name: str, default: str = "") -> str:
    match = re.search(rf"^{re.escape(name)}:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else default


def extract_acceptance_criteria(text: str) -> list[str]:
    items: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if "ACCEPTANCE CRITERIA" in stripped:
            in_section = True
            continue
        if in_section and re.match(r"^\d+\.\s+[A-Z ]+$", stripped):
            break
        if in_section and stripped.startswith("- "):
            items.append(stripped[2:])
    return items


def extract_constraints(text: str) -> list[str]:
    prefixes = ("Do not", "Never", "After bootstrap", "All implementation", "Default policy")
    return [line.strip() for line in text.splitlines() if line.strip().startswith(prefixes)]


def validate_against_schema(document: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in schema.get("required", []):
        if field not in document:
            errors.append(f"missing required field: {field}")
    for field, spec in schema.get("properties", {}).items():
        if field not in document:
            continue
        expected = spec.get("type")
        value = document[field]
        if expected == "string" and not isinstance(value, str):
            errors.append(f"{field} must be string")
        if expected == "array" and not isinstance(value, list):
            errors.append(f"{field} must be array")
        if expected == "object" and not isinstance(value, dict):
            errors.append(f"{field} must be object")
    return errors


@dataclass
class DirectiveStore:
    root: Path = DEFAULT_ROOT

    @property
    def factory(self) -> Path:
        return self.root / ".factory"

    def ensure(self) -> None:
        for rel in [
            "directives/raw",
            "directives/compiled",
            "directives/active",
            "directives/superseded",
            "directives/failed",
            "contracts",
            "memory",
        ]:
            (self.factory / rel).mkdir(parents=True, exist_ok=True)
        for name in ["directive-ledger.jsonl", "decision-ledger.jsonl", "conflict-ledger.jsonl", "lesson-ledger.jsonl"]:
            path = self.factory / "memory" / name
            if not path.exists():
                path.write_text("", encoding="utf-8")

    def schema(self, name: str) -> dict[str, Any]:
        path = self.factory / "contracts" / f"{name}.schema.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def append_ledger(self, name: str, payload: dict[str, Any]) -> None:
        path = self.factory / "memory" / name
        payload = {"timestamp": utc_now(), **payload}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def submit_directive(self, raw_text: str, source: str = "api", owner_id: str = "project-owner", directive_id: str | None = None) -> dict[str, Any]:
        self.ensure()
        directive_id = directive_id or header_value(raw_text, "DIRECTIVE_ID", f"KOL-DIRECTIVE-{sha256_text(raw_text)[:12]}")
        raw_path = self.factory / "directives" / "raw" / f"{directive_id}.txt"
        meta_path = self.factory / "directives" / "raw" / f"{directive_id}.json"
        if raw_path.exists():
            existing_sha = sha256_text(raw_path.read_text(encoding="utf-8"))
            new_sha = sha256_text(raw_text)
            if existing_sha != new_sha:
                raise ValueError("raw directive is immutable; create a superseding directive instead")
        raw_path.write_text(raw_text, encoding="utf-8")
        meta = {
            "directive_id": directive_id,
            "source": source,
            "owner_id": owner_id,
            "received_at": utc_now(),
            "sha256": sha256_text(raw_text),
            "current_status": "RAW",
        }
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        self.append_ledger("directive-ledger.jsonl", {"event": "directive_received", **meta})
        return meta

    def compile_directive(self, directive_id: str) -> dict[str, Any]:
        self.ensure()
        raw_path = self.factory / "directives" / "raw" / f"{directive_id}.txt"
        if not raw_path.exists():
            raise FileNotFoundError(directive_id)
        raw_text = raw_path.read_text(encoding="utf-8")
        priority = header_value(raw_text, "PRIORITY", "P2")
        mode = header_value(raw_text, "MODE", "MEDIUM")
        title = header_value(raw_text, "TITLE", directive_id)
        root_goal_id = f"{directive_id}-ROOT"
        compiled = {
            "directive_id": directive_id,
            "source": "directive-compiler",
            "owner_id": "project-owner",
            "raw_text": raw_text,
            "language": detect_language(raw_text),
            "received_at": utc_now(),
            "sha256": sha256_text(raw_text),
            "priority": priority,
            "mode": mode,
            "dependencies": [],
            "supersedes": [],
            "conflicts": [],
            "objectives": [title],
            "constraints": extract_constraints(raw_text),
            "acceptance_criteria": extract_acceptance_criteria(raw_text),
            "budgets": {"max_depth": 5, "max_children_per_task": 20, "max_active_children": 10, "max_retries": 3},
            "risk_level": "medium" if priority not in {"P0", "P1"} else "high",
            "execution_policy": {"requires_remote_agents": True, "validated_output_only": True},
            "created_root_goals": [root_goal_id],
            "current_status": "COMPILED",
            "evidence_refs": [],
            "artifact_refs": [],
        }
        errors = validate_against_schema(compiled, self.schema("directive"))
        if errors:
            failed = {"directive_id": directive_id, "current_status": "INVALID", "errors": errors}
            (self.factory / "directives" / "failed" / f"{directive_id}.json").write_text(
                json.dumps(failed, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.append_ledger("directive-ledger.jsonl", {"event": "directive_invalid", "directive_id": directive_id, "errors": errors})
            return failed
        path = self.factory / "directives" / "compiled" / f"{directive_id}.json"
        path.write_text(json.dumps(compiled, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        self.append_ledger("directive-ledger.jsonl", {"event": "directive_compiled", "directive_id": directive_id, "sha256": compiled["sha256"]})
        return compiled

    def activate_directive(self, directive_id: str) -> dict[str, Any]:
        compiled_path = self.factory / "directives" / "compiled" / f"{directive_id}.json"
        if not compiled_path.exists():
            self.compile_directive(directive_id)
        compiled = json.loads(compiled_path.read_text(encoding="utf-8"))
        compiled["current_status"] = "ACTIVE"
        active_path = self.factory / "directives" / "active" / f"{directive_id}.json"
        active_path.write_text(json.dumps(compiled, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        self.append_ledger("directive-ledger.jsonl", {"event": "directive_activated", "directive_id": directive_id})
        return compiled

    def pause_directive(self, directive_id: str) -> dict[str, Any]:
        active_path = self.factory / "directives" / "active" / f"{directive_id}.json"
        if not active_path.exists():
            raise FileNotFoundError(directive_id)
        data = json.loads(active_path.read_text(encoding="utf-8"))
        data["current_status"] = "PAUSED"
        active_path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        self.append_ledger("directive-ledger.jsonl", {"event": "directive_paused", "directive_id": directive_id})
        return data

    def supersede_directive(self, directive_id: str, replacement_id: str) -> dict[str, Any]:
        active_path = self.factory / "directives" / "active" / f"{directive_id}.json"
        if not active_path.exists():
            raise FileNotFoundError(directive_id)
        data = json.loads(active_path.read_text(encoding="utf-8"))
        data["current_status"] = "SUPERSEDED"
        data["superseded_by"] = replacement_id
        target = self.factory / "directives" / "superseded" / f"{directive_id}.json"
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        active_path.unlink()
        self.append_ledger("directive-ledger.jsonl", {"event": "directive_superseded", "directive_id": directive_id, "replacement_id": replacement_id})
        return data

    def list_directives(self) -> list[dict[str, Any]]:
        self.ensure()
        out: list[dict[str, Any]] = []
        for folder in ["active", "compiled", "failed", "superseded"]:
            for path in sorted((self.factory / "directives" / folder).glob("*.json")):
                data = json.loads(path.read_text(encoding="utf-8"))
                out.append({"storage": folder, "directive_id": data.get("directive_id"), "current_status": data.get("current_status")})
        return out

    def get_directive(self, directive_id: str) -> dict[str, Any]:
        for folder in ["active", "compiled", "failed", "superseded", "raw"]:
            path = self.factory / "directives" / folder / f"{directive_id}.json"
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        raise FileNotFoundError(directive_id)

    def evidence(self, directive_id: str) -> dict[str, Any]:
        data = self.get_directive(directive_id)
        return {
            "directive_id": directive_id,
            "sha256": data.get("sha256"),
            "evidence_refs": data.get("evidence_refs", []),
            "artifact_refs": data.get("artifact_refs", []),
        }
