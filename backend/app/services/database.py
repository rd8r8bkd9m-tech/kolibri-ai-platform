from __future__ import annotations

import hashlib
import json
import os
import platform
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .documents import generate_document_pack

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = ROOT / "configs" / "fone-os" / "manifest.json"
DEFAULT_DB_PATH = ROOT / "var" / "vista.db"
ARTIFACT_ROOT = Path(os.environ.get("VISTA_ARTIFACT_ROOT", str(ROOT / "var" / "artifacts")))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: str | None, fallback: Any = None) -> Any:
    if value in (None, ""):
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def money(value: float) -> int:
    return int(round(float(value)))


def item_total(item: dict[str, Any]) -> int:
    return money(float(item.get("qty", 0)) * float(item.get("price", 0)) * float(item.get("coef", 1)))


def cost_settings(project: dict[str, Any] | None = None) -> dict[str, float]:
    project = project or {}
    defaults = {
        "overhead_percent": 12.0,
        "margin_percent": 18.0,
        "discount_percent": 0.0,
        "vat_percent": 0.0,
    }
    result: dict[str, float] = {}
    for key, default in defaults.items():
        try:
            value = float(project.get(key, default))
        except (TypeError, ValueError):
            value = default
        result[key] = min(100.0, max(0.0, value))
    return result


def read_memory_percent() -> float:
    try:
        values: dict[str, int] = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                key, rest = line.split(":", 1)
                values[key] = int(rest.strip().split()[0])
        total = values.get("MemTotal", 1)
        available = values.get("MemAvailable", 0)
        return round((1 - available / total) * 100, 1)
    except Exception:
        return 0.0


def read_disk_percent(path: str = "/") -> float:
    try:
        usage = os.statvfs(path)
        total = usage.f_blocks * usage.f_frsize
        available = usage.f_bavail * usage.f_frsize
        if total <= 0:
            return 0.0
        return round((1 - available / total) * 100, 1)
    except Exception:
        return 0.0


def read_cpu_load_percent() -> float:
    try:
        load1, _, _ = os.getloadavg()
        cpus = os.cpu_count() or 1
        return round(min(100.0, (load1 / cpus) * 100), 1)
    except Exception:
        return 0.0


class NotFound(KeyError):
    pass


class PolicyViolation(RuntimeError):
    pass


class VistaStore:
    """SQLite-backed Vista OS store with real local/distributed factory contracts.

    This store intentionally avoids in-memory/demo success. All app state, node
    heartbeats, queued tasks, leases, artifacts, verifier events and audit events
    are persisted in SQLite. A future NATS/PostgreSQL backend can replace the
    queue/storage adapter without changing the external API contract.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.manifest = load_manifest()
        env_path = os.environ.get("VISTA_DB_PATH")
        self.db_path = Path(db_path or env_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._migrate_schema()
        self._ensure_initial_state()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    device TEXT NOT NULL,
                    active_estimate_id TEXT,
                    windows_json TEXT NOT NULL,
                    chat_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS estimates (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    city TEXT NOT NULL,
                    client_json TEXT NOT NULL,
                    project_json TEXT NOT NULL,
                    assumptions_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS estimate_items (
                    id TEXT PRIMARY KEY,
                    estimate_id TEXT NOT NULL REFERENCES estimates(id) ON DELETE CASCADE,
                    section TEXT NOT NULL,
                    name TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    qty REAL NOT NULL,
                    price REAL NOT NULL,
                    coef REAL NOT NULL,
                    position INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    estimate_id TEXT REFERENCES estimates(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    visibility TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    sha256 TEXT,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS leads (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    phone TEXT,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    brief_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    hostname TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    capabilities_json TEXT NOT NULL,
                    workers_total INTEGER NOT NULL,
                    workers_busy INTEGER NOT NULL,
                    cpu REAL NOT NULL DEFAULT 0,
                    ram REAL NOT NULL DEFAULT 0,
                    disk REAL NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    last_heartbeat_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS factory_tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    state TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 100,
                    required_capabilities_json TEXT NOT NULL,
                    required_artifacts_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    assigned_node_id TEXT,
                    lease_id TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    artifact_path TEXT,
                    result_json TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_leases (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES factory_tasks(id) ON DELETE CASCADE,
                    node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    granted_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_artifacts (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES factory_tasks(id) ON DELETE CASCADE,
                    node_id TEXT,
                    name TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    sha256 TEXT,
                    size_bytes INTEGER NOT NULL,
                    verifier_state TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS factory_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    ts TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    ts TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS developer_api_keys (
                    id TEXT PRIMARY KEY,
                    owner_session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    key_prefix TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    scopes_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    revoked_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_factory_tasks_state ON factory_tasks(state, priority, created_at);
                CREATE INDEX IF NOT EXISTS idx_factory_events_task ON factory_events(task_id, id);
                """
            )

    def _migrate_schema(self) -> None:
        """Apply additive SQLite migrations for product releases.

        The migration is intentionally idempotent so a user can upgrade an
        existing Vista database without deleting estimates or artifacts.
        """
        with self.connect() as conn:
            estimate_columns = {row[1] for row in conn.execute("PRAGMA table_info(estimates)").fetchall()}
            if "owner_session_id" not in estimate_columns:
                conn.execute("ALTER TABLE estimates ADD COLUMN owner_session_id TEXT")
            artifact_columns = {row[1] for row in conn.execute("PRAGMA table_info(artifacts)").fetchall()}
            if "file_path" not in artifact_columns:
                conn.execute("ALTER TABLE artifacts ADD COLUMN file_path TEXT")
            if "status" not in artifact_columns:
                conn.execute("ALTER TABLE artifacts ADD COLUMN status TEXT NOT NULL DEFAULT 'ready'")
            if "factory_task_id" not in artifact_columns:
                conn.execute("ALTER TABLE artifacts ADD COLUMN factory_task_id TEXT")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS estimate_versions (
                    id TEXT PRIMARY KEY,
                    estimate_id TEXT NOT NULL REFERENCES estimates(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS share_links (
                    token TEXT PRIMARY KEY,
                    estimate_id TEXT NOT NULL REFERENCES estimates(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS developer_api_keys (
                    id TEXT PRIMARY KEY,
                    owner_session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    key_prefix TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    scopes_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    revoked_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_estimate_versions_estimate ON estimate_versions(estimate_id, version DESC);
                CREATE INDEX IF NOT EXISTS idx_share_links_estimate ON share_links(estimate_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_developer_api_keys_owner ON developer_api_keys(owner_session_id, created_at DESC);
                """
            )

    def _ensure_initial_state(self) -> None:
        # Production starts with an empty client workspace. The first estimate is
        # created explicitly by the user; Vista never paints hidden demo data.
        self.register_node(
            {
                "node_id": os.environ.get("VISTA_NODE_ID", "local-control"),
                "hostname": platform.node() or "local-control",
                "role": "control",
                "mode": "CONTROLLED_WRITE",
                "capabilities": ["factory.local", "estimate.artifacts", "health.probe"],
                "workers_total": 1,
                "workers_busy": 0,
                "metrics": {"cpu": read_cpu_load_percent(), "ram": read_memory_percent(), "disk": read_disk_percent(str(ROOT))},
                "metadata": {"runtime": "vista-api", "version": self.manifest.get("version")},
            },
            audit=False,
        )

    # ---------- utilities ----------
    def audit(self, actor: str, action: str, target: str, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO audit_events(actor, action, target, payload_json, ts) VALUES(?,?,?,?,?)",
                (actor, action, target, json_dumps(payload or {}), now()),
            )

    def audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) | {"payload": json_loads(row["payload_json"], {})} for row in rows]

    # ---------- developer API keys / OpenAI-compatible gateway ----------
    def create_developer_api_key(
        self,
        owner_session_id: str,
        name: str,
        scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        session = self.get_session(owner_session_id)
        if session["role"] not in {"developer", "owner"}:
            raise PolicyViolation("developer or owner role required")
        raw_key = "vista_sk_live_" + secrets.token_urlsafe(32)
        key_id = f"vkey_{uuid.uuid4().hex[:12]}"
        prefix = raw_key[:20]
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        granted_scopes = sorted(set(scopes or ["openai.proxy"]))
        if "openai.proxy" not in granted_scopes:
            granted_scopes.append("openai.proxy")
        ts = now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO developer_api_keys(
                    id, owner_session_id, name, key_prefix, key_hash, scopes_json,
                    status, created_at, last_used_at, revoked_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (key_id, owner_session_id, name.strip() or "Vista API key", prefix, key_hash, json_dumps(granted_scopes), "active", ts, None, None),
            )
        self.audit(owner_session_id, "developer.key.create", key_id, {"name": name, "scopes": granted_scopes})
        return {
            "id": key_id,
            "name": name.strip() or "Vista API key",
            "key": raw_key,
            "prefix": prefix,
            "scopes": granted_scopes,
            "status": "active",
            "created_at": ts,
        }

    def list_developer_api_keys(self, owner_session_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, key_prefix, scopes_json, status, created_at, last_used_at, revoked_at
                  FROM developer_api_keys
                 WHERE owner_session_id=?
                 ORDER BY created_at DESC
                """,
                (owner_session_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "prefix": row["key_prefix"],
                "scopes": json_loads(row["scopes_json"], []),
                "status": row["status"],
                "created_at": row["created_at"],
                "last_used_at": row["last_used_at"],
                "revoked_at": row["revoked_at"],
            }
            for row in rows
        ]

    def revoke_developer_api_key(self, key_id: str, owner_session_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id FROM developer_api_keys WHERE id=? AND owner_session_id=?",
                (key_id, owner_session_id),
            ).fetchone()
            if not row:
                raise NotFound(key_id)
            revoked_at = now()
            conn.execute(
                "UPDATE developer_api_keys SET status='revoked', revoked_at=? WHERE id=?",
                (revoked_at, key_id),
            )
        self.audit(owner_session_id, "developer.key.revoke", key_id, {})
        return {"id": key_id, "status": "revoked", "revoked_at": revoked_at}

    def authenticate_developer_api_key(self, raw_key: str) -> dict[str, Any]:
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM developer_api_keys
                 WHERE key_hash=? AND status='active' AND revoked_at IS NULL
                """,
                (key_hash,),
            ).fetchone()
            if not row:
                raise NotFound("developer api key")
            conn.execute(
                "UPDATE developer_api_keys SET last_used_at=? WHERE id=?",
                (now(), row["id"]),
            )
        session = self.get_session(row["owner_session_id"])
        if session["role"] not in {"developer", "owner"}:
            raise PolicyViolation("API key owner no longer has developer access")
        scopes = json_loads(row["scopes_json"], [])
        if "openai.proxy" not in scopes:
            raise PolicyViolation("API key lacks openai.proxy scope")
        return {"key_id": row["id"], "session": session, "scopes": scopes}

    # ---------- sessions / workbench ----------
    def active_estimate_id(self, owner_session_id: str | None = None) -> str | None:
        estimates = self.list_estimates(owner_session_id=owner_session_id)
        return estimates[0]["id"] if estimates else None

    def create_session(self, role: str = "client", device: str = "auto", plan: str | None = None) -> dict[str, Any]:
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        role_cfg = self.manifest.get("roles", {}).get(role, self.manifest.get("roles", {}).get("client", {}))
        plan_id = plan or role_cfg.get("plan") or role_cfg.get("default_plan") or "basic_estimates"
        ts = now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions(id, role, plan, device, active_estimate_id, windows_json, chat_json, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (session_id, role, plan_id, device, self.active_estimate_id(session_id), "[]", "[]", ts, ts),
            )
        self.audit("system", "session.create", session_id, {"role": role, "device": device})
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            raise NotFound(session_id)
        return {
            "id": row["id"],
            "role": row["role"],
            "plan": row["plan"],
            "device": row["device"],
            "active_estimate_id": row["active_estimate_id"],
            "windows": json_loads(row["windows_json"], []),
            "chat": json_loads(row["chat_json"], []),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def update_session(self, session_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        current = self.get_session(session_id)
        allowed = {"role", "plan", "device", "active_estimate_id", "windows", "chat"}
        next_state = {**current, **{k: v for k, v in patch.items() if k in allowed}}
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE sessions SET role=?, plan=?, device=?, active_estimate_id=?, windows_json=?, chat_json=?, updated_at=? WHERE id=?
                """,
                (
                    next_state["role"],
                    next_state["plan"],
                    next_state["device"],
                    next_state.get("active_estimate_id"),
                    json_dumps(next_state.get("windows", [])),
                    json_dumps(next_state.get("chat", [])),
                    now(),
                    session_id,
                ),
            )
        self.audit("system", "session.update", session_id, {"fields": list(patch.keys())})
        return self.get_session(session_id)

    def open_window(self, session_id: str, component_id: str, label: str | None = None) -> dict[str, Any]:
        session = self.get_session(session_id)
        windows = session.get("windows", [])
        existing = next((w for w in windows if w.get("componentId") == component_id), None)
        if existing:
            existing["minimized"] = False
            existing["focused"] = True
        else:
            windows.append({"componentId": component_id, "label": label or component_id, "minimized": False, "focused": True})
        return self.update_session(session_id, {"windows": windows})

    def close_window(self, session_id: str, component_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        return self.update_session(session_id, {"windows": [w for w in session.get("windows", []) if w.get("componentId") != component_id]})

    # ---------- estimates ----------
    def list_estimates(self, owner_session_id: str | None = None, include_all: bool = False) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if owner_session_id and not include_all:
                rows = conn.execute(
                    "SELECT id FROM estimates WHERE owner_session_id=? ORDER BY updated_at DESC",
                    (owner_session_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT id FROM estimates ORDER BY updated_at DESC").fetchall()
        return [self.get_estimate(row["id"], owner_session_id=owner_session_id, include_all=include_all) for row in rows]

    def _assert_estimate_owner(self, row: sqlite3.Row, owner_session_id: str | None, include_all: bool) -> None:
        if include_all or owner_session_id is None:
            return
        if row["owner_session_id"] != owner_session_id:
            raise NotFound(row["id"])

    def get_estimate(self, estimate_id: str, owner_session_id: str | None = None, include_all: bool = False) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM estimates WHERE id=?", (estimate_id,)).fetchone()
            if not row:
                raise NotFound(estimate_id)
            self._assert_estimate_owner(row, owner_session_id, include_all)
            item_rows = conn.execute(
                "SELECT * FROM estimate_items WHERE estimate_id=? ORDER BY position ASC", (estimate_id,)
            ).fetchall()
            artifact_rows = conn.execute(
                """
                SELECT id, estimate_id, kind, name, visibility, content_type, created_at,
                       size_bytes, sha256, status, factory_task_id
                FROM artifacts WHERE estimate_id=? ORDER BY created_at DESC
                """,
                (estimate_id,),
            ).fetchall()
        return {
            "id": row["id"],
            "owner_session_id": row["owner_session_id"],
            "status": row["status"],
            "version": row["version"],
            "city": row["city"],
            "client": json_loads(row["client_json"], {}),
            "project": json_loads(row["project_json"], {}),
            "items": [dict(item) for item in item_rows],
            "assumptions": json_loads(row["assumptions_json"], []),
            "summary": json_loads(row["summary_json"], {}),
            "artifacts": [dict(artifact) for artifact in artifact_rows],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create_estimate(self, payload: dict[str, Any], owner_session_id: str | None = None) -> dict[str, Any]:
        estimate_id = payload.get("id") or f"est_{uuid.uuid4().hex[:10]}"
        ts = now()
        items = payload.get("items", [])
        project = {
            "name": "Новый объект",
            "area": 0,
            "address": "",
            "type": "renovation",
            "overhead_percent": 12.0,
            "margin_percent": 18.0,
            "discount_percent": 0.0,
            "vat_percent": 0.0,
            **payload.get("project", {}),
        }
        client = {"name": "Новый клиент", "phone": "", "email": "", **payload.get("client", {})}
        summary = self.calculate_summary(items, project)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO estimates(
                    id, status, version, city, client_json, project_json,
                    assumptions_json, summary_json, created_at, updated_at, owner_session_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    estimate_id,
                    payload.get("status", "draft"),
                    1,
                    payload.get("city", "Москва"),
                    json_dumps(client),
                    json_dumps(project),
                    json_dumps(payload.get("assumptions", [])),
                    json_dumps(summary),
                    ts,
                    ts,
                    owner_session_id,
                ),
            )
            for pos, item in enumerate(items):
                conn.execute(
                    "INSERT INTO estimate_items(id, estimate_id, section, name, unit, qty, price, coef, position) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        item.get("id") or f"item_{uuid.uuid4().hex[:10]}",
                        estimate_id,
                        item.get("section", "Работы"),
                        item.get("name", "Позиция"),
                        item.get("unit", "шт"),
                        float(item.get("qty", 1)),
                        float(item.get("price", 0)),
                        float(item.get("coef", 1)),
                        pos,
                    ),
                )
        self.save_estimate_version(estimate_id, note="Создание сметы", owner_session_id=owner_session_id)
        if owner_session_id:
            try:
                self.update_session(owner_session_id, {"active_estimate_id": estimate_id})
            except NotFound:
                pass
        self.audit(owner_session_id or "system", "estimate.create", estimate_id, {"items": len(items)})
        return self.get_estimate(estimate_id, owner_session_id=owner_session_id)

    def update_estimate(self, estimate_id: str, payload: dict[str, Any], owner_session_id: str | None = None) -> dict[str, Any]:
        current = self.get_estimate(estimate_id, owner_session_id=owner_session_id)
        city = payload.get("city", current["city"])
        status = payload.get("status", current["status"])
        allowed_statuses = {"draft", "review", "approved", "sent", "archived"}
        if status not in allowed_statuses:
            raise PolicyViolation(f"unsupported estimate status: {status}")
        client = {**current["client"], **payload.get("client", {})}
        project = {**current["project"], **payload.get("project", {})}
        project.update(cost_settings(project))
        assumptions = payload.get("assumptions", current["assumptions"])
        summary = self.calculate_summary(current["items"], project)
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE estimates
                   SET status=?, city=?, client_json=?, project_json=?, assumptions_json=?, summary_json=?,
                       version=version+1, updated_at=?
                 WHERE id=?
                """,
                (status, city, json_dumps(client), json_dumps(project), json_dumps(assumptions), json_dumps(summary), now(), estimate_id),
            )
        self.audit(owner_session_id or "system", "estimate.update", estimate_id, {"fields": sorted(payload.keys())})
        return self.get_estimate(estimate_id, owner_session_id=owner_session_id)

    def calculate_summary(self, items: Iterable[dict[str, Any]], project: dict[str, Any] | None = None) -> dict[str, int | float]:
        settings = cost_settings(project)
        subtotal = sum(item_total(dict(item)) for item in items)
        overhead = money(subtotal * settings["overhead_percent"] / 100)
        margin_base = subtotal + overhead
        margin = money(margin_base * settings["margin_percent"] / 100)
        before_discount = margin_base + margin
        discount = money(before_discount * settings["discount_percent"] / 100)
        taxable = max(0, before_discount - discount)
        tax = money(taxable * settings["vat_percent"] / 100)
        total = taxable + tax
        return {
            "subtotal": subtotal,
            "overhead": overhead,
            "margin": margin,
            "discount": discount,
            "tax": tax,
            "total": total,
            **settings,
        }

    def _reload_items(self, estimate_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM estimate_items WHERE estimate_id=? ORDER BY position ASC", (estimate_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def _save_summary(self, estimate_id: str) -> None:
        items = self._reload_items(estimate_id)
        with self.connect() as conn:
            row = conn.execute("SELECT project_json FROM estimates WHERE id=?", (estimate_id,)).fetchone()
        if not row:
            raise NotFound(estimate_id)
        project = json_loads(row["project_json"], {})
        summary = self.calculate_summary(items, project)
        with self.connect() as conn:
            conn.execute(
                "UPDATE estimates SET summary_json=?, version=version+1, updated_at=? WHERE id=?",
                (json_dumps(summary), now(), estimate_id),
            )

    def add_estimate_item(self, estimate_id: str, payload: dict[str, Any], owner_session_id: str | None = None) -> dict[str, Any]:
        self.get_estimate(estimate_id, owner_session_id=owner_session_id)
        with self.connect() as conn:
            position = conn.execute(
                "SELECT COUNT(*) FROM estimate_items WHERE estimate_id=?", (estimate_id,)
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO estimate_items(id, estimate_id, section, name, unit, qty, price, coef, position) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    payload.get("id") or f"item_{uuid.uuid4().hex[:10]}",
                    estimate_id,
                    payload.get("section", "Работы"),
                    payload.get("name", "Новая позиция"),
                    payload.get("unit", "шт"),
                    float(payload.get("qty", 1)),
                    float(payload.get("price", 0)),
                    float(payload.get("coef", 1)),
                    position,
                ),
            )
        self._save_summary(estimate_id)
        self.audit(owner_session_id or "system", "estimate.item.add", estimate_id, payload)
        return self.get_estimate(estimate_id, owner_session_id=owner_session_id)

    def update_estimate_item(self, estimate_id: str, item_id: str, payload: dict[str, Any], owner_session_id: str | None = None) -> dict[str, Any]:
        self.get_estimate(estimate_id, owner_session_id=owner_session_id)
        allowed = {"section", "name", "unit", "qty", "price", "coef"}
        fields = [key for key in payload if key in allowed]
        if not fields:
            return self.get_estimate(estimate_id, owner_session_id=owner_session_id)
        assignments = ", ".join(f"{key}=?" for key in fields)
        values = [payload[key] for key in fields]
        with self.connect() as conn:
            cursor = conn.execute(
                f"UPDATE estimate_items SET {assignments} WHERE estimate_id=? AND id=?",
                (*values, estimate_id, item_id),
            )
            if cursor.rowcount == 0:
                raise NotFound(item_id)
        self._save_summary(estimate_id)
        self.audit(owner_session_id or "system", "estimate.item.update", item_id, payload)
        return self.get_estimate(estimate_id, owner_session_id=owner_session_id)

    def delete_estimate_item(self, estimate_id: str, item_id: str, owner_session_id: str | None = None) -> dict[str, Any]:
        self.get_estimate(estimate_id, owner_session_id=owner_session_id)
        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM estimate_items WHERE estimate_id=? AND id=?", (estimate_id, item_id)
            )
            if cursor.rowcount == 0:
                raise NotFound(item_id)
        self._save_summary(estimate_id)
        self.audit(owner_session_id or "system", "estimate.item.delete", item_id, {})
        return self.get_estimate(estimate_id, owner_session_id=owner_session_id)

    def save_estimate_version(self, estimate_id: str, note: str = "", owner_session_id: str | None = None) -> dict[str, Any]:
        estimate = self.get_estimate(estimate_id, owner_session_id=owner_session_id)
        version_id = f"ver_{uuid.uuid4().hex[:12]}"
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO estimate_versions(id, estimate_id, version, snapshot_json, note, created_at) VALUES(?,?,?,?,?,?)",
                (version_id, estimate_id, estimate["version"], json_dumps(estimate), note, now()),
            )
        self.audit(owner_session_id or "system", "estimate.version.save", estimate_id, {"version_id": version_id})
        return {"id": version_id, "estimate_id": estimate_id, "version": estimate["version"], "note": note}

    def list_estimate_versions(self, estimate_id: str, owner_session_id: str | None = None) -> list[dict[str, Any]]:
        self.get_estimate(estimate_id, owner_session_id=owner_session_id)
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, estimate_id, version, note, created_at FROM estimate_versions WHERE estimate_id=? ORDER BY created_at DESC",
                (estimate_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def proposal(self, estimate_id: str, owner_session_id: str | None = None) -> dict[str, Any]:
        estimate = self.get_estimate(estimate_id, owner_session_id=owner_session_id)
        return {
            "id": f"proposal_{estimate_id}",
            "estimate_id": estimate_id,
            "title": f"Коммерческое предложение — {estimate['project'].get('name', 'объект')}",
            "client": estimate["client"].get("name", "Клиент"),
            "total": estimate["summary"].get("total", 0),
            "valid_days": 14,
            "payment": ["40% аванс", "40% после черновых работ", "20% после сдачи"],
            "timeline": ["замер", "согласование", "работы", "приёмка"],
            "status": "ready" if estimate["items"] else "draft",
        }

    def generate_estimate_documents(self, estimate_id: str, owner_session_id: str | None = None) -> dict[str, Any]:
        estimate = self.get_estimate(estimate_id, owner_session_id=owner_session_id)
        if not estimate["items"]:
            raise PolicyViolation("Добавьте хотя бы одну позицию перед формированием документов")
        task = self.create_factory_task(
            {
                "title": f"Документы по смете {estimate_id}",
                "kind": "estimate_document_pack",
                "required_capabilities": ["estimate.artifacts"],
                "required_artifacts": ["DOCUMENT_PACK.json"],
                "payload": {"estimate_id": estimate_id, "owner_session_id": owner_session_id},
            }
        )
        local_node = os.environ.get("VISTA_NODE_ID", "local-control")
        lease = self.lease_task({"node_id": local_node, "task_id": task["id"], "lease_seconds": 300})
        if not lease.get("task") or lease["task"]["id"] != task["id"]:
            raise PolicyViolation("local document worker could not lease the task")
        output_dir = ARTIFACT_ROOT / estimate_id / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        generated = generate_document_pack(estimate, output_dir)
        with self.connect() as conn:
            conn.execute("DELETE FROM artifacts WHERE estimate_id=?", (estimate_id,))
            product_artifacts: list[dict[str, Any]] = []
            for generated_file in generated:
                artifact_id = f"art_{uuid.uuid4().hex[:14]}"
                record = {
                    "id": artifact_id,
                    "name": generated_file.name,
                    "kind": generated_file.kind,
                    "content_type": generated_file.content_type,
                    "sha256": generated_file.checksum,
                    "size_bytes": generated_file.size_bytes,
                }
                product_artifacts.append(record)
                conn.execute(
                    """
                    INSERT INTO artifacts(
                        id, estimate_id, kind, name, visibility, content_type, payload,
                        sha256, size_bytes, created_at, file_path, status, factory_task_id
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        artifact_id,
                        estimate_id,
                        generated_file.kind,
                        generated_file.name,
                        "client",
                        generated_file.content_type,
                        "",
                        generated_file.checksum,
                        generated_file.size_bytes,
                        now(),
                        str(generated_file.path),
                        "ready",
                        task["id"],
                    ),
                )
        manifest_payload = json_dumps({"estimate_id": estimate_id, "files": product_artifacts})
        completed = self.complete_task(
            task["id"],
            {
                "lease_id": lease["lease"]["id"],
                "node_id": local_node,
                "artifacts": [
                    {
                        "name": "DOCUMENT_PACK.json",
                        "content_type": "application/json",
                        "payload": manifest_payload,
                    }
                ],
            },
        )
        with self.connect() as conn:
            conn.execute(
                "UPDATE factory_tasks SET artifact_path=?, result_json=?, updated_at=? WHERE id=?",
                (str(output_dir), json_dumps({"estimate_id": estimate_id, "artifacts": product_artifacts}), now(), task["id"]),
            )
        self.save_estimate_version(estimate_id, note="Сформирован пакет документов", owner_session_id=owner_session_id)
        self.audit(owner_session_id or "system", "estimate.documents.generate", estimate_id, {"task_id": task["id"]})
        return {
            "task": self.get_factory_task(completed["id"]),
            "artifacts": self.get_artifacts(estimate_id, owner_session_id=owner_session_id),
        }

    def get_artifacts(self, estimate_id: str, owner_session_id: str | None = None) -> list[dict[str, Any]]:
        return self.get_estimate(estimate_id, owner_session_id=owner_session_id)["artifacts"]

    def get_artifact_payload(self, artifact_id: str, owner_session_id: str | None = None, include_all: bool = False) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
            if row:
                if row["estimate_id"]:
                    self.get_estimate(row["estimate_id"], owner_session_id=owner_session_id, include_all=include_all)
                return {
                    "id": row["id"],
                    "estimate_id": row["estimate_id"],
                    "kind": row["kind"],
                    "name": row["name"],
                    "visibility": row["visibility"],
                    "content_type": row["content_type"],
                    "payload": row["payload"],
                    "file_path": row["file_path"],
                    "sha256": row["sha256"],
                    "size_bytes": row["size_bytes"],
                    "status": row["status"],
                    "factory_task_id": row["factory_task_id"],
                    "created_at": row["created_at"],
                }
            task_row = conn.execute("SELECT * FROM task_artifacts WHERE id=?", (artifact_id,)).fetchone()
        if not task_row:
            raise NotFound(artifact_id)
        return {
            "id": task_row["id"],
            "task_id": task_row["task_id"],
            "kind": "task_artifact",
            "name": task_row["name"],
            "visibility": "factory",
            "content_type": task_row["content_type"],
            "payload": task_row["payload"],
            "file_path": None,
            "sha256": task_row["sha256"],
            "size_bytes": task_row["size_bytes"],
            "status": "ready",
            "created_at": task_row["created_at"],
        }

    def create_share_link(self, estimate_id: str, owner_session_id: str | None = None, ttl_hours: int = 168) -> dict[str, Any]:
        self.get_estimate(estimate_id, owner_session_id=owner_session_id)
        token = secrets.token_urlsafe(24)
        expires = datetime.now(timezone.utc) + timedelta(hours=max(1, ttl_hours))
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO share_links(token, estimate_id, expires_at, revoked_at, created_at) VALUES(?,?,?,?,?)",
                (token, estimate_id, expires.isoformat(), None, now()),
            )
        self.audit(owner_session_id or "system", "estimate.share.create", estimate_id, {"token_prefix": token[:6]})
        return {"token": token, "estimate_id": estimate_id, "expires_at": expires.isoformat()}

    def _active_share_row(self, token: str):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM share_links WHERE token=?", (token,)).fetchone()
        if not row or row["revoked_at"] or parse_ts(row["expires_at"]) <= datetime.now(timezone.utc):
            raise NotFound(token)
        return row

    def public_share(self, token: str) -> dict[str, Any]:
        row = self._active_share_row(token)
        estimate = self.get_estimate(row["estimate_id"], include_all=True)
        artifacts = [
            {
                **artifact,
                "public_download_path": f"/api/public/share/{token}/artifacts/{artifact['id']}/download",
            }
            for artifact in estimate["artifacts"]
            if artifact.get("visibility") == "client" and artifact.get("status") == "ready"
        ]
        return {
            "estimate": {
                "id": estimate["id"],
                "project": estimate["project"],
                "client": estimate["client"],
                "city": estimate["city"],
                "summary": estimate["summary"],
                "items": estimate["items"],
                "status": estimate["status"],
                "version": estimate["version"],
            },
            "artifacts": artifacts,
            "expires_at": row["expires_at"],
        }

    def public_artifact(self, token: str, artifact_id: str) -> dict[str, Any]:
        row = self._active_share_row(token)
        artifact = self.get_artifact_payload(artifact_id, include_all=True)
        if artifact.get("estimate_id") != row["estimate_id"]:
            raise NotFound(artifact_id)
        if artifact.get("visibility") != "client" or artifact.get("status") != "ready":
            raise NotFound(artifact_id)
        return artifact

    def list_share_links(self, estimate_id: str, owner_session_id: str | None = None) -> list[dict[str, Any]]:
        self.get_estimate(estimate_id, owner_session_id=owner_session_id)
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT token, estimate_id, expires_at, revoked_at, created_at FROM share_links WHERE estimate_id=? ORDER BY created_at DESC",
                (estimate_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def revoke_share_link(self, estimate_id: str, token: str, owner_session_id: str | None = None) -> dict[str, Any]:
        self.get_estimate(estimate_id, owner_session_id=owner_session_id)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT token FROM share_links WHERE token=? AND estimate_id=?",
                (token, estimate_id),
            ).fetchone()
            if not row:
                raise NotFound(token)
            revoked_at = now()
            conn.execute("UPDATE share_links SET revoked_at=? WHERE token=?", (revoked_at, token))
        self.audit(owner_session_id or "system", "estimate.share.revoke", estimate_id, {"token_prefix": token[:6]})
        return {"token": token, "estimate_id": estimate_id, "status": "revoked", "revoked_at": revoked_at}

    # ---------- leads ----------
    def create_lead(self, payload: dict[str, Any]) -> dict[str, Any]:
        lead_id = payload.get("id") or f"lead_{uuid.uuid4().hex[:8]}"
        ts = now()
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO leads(id, name, phone, source, status, brief_json, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (lead_id, payload.get("name", "Новый лид"), payload.get("phone"), payload.get("source", "app"), payload.get("status", "new"), json_dumps(payload.get("brief", {})), ts, ts),
            )
        self.audit("system", "lead.create", lead_id, payload)
        return self.get_lead(lead_id)

    def get_lead(self, lead_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        if not row:
            raise NotFound(lead_id)
        return dict(row) | {"brief": json_loads(row["brief_json"], {})}

    def list_leads(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT id FROM leads ORDER BY updated_at DESC").fetchall()
        return [self.get_lead(row["id"]) for row in rows]

    # ---------- nodes ----------
    def register_node(self, payload: dict[str, Any], audit: bool = True) -> dict[str, Any]:
        node_id = payload.get("node_id") or payload.get("id") or f"node_{uuid.uuid4().hex[:8]}"
        metrics = payload.get("metrics", {})
        ts = now()
        with self.connect() as conn:
            existing = conn.execute("SELECT registered_at FROM nodes WHERE id=?", (node_id,)).fetchone()
            registered_at = existing["registered_at"] if existing else ts
            conn.execute(
                """
                INSERT OR REPLACE INTO nodes(id, hostname, role, status, mode, capabilities_json, workers_total, workers_busy, cpu, ram, disk, metadata_json, registered_at, last_heartbeat_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    node_id,
                    payload.get("hostname") or node_id,
                    payload.get("role", "worker"),
                    payload.get("status", "online"),
                    payload.get("mode", "READ_ONLY"),
                    json_dumps(payload.get("capabilities", [])),
                    int(payload.get("workers_total", 1)),
                    int(payload.get("workers_busy", 0)),
                    float(metrics.get("cpu", payload.get("cpu", 0))),
                    float(metrics.get("ram", payload.get("ram", 0))),
                    float(metrics.get("disk", payload.get("disk", 0))),
                    json_dumps(payload.get("metadata", {})),
                    registered_at,
                    ts,
                ),
            )
        if audit:
            self.audit("node", "node.register", node_id, payload)
        return self.get_node(node_id)

    def heartbeat_node(self, node_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        node = self.get_node(node_id)
        metrics = payload.get("metrics", {})
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE nodes SET status=?, mode=?, capabilities_json=?, workers_total=?, workers_busy=?, cpu=?, ram=?, disk=?, metadata_json=?, last_heartbeat_at=? WHERE id=?
                """,
                (
                    payload.get("status", "online"),
                    payload.get("mode", node.get("mode", "READ_ONLY")),
                    json_dumps(payload.get("capabilities", node.get("capabilities", []))),
                    int(payload.get("workers_total", node.get("workers_total", 1))),
                    int(payload.get("workers_busy", node.get("workers_busy", 0))),
                    float(metrics.get("cpu", payload.get("cpu", node.get("cpu", 0)))),
                    float(metrics.get("ram", payload.get("ram", node.get("ram", 0)))),
                    float(metrics.get("disk", payload.get("disk", node.get("disk", 0)))),
                    json_dumps(payload.get("metadata", node.get("metadata", {}))),
                    now(),
                    node_id,
                ),
            )
        return self.get_node(node_id)

    def get_node(self, node_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
        if not row:
            raise NotFound(node_id)
        data = dict(row)
        data["capabilities"] = json_loads(data.pop("capabilities_json"), [])
        data["metadata"] = json_loads(data.pop("metadata_json"), {})
        return data

    def list_nodes(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT id FROM nodes ORDER BY last_heartbeat_at DESC").fetchall()
        return [self.get_node(row["id"]) for row in rows]

    def set_node_mode(self, node_id: str, mode: str) -> dict[str, Any]:
        self.get_node(node_id)
        with self.connect() as conn:
            conn.execute("UPDATE nodes SET mode=?, last_heartbeat_at=? WHERE id=?", (mode, now(), node_id))
        self.audit("operator", "node.mode", node_id, {"mode": mode})
        return self.get_node(node_id)

    def fleet_health(self, stale_seconds: int | None = None) -> dict[str, Any]:
        ttl = int(stale_seconds or os.environ.get("VISTA_NODE_STALE_SECONDS", "60"))
        now_dt = datetime.now(timezone.utc)
        nodes = []
        for node in self.list_nodes():
            try:
                age = (now_dt - parse_ts(node["last_heartbeat_at"])).total_seconds()
            except Exception:
                age = 999999
            health = "stale" if age > ttl else node.get("status", "unknown")
            nodes.append(node | {"heartbeat_age_seconds": int(age), "health": health})
        summary = {
            "registered": len(nodes),
            "online": sum(1 for n in nodes if n["health"] == "online"),
            "stale": sum(1 for n in nodes if n["health"] == "stale"),
            "draining": sum(1 for n in nodes if n.get("mode") == "DRAINING"),
            "workers_free": sum(max(0, int(n.get("workers_total", 0)) - int(n.get("workers_busy", 0))) for n in nodes if n["health"] == "online"),
        }
        return {"summary": summary, "nodes": nodes, "ttl_seconds": ttl, "updated_at": now()}

    # ---------- server metrics/logs ----------
    def server_metrics(self) -> dict[str, Any]:
        # Update local-control heartbeat on every metrics read.
        self.heartbeat_node(
            os.environ.get("VISTA_NODE_ID", "local-control"),
            {
                "status": "online",
                "mode": "CONTROLLED_WRITE",
                "capabilities": ["factory.local", "estimate.artifacts", "health.probe"],
                "workers_total": 1,
                "workers_busy": 0,
                "metrics": {"cpu": read_cpu_load_percent(), "ram": read_memory_percent(), "disk": read_disk_percent(str(ROOT))},
                "metadata": {"runtime": "vista-api"},
            },
        )
        nodes = self.list_nodes()
        online = [n for n in nodes if n["status"] == "online"]
        return {
            "summary": {
                "online_nodes": len(online),
                "registered_nodes": len(nodes),
                "workers_free": sum(max(0, int(n["workers_total"]) - int(n["workers_busy"])) for n in online),
                "cpu_avg": round(sum(float(n["cpu"]) for n in online) / max(1, len(online)), 1),
                "ram_avg": round(sum(float(n["ram"]) for n in online) / max(1, len(online)), 1),
                "disk_max": round(max([float(n["disk"]) for n in online] or [0]), 1),
            },
            "nodes": [
                {
                    "id": n["id"],
                    "role": n["role"],
                    "status": n["status"],
                    "mode": n["mode"],
                    "cpu": n["cpu"],
                    "ram": n["ram"],
                    "disk": n["disk"],
                    "workers": f"{n['workers_busy']}/{n['workers_total']}",
                    "last_heartbeat_at": n["last_heartbeat_at"],
                }
                for n in nodes
            ],
            "source": "vista_node_registry",
            "collected_at": now(),
        }

    def server_logs(self) -> list[dict[str, Any]]:
        events = self.audit_events(limit=40)
        if not events:
            return [{"ts": now(), "level": "info", "service": "vista-api", "text": "no audit events yet"}]
        return [{"ts": event["ts"], "level": "info", "service": "audit", "text": f"{event['action']} → {event['target']}"} for event in events[:40]]

    # ---------- factory queue/runtime ----------
    def record_factory_event(self, task_id: str, event: str, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO factory_events(task_id, event, payload_json, ts) VALUES(?,?,?,?)",
                (task_id, event, json_dumps(payload or {}), now()),
            )

    def create_factory_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = payload.get("task_id") or f"vistatask_{uuid.uuid4().hex[:8]}"
        required_artifacts = payload.get("required_artifacts") or ["RESULT.md"]
        required_capabilities = payload.get("required_capabilities") or []
        ts = now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO factory_tasks(id, title, kind, state, priority, required_capabilities_json, required_artifacts_json, payload_json, result_json, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    task_id,
                    payload.get("title", "Vista factory task"),
                    payload.get("kind", "health_probe"),
                    "queued",
                    int(payload.get("priority", 100)),
                    json_dumps(required_capabilities),
                    json_dumps(required_artifacts),
                    json_dumps(payload.get("payload", {})),
                    json_dumps({}),
                    ts,
                    ts,
                ),
            )
        self.record_factory_event(task_id, "task.created", {"title": payload.get("title")})
        self.audit("factory", "task.create", task_id, payload)
        return self.get_factory_task(task_id)

    def get_factory_task(self, task_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM factory_tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise NotFound(task_id)
        data = dict(row)
        data["required_capabilities"] = json_loads(data.pop("required_capabilities_json"), [])
        data["required_artifacts"] = json_loads(data.pop("required_artifacts_json"), [])
        data["payload"] = json_loads(data.pop("payload_json"), {})
        data["result"] = json_loads(data.pop("result_json"), {})
        data["events"] = self.factory_events(task_id)
        data["artifacts"] = self.task_artifacts(task_id)
        return data

    def list_factory_tasks(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT id FROM factory_tasks ORDER BY created_at DESC LIMIT 200").fetchall()
        return [self.get_factory_task(row["id"]) for row in rows]

    def _node_matches_task(self, node: dict[str, Any], task: dict[str, Any]) -> bool:
        if node.get("status") != "online":
            return False
        if node.get("mode") not in {"CONTROLLED_WRITE", "PRODUCTION"}:
            return False
        if int(node.get("workers_busy", 0)) >= int(node.get("workers_total", 1)):
            return False
        node_caps = set(node.get("capabilities", []))
        required = set(task.get("required_capabilities", []))
        return required.issubset(node_caps)

    def lease_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Atomically lease one compatible queued task to a node.

        ``task_id`` is optional and is used by bounded in-process workers such as
        the document generator. Remote node-agents normally omit it and receive
        the oldest compatible task. The conditional state update prevents two
        workers from leasing the same task under concurrent polling.
        """
        self.reap_expired_leases()
        node_id = payload.get("node_id")
        if not node_id:
            raise PolicyViolation("node_id is required")
        node = self.get_node(node_id)
        requested_task_id = payload.get("task_id")
        now_dt = datetime.now(timezone.utc)
        requested_lease_seconds = int(payload.get("lease_seconds", 120))
        if os.environ.get("VISTA_ENV", "local").lower() in {"prod", "production"}:
            lease_seconds = max(15, min(requested_lease_seconds, 3600))
        else:
            lease_seconds = min(requested_lease_seconds, 3600)
        leased_task_id: str | None = None
        leased_payload: dict[str, Any] | None = None

        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if requested_task_id:
                rows = conn.execute(
                    "SELECT id FROM factory_tasks WHERE state='queued' AND id=? LIMIT 1",
                    (requested_task_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id FROM factory_tasks WHERE state='queued' ORDER BY priority ASC, created_at ASC LIMIT 50"
                ).fetchall()
            for row in rows:
                task = self.get_factory_task(row["id"])
                if not self._node_matches_task(node, task):
                    if requested_task_id:
                        raise PolicyViolation("requested task is not compatible with node")
                    continue
                lease_id = f"lease_{uuid.uuid4().hex[:10]}"
                expires_at = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
                update = conn.execute(
                    """
                    UPDATE factory_tasks
                       SET state='leased', assigned_node_id=?, lease_id=?, attempts=attempts+1, updated_at=?
                     WHERE id=? AND state='queued'
                    """,
                    (node_id, lease_id, now(), task["id"]),
                )
                if update.rowcount != 1:
                    continue
                conn.execute(
                    "INSERT INTO task_leases(id, task_id, node_id, status, granted_at, expires_at, heartbeat_at) VALUES(?,?,?,?,?,?,?)",
                    (lease_id, task["id"], node_id, "active", now(), expires_at, now()),
                )
                conn.execute("UPDATE nodes SET workers_busy=workers_busy+1 WHERE id=?", (node_id,))
                conn.execute(
                    "INSERT INTO factory_events(task_id, event, payload_json, ts) VALUES(?,?,?,?)",
                    (task["id"], "lease.granted", json_dumps({"node_id": node_id, "lease_id": lease_id, "expires_at": expires_at}), now()),
                )
                leased_task_id = task["id"]
                leased_payload = {"id": lease_id, "node_id": node_id, "expires_at": expires_at}
                break

        if leased_task_id and leased_payload:
            self.audit("factory", "task.lease", leased_task_id, {"node_id": node_id, "lease_id": leased_payload["id"]})
            return {"task": self.get_factory_task(leased_task_id), "lease": leased_payload}
        return {"task": None, "lease": None}

    def reap_expired_leases(self, max_attempts: int | None = None) -> dict[str, Any]:
        max_attempts = int(max_attempts or os.environ.get("VISTA_TASK_MAX_ATTEMPTS", "3"))
        ts = now()
        now_dt = datetime.now(timezone.utc)
        expired: list[dict[str, Any]] = []
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT l.id AS lease_id, l.task_id, l.node_id, l.expires_at, t.attempts
                FROM task_leases l
                JOIN factory_tasks t ON t.id = l.task_id
                WHERE l.status='active' AND t.state='leased'
                """
            ).fetchall()
            for row in rows:
                try:
                    if parse_ts(row["expires_at"]) > now_dt:
                        continue
                except Exception:
                    pass
                next_state = "dead_letter" if int(row["attempts"] or 0) >= max_attempts else "queued"
                conn.execute("UPDATE task_leases SET status='expired' WHERE id=?", (row["lease_id"],))
                conn.execute(
                    "UPDATE factory_tasks SET state=?, assigned_node_id=NULL, lease_id=NULL, error=?, updated_at=? WHERE id=?",
                    (next_state, "lease_expired" if next_state == "queued" else "lease_expired_max_attempts", ts, row["task_id"]),
                )
                conn.execute("UPDATE nodes SET workers_busy=MAX(0, workers_busy-1) WHERE id=?", (row["node_id"],))
                conn.execute(
                    "INSERT INTO factory_events(task_id, event, payload_json, ts) VALUES(?,?,?,?)",
                    (row["task_id"], "lease.expired", json_dumps({"lease_id": row["lease_id"], "node_id": row["node_id"], "next_state": next_state}), ts),
                )
                expired.append({"task_id": row["task_id"], "lease_id": row["lease_id"], "next_state": next_state})
        if expired:
            self.audit("factory", "leases.reap", "factory", {"expired": expired})
        return {"expired": expired, "count": len(expired), "checked_at": ts}

    def task_lease_heartbeat(self, task_id: str, lease_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            cur = conn.execute("UPDATE task_leases SET heartbeat_at=? WHERE id=? AND task_id=? AND status='active'", (now(), lease_id, task_id))
        if cur.rowcount == 0:
            raise NotFound(lease_id)
        self.record_factory_event(task_id, "lease.heartbeat", {"lease_id": lease_id})
        return self.get_factory_task(task_id)

    def _release_worker(self, node_id: str | None) -> None:
        if not node_id:
            return
        with self.connect() as conn:
            conn.execute("UPDATE nodes SET workers_busy=MAX(0, workers_busy-1) WHERE id=?", (node_id,))

    def complete_task(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        task = self.get_factory_task(task_id)
        lease_id = payload.get("lease_id") or task.get("lease_id")
        node_id = payload.get("node_id") or task.get("assigned_node_id")
        if not lease_id:
            raise PolicyViolation("lease_id is required")
        artifacts = payload.get("artifacts") or []
        required_names = set(task.get("required_artifacts") or [])
        provided_names = {a.get("name") for a in artifacts if a.get("name") and a.get("payload")}
        missing = sorted(required_names - provided_names)
        verifier_state = "passed" if not missing else "failed"
        ts = now()
        with self.connect() as conn:
            for artifact in artifacts:
                data = str(artifact.get("payload", ""))
                if not data.strip():
                    continue
                artifact_id = artifact.get("id") or f"taskart_{uuid.uuid4().hex[:10]}"
                encoded = data.encode("utf-8")
                sha256 = hashlib.sha256(encoded).hexdigest()
                conn.execute(
                    """
                    INSERT INTO task_artifacts(id, task_id, node_id, name, content_type, payload, sha256, size_bytes, verifier_state, created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (artifact_id, task_id, node_id, artifact.get("name", "RESULT.md"), artifact.get("content_type", "text/markdown"), data, sha256, len(encoded), verifier_state, ts),
                )
            conn.execute("UPDATE task_leases SET status=? WHERE id=? AND task_id=?", ("completed" if verifier_state == "passed" else "failed", lease_id, task_id))
            state = "completed" if verifier_state == "passed" else "blocked"
            result = {"ok": verifier_state == "passed", "verifier_state": verifier_state, "missing_artifacts": missing, "node_id": node_id}
            conn.execute(
                "UPDATE factory_tasks SET state=?, result_json=?, error=?, artifact_path=?, updated_at=? WHERE id=?",
                (state, json_dumps(result), ";".join(missing) if missing else None, f"task_artifacts/{task_id}", ts, task_id),
            )
        self._release_worker(node_id)
        self.record_factory_event(task_id, "worker.executed", {"node_id": node_id})
        self.record_factory_event(task_id, "artifact.written", {"count": len(artifacts)})
        self.record_factory_event(task_id, "verifier.checked", {"state": verifier_state, "missing": missing})
        self.record_factory_event(task_id, "task.completed" if verifier_state == "passed" else "task.blocked", {})
        self.audit("factory", "task.complete", task_id, {"verifier_state": verifier_state})
        return self.get_factory_task(task_id)

    def fail_task(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        task = self.get_factory_task(task_id)
        node_id = payload.get("node_id") or task.get("assigned_node_id")
        with self.connect() as conn:
            if task.get("lease_id"):
                conn.execute("UPDATE task_leases SET status='failed' WHERE id=?", (task["lease_id"],))
            conn.execute("UPDATE factory_tasks SET state='failed', error=?, result_json=?, updated_at=? WHERE id=?", (payload.get("error", "worker_failed"), json_dumps(payload), now(), task_id))
        self._release_worker(node_id)
        self.record_factory_event(task_id, "task.failed", payload)
        self.audit("factory", "task.fail", task_id, payload)
        return self.get_factory_task(task_id)

    def task_artifacts(self, task_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT id, task_id, node_id, name, content_type, sha256, size_bytes, verifier_state, created_at FROM task_artifacts WHERE task_id=? ORDER BY created_at DESC", (task_id,)).fetchall()
        return [dict(row) for row in rows]

    def execute_factory_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Backward-compatible single-server execution path: creates a real queued
        # task, leases it to local-control and completes it with a non-empty
        # artifact through the same verifier path as node-agent workers.
        task = self.create_factory_task({**payload, "required_capabilities": ["factory.local"], "required_artifacts": ["RESULT.md"]})
        lease = self.lease_task({"node_id": os.environ.get("VISTA_NODE_ID", "local-control"), "lease_seconds": 120})
        leased_task = lease.get("task")
        if not leased_task:
            raise PolicyViolation("local-control could not lease the task")
        result_md = f"# Vista Factory Result\n\nTask: {task['title']}\nMode: controlled-local\nCompleted at: {now()}\n"
        completed = self.complete_task(leased_task["id"], {"lease_id": lease["lease"]["id"], "node_id": "local-control", "artifacts": [{"name": "RESULT.md", "content_type": "text/markdown", "payload": result_md}]})
        return {"task": completed, "events": completed["events"], "artifact": completed["artifacts"][0] if completed["artifacts"] else None}

    def factory_events(self, task_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if task_id:
                rows = conn.execute("SELECT * FROM factory_events WHERE task_id=? ORDER BY id ASC", (task_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM factory_events ORDER BY id DESC LIMIT 200").fetchall()
        return [dict(row) | {"payload": json_loads(row["payload_json"], {})} for row in rows]

    def factory_stats(self) -> dict[str, Any]:
        with self.connect() as conn:
            states = {row["state"]: row["count"] for row in conn.execute("SELECT state, COUNT(*) AS count FROM factory_tasks GROUP BY state").fetchall()}
            nodes = self.list_nodes()
        return {"states": states, "nodes": len(nodes), "events": len(self.factory_events()), "updated_at": now()}

    def readiness(self) -> dict[str, Any]:
        return {
            "market_mvp": "ready_for_controlled_pilot",
            "production_mode": "single_server_real_persistence_plus_real_factory_contracts",
            "live_fleet_canary": "run required on real worker nodes before 24/7 autonomous claim",
            "checks": [
                "sqlite_persistence",
                "session_workbench_state",
                "estimate_crud",
                "proposal_generation",
                "artifact_download",
                "role_capability_policy",
                "node_registry",
                "task_queue",
                "lease_manager",
                "node_agent_execution_loop",
                "artifact_upload",
                "verifier_gate",
                "node_token_auth_optional",
                "signed_node_requests_optional",
                "lease_expiry_reaper",
                "node_drain_resume",
                "fleet_health_snapshot",
                "artifact_sha256",
                "multi_node_canary_script",
            ],
        }


STORE = VistaStore()
