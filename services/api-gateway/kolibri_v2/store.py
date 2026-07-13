from __future__ import annotations

import hashlib
import json
import sqlite3
import secrets
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=30000;

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  role TEXT NOT NULL DEFAULT 'client',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  name TEXT NOT NULL,
  key_prefix TEXT NOT NULL,
  key_hash TEXT NOT NULL UNIQUE,
  role TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_used_at TEXT,
  revoked_at TEXT,
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);
CREATE INDEX IF NOT EXISTS api_keys_session_idx ON api_keys(session_id, created_at DESC);
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  title TEXT NOT NULL,
  deleted_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);
CREATE INDEX IF NOT EXISTS projects_session_idx ON projects(session_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  response_id TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(project_id, response_id, role),
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
CREATE INDEX IF NOT EXISTS messages_project_idx ON messages(project_id, created_at);
CREATE TABLE IF NOT EXISTS responses (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  status TEXT NOT NULL,
  model TEXT NOT NULL,
  input_json TEXT NOT NULL,
  output_text TEXT NOT NULL DEFAULT '',
  error_json TEXT,
  previous_response_id TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  request_hash TEXT NOT NULL,
  idempotency_key TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  completed_at TEXT,
  UNIQUE(session_id, idempotency_key),
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
CREATE INDEX IF NOT EXISTS responses_status_idx ON responses(status, updated_at);
CREATE TABLE IF NOT EXISTS response_events (
  response_id TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  type TEXT NOT NULL,
  data_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(response_id, sequence),
  FOREIGN KEY(response_id) REFERENCES responses(id)
);
CREATE TABLE IF NOT EXISTS estimates (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  title TEXT NOT NULL,
  client_name TEXT NOT NULL DEFAULT '',
  region TEXT NOT NULL DEFAULT '',
  currency TEXT NOT NULL DEFAULT 'RUB',
  overhead_pct TEXT NOT NULL DEFAULT '0',
  margin_pct TEXT NOT NULL DEFAULT '0',
  discount_pct TEXT NOT NULL DEFAULT '0',
  tax_pct TEXT NOT NULL DEFAULT '0',
  status TEXT NOT NULL DEFAULT 'needs_input',
  revision INTEGER NOT NULL DEFAULT 0,
  subtotal TEXT NOT NULL DEFAULT '0',
  total TEXT NOT NULL DEFAULT '0',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
CREATE TABLE IF NOT EXISTS estimate_items (
  id TEXT PRIMARY KEY,
  estimate_id TEXT NOT NULL,
  section TEXT NOT NULL,
  name TEXT NOT NULL,
  unit TEXT NOT NULL,
  quantity TEXT NOT NULL,
  unit_price TEXT NOT NULL,
  coefficient TEXT NOT NULL DEFAULT '1',
  source_id TEXT,
  position INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(estimate_id) REFERENCES estimates(id)
);
CREATE TABLE IF NOT EXISTS estimate_sources (
  id TEXT PRIMARY KEY,
  estimate_id TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  region TEXT NOT NULL,
  price_date TEXT NOT NULL,
  unit TEXT NOT NULL,
  verification_status TEXT NOT NULL DEFAULT 'unverified',
  retrieved_at TEXT NOT NULL,
  FOREIGN KEY(estimate_id) REFERENCES estimates(id)
);
CREATE TABLE IF NOT EXISTS estimate_revisions (
  id TEXT PRIMARY KEY,
  estimate_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  snapshot_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(estimate_id, revision),
  FOREIGN KEY(estimate_id) REFERENCES estimates(id)
);
CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  project_id TEXT,
  estimate_id TEXT,
  task_id TEXT,
  revision INTEGER,
  name TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  size INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  verifier_status TEXT NOT NULL DEFAULT 'verified',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS artifacts_estimate_idx ON artifacts(estimate_id, revision);
CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY,
  hostname TEXT NOT NULL,
  capabilities_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'online',
  draining INTEGER NOT NULL DEFAULT 0,
  last_heartbeat TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  session_id TEXT,
  project_id TEXT,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  input_json TEXT NOT NULL,
  required_capabilities_json TEXT NOT NULL,
  required_artifacts_json TEXT NOT NULL,
  attempt INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  attempt_id TEXT,
  lease_id TEXT,
  lease_owner TEXT,
  fencing_token INTEGER NOT NULL DEFAULT 0,
  lease_until TEXT,
  result_json TEXT,
  result_hash TEXT,
  verifier_binding TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tasks_status_idx ON tasks(status, created_at);
CREATE TABLE IF NOT EXISTS task_events (
  task_id TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  type TEXT NOT NULL,
  data_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(task_id, sequence),
  FOREIGN KEY(task_id) REFERENCES tasks(id)
);
CREATE TABLE IF NOT EXISTS formula_traces (
  id TEXT PRIMARY KEY,
  session_id TEXT,
  consent INTEGER NOT NULL DEFAULT 0,
  provenance TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'candidate',
  created_at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with self._lock, self.connection() as conn:
            conn.execute(sql, tuple(params))

    def fetchone(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        with self._lock, self.connection() as conn:
            return self.row(conn.execute(sql, tuple(params)).fetchone())

    def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock, self.connection() as conn:
            return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]

    # sessions/projects/messages
    def create_session(self, role: str = "client") -> dict[str, Any]:
        now = utcnow(); sid = new_id("sess")
        self.execute("INSERT INTO sessions VALUES(?,?,?,?)", (sid, role, now, now))
        return self.get_session(sid) or {}

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self.fetchone("SELECT * FROM sessions WHERE id=?", (session_id,))

    def ensure_session(self, session_id: str, role: str = "client") -> dict[str, Any]:
        existing = self.get_session(session_id)
        if existing:
            return existing
        now = utcnow()
        self.execute("INSERT INTO sessions VALUES(?,?,?,?)", (session_id, role, now, now))
        return self.get_session(session_id) or {}

    @staticmethod
    def api_key_hash(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode()).hexdigest()

    def create_api_key(
        self,
        session_id: str,
        role: str,
        name: str,
        raw_key: str | None = None,
        key_id: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        raw = raw_key or f"sk-kolibri-{secrets.token_urlsafe(32)}"
        key_hash = self.api_key_hash(raw)
        existing = self.fetchone("SELECT * FROM api_keys WHERE key_hash=?", (key_hash,))
        if existing:
            return existing, raw
        now = utcnow()
        kid = key_id or new_id("key")
        prefix = raw[:18]
        self.execute(
            "INSERT INTO api_keys(id,session_id,name,key_prefix,key_hash,role,created_at,last_used_at,revoked_at) VALUES(?,?,?,?,?,?,?,?,NULL)",
            (kid, session_id, name, prefix, key_hash, role, now, None),
        )
        return self.fetchone("SELECT * FROM api_keys WHERE id=?", (kid,)) or {}, raw

    def seed_api_key(self, raw_key: str, role: str, name: str) -> dict[str, Any]:
        digest = self.api_key_hash(raw_key)
        session_id = f"sess_api_{digest[:24]}"
        key_id = f"key_{digest[:24]}"
        self.ensure_session(session_id, role)
        row, _ = self.create_api_key(session_id, role, name, raw_key=raw_key, key_id=key_id)
        return row

    def authenticate_api_key(self, raw_key: str) -> dict[str, Any] | None:
        digest = self.api_key_hash(raw_key)
        row = self.fetchone("SELECT * FROM api_keys WHERE key_hash=? AND revoked_at IS NULL", (digest,))
        if not row:
            return None
        self.execute("UPDATE api_keys SET last_used_at=? WHERE id=?", (utcnow(), row["id"]))
        row["last_used_at"] = utcnow()
        return row

    def list_api_keys(self, session_id: str, include_all: bool = False) -> list[dict[str, Any]]:
        if include_all:
            return self.fetchall("SELECT * FROM api_keys ORDER BY created_at DESC")
        return self.fetchall("SELECT * FROM api_keys WHERE session_id=? ORDER BY created_at DESC", (session_id,))

    def revoke_api_key(self, key_id: str, session_id: str, include_all: bool = False) -> dict[str, Any] | None:
        row = self.fetchone("SELECT * FROM api_keys WHERE id=?", (key_id,))
        if not row or (not include_all and row["session_id"] != session_id):
            return None
        if not row.get("revoked_at"):
            self.execute("UPDATE api_keys SET revoked_at=? WHERE id=?", (utcnow(), key_id))
        return self.fetchone("SELECT * FROM api_keys WHERE id=?", (key_id,))

    def create_project(self, session_id: str, title: str = "Новый проект") -> dict[str, Any]:
        now = utcnow(); pid = new_id("proj")
        self.execute("INSERT INTO projects VALUES(?,?,?,?,?,?)", (pid, session_id, title, None, now, now))
        return self.get_project(pid, session_id) or {}

    def list_projects(self, session_id: str, include_deleted: bool = False) -> list[dict[str, Any]]:
        where = "session_id=?" if include_deleted else "session_id=? AND deleted_at IS NULL"
        return self.fetchall(f"SELECT * FROM projects WHERE {where} ORDER BY updated_at DESC", (session_id,))

    def get_project(self, project_id: str, session_id: str) -> dict[str, Any] | None:
        return self.fetchone("SELECT * FROM projects WHERE id=? AND session_id=?", (project_id, session_id))

    def update_project(self, project_id: str, session_id: str, title: str) -> dict[str, Any] | None:
        self.execute("UPDATE projects SET title=?, updated_at=? WHERE id=? AND session_id=?", (title, utcnow(), project_id, session_id))
        return self.get_project(project_id, session_id)

    def soft_delete_project(self, project_id: str, session_id: str) -> None:
        now = utcnow(); self.execute("UPDATE projects SET deleted_at=?, updated_at=? WHERE id=? AND session_id=?", (now, now, project_id, session_id))

    def restore_project(self, project_id: str, session_id: str) -> dict[str, Any] | None:
        self.execute("UPDATE projects SET deleted_at=NULL, updated_at=? WHERE id=? AND session_id=?", (utcnow(), project_id, session_id))
        return self.get_project(project_id, session_id)

    def add_message(self, project_id: str, role: str, content: str, response_id: str | None = None) -> dict[str, Any]:
        mid = new_id("msg"); now = utcnow()
        try:
            self.execute("INSERT INTO messages VALUES(?,?,?,?,?,?)", (mid, project_id, role, content, response_id, now))
        except sqlite3.IntegrityError:
            existing = self.fetchone("SELECT * FROM messages WHERE project_id=? AND response_id=? AND role=?", (project_id, response_id, role))
            return existing or {}
        return self.fetchone("SELECT * FROM messages WHERE id=?", (mid,)) or {}

    def update_message_for_response(self, response_id: str, content: str) -> None:
        self.execute("UPDATE messages SET content=? WHERE response_id=? AND role='assistant'", (content, response_id))

    def list_messages(self, project_id: str) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM messages WHERE project_id=? ORDER BY created_at", (project_id,))

    # responses/events
    def create_response(self, session_id: str, project_id: str, payload: dict[str, Any], request_hash: str, idempotency_key: str | None) -> tuple[dict[str, Any], bool]:
        if idempotency_key:
            existing = self.fetchone("SELECT * FROM responses WHERE session_id=? AND idempotency_key=?", (session_id, idempotency_key))
            if existing:
                if existing["request_hash"] != request_hash:
                    raise ValueError("idempotency_conflict")
                return existing, False
        rid = new_id("resp"); now = utcnow()
        self.execute(
            "INSERT INTO responses(id,session_id,project_id,status,model,input_json,previous_response_id,metadata_json,request_hash,idempotency_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, session_id, project_id, "queued", payload.get("model", "kolibri"), json_dumps(payload.get("input")), payload.get("previous_response_id"), json_dumps(payload.get("metadata", {})), request_hash, idempotency_key, now, now),
        )
        self.append_response_event(rid, "response.created", {"response_id": rid, "status": "queued"})
        return self.get_response(rid, session_id) or {}, True

    def get_response(self, response_id: str, session_id: str | None = None) -> dict[str, Any] | None:
        if session_id:
            return self.fetchone("SELECT * FROM responses WHERE id=? AND session_id=?", (response_id, session_id))
        return self.fetchone("SELECT * FROM responses WHERE id=?", (response_id,))

    def update_response(self, response_id: str, *, status: str | None = None, output_text: str | None = None, error: dict[str, Any] | None = None) -> dict[str, Any] | None:
        current = self.get_response(response_id)
        if not current:
            return None
        values = {
            "status": status if status is not None else current["status"],
            "output_text": output_text if output_text is not None else current["output_text"],
            "error_json": json_dumps(error) if error is not None else current["error_json"],
            "updated_at": utcnow(),
            "completed_at": utcnow() if status in {"completed", "failed", "cancelled"} else current["completed_at"],
        }
        self.execute("UPDATE responses SET status=?, output_text=?, error_json=?, updated_at=?, completed_at=? WHERE id=?", (*values.values(), response_id))
        return self.get_response(response_id)

    def append_response_event(self, response_id: str, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        row = self.fetchone("SELECT COALESCE(MAX(sequence),0)+1 AS seq FROM response_events WHERE response_id=?", (response_id,))
        seq = int(row["seq"] if row else 1); now = utcnow()
        self.execute("INSERT INTO response_events VALUES(?,?,?,?,?)", (response_id, seq, event_type, json_dumps(data), now))
        return {"response_id": response_id, "sequence": seq, "type": event_type, "data": data, "created_at": now}

    def list_response_events(self, response_id: str, starting_after: int = 0) -> list[dict[str, Any]]:
        rows = self.fetchall("SELECT * FROM response_events WHERE response_id=? AND sequence>? ORDER BY sequence", (response_id, starting_after))
        for row in rows:
            row["data"] = json_loads(row.pop("data_json"), {})
        return rows

    def incomplete_responses(self) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM responses WHERE status IN ('queued','planning','running','verifying') ORDER BY created_at")

    # estimate helpers
    def create_estimate(self, session_id: str, project_id: str, title: str, client_name: str = "", region: str = "") -> dict[str, Any]:
        eid = new_id("est"); now = utcnow()
        self.execute("INSERT INTO estimates(id,session_id,project_id,title,client_name,region,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (eid, session_id, project_id, title, client_name, region, now, now))
        self.save_revision(eid)
        return self.get_estimate(eid, session_id) or {}

    def list_estimates(self, session_id: str, project_id: str | None = None) -> list[dict[str, Any]]:
        if project_id:
            rows = self.fetchall("SELECT * FROM estimates WHERE session_id=? AND project_id=? ORDER BY updated_at DESC", (session_id, project_id))
        else:
            rows = self.fetchall("SELECT * FROM estimates WHERE session_id=? ORDER BY updated_at DESC", (session_id,))
        return [self.hydrate_estimate(row) for row in rows]

    def get_estimate(self, estimate_id: str, session_id: str | None = None) -> dict[str, Any] | None:
        row = self.fetchone("SELECT * FROM estimates WHERE id=?" + (" AND session_id=?" if session_id else ""), (estimate_id, session_id) if session_id else (estimate_id,))
        return self.hydrate_estimate(row) if row else None

    def hydrate_estimate(self, row: dict[str, Any]) -> dict[str, Any]:
        row = dict(row)
        row["items"] = self.fetchall("SELECT * FROM estimate_items WHERE estimate_id=? ORDER BY position, created_at", (row["id"],))
        row["sources"] = self.fetchall("SELECT * FROM estimate_sources WHERE estimate_id=? ORDER BY retrieved_at DESC", (row["id"],))
        return row

    def update_estimate_fields(self, estimate_id: str, session_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"title","client_name","region","overhead_pct","margin_pct","discount_pct","tax_pct"}
        data = {key: str(value) for key, value in fields.items() if key in allowed}
        if data:
            data["updated_at"] = utcnow()
            setters = ",".join(f"{key}=?" for key in data)
            self.execute(f"UPDATE estimates SET {setters} WHERE id=? AND session_id=?", (*data.values(), estimate_id, session_id))
        return self.get_estimate(estimate_id, session_id)

    def add_estimate_item(self, estimate_id: str, item: dict[str, Any]) -> dict[str, Any]:
        iid = new_id("item"); now = utcnow()
        self.execute("INSERT INTO estimate_items VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (iid, estimate_id, item.get("section","Работы"), item["name"], item.get("unit","шт."), str(item.get("quantity","0")), str(item.get("unit_price","0")), str(item.get("coefficient","1")), item.get("source_id"), int(item.get("position",0)), now, now))
        return self.fetchone("SELECT * FROM estimate_items WHERE id=?", (iid,)) or {}

    def update_estimate_item(self, estimate_id: str, item_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"section","name","unit","quantity","unit_price","coefficient","source_id","position"}
        data = {key: (int(value) if key == "position" else str(value) if value is not None else None) for key, value in fields.items() if key in allowed}
        if data:
            data["updated_at"] = utcnow(); setters=",".join(f"{key}=?" for key in data)
            self.execute(f"UPDATE estimate_items SET {setters} WHERE id=? AND estimate_id=?", (*data.values(), item_id, estimate_id))
        return self.fetchone("SELECT * FROM estimate_items WHERE id=? AND estimate_id=?", (item_id, estimate_id))

    def delete_estimate_item(self, estimate_id: str, item_id: str) -> None:
        self.execute("DELETE FROM estimate_items WHERE id=? AND estimate_id=?", (item_id, estimate_id))

    def add_source(self, estimate_id: str, source: dict[str, Any]) -> dict[str, Any]:
        sid = new_id("src"); now=utcnow()
        self.execute("INSERT INTO estimate_sources VALUES(?,?,?,?,?,?,?,?,?)", (sid, estimate_id, source["title"], source["url"], source["region"], source["price_date"], source["unit"], source.get("verification_status","unverified"), now))
        return self.fetchone("SELECT * FROM estimate_sources WHERE id=?", (sid,)) or {}

    def save_revision(self, estimate_id: str) -> dict[str, Any]:
        estimate = self.get_estimate(estimate_id)
        if not estimate:
            raise KeyError(estimate_id)
        next_rev = int(estimate["revision"]) + 1
        snapshot = dict(estimate); snapshot["revision"] = next_rev
        rid = new_id("rev"); now=utcnow()
        self.execute("INSERT INTO estimate_revisions VALUES(?,?,?,?,?)", (rid, estimate_id, next_rev, json_dumps(snapshot), now))
        self.execute("UPDATE estimates SET revision=?, updated_at=? WHERE id=?", (next_rev, now, estimate_id))
        return {"id": rid, "estimate_id": estimate_id, "revision": next_rev, "snapshot": snapshot, "created_at": now}

    def list_revisions(self, estimate_id: str) -> list[dict[str, Any]]:
        rows=self.fetchall("SELECT * FROM estimate_revisions WHERE estimate_id=? ORDER BY revision DESC", (estimate_id,))
        for row in rows: row["snapshot"] = json_loads(row.pop("snapshot_json"), {})
        return rows

    def set_estimate_totals(self, estimate_id: str, status: str, subtotal: str, total: str) -> None:
        self.execute("UPDATE estimates SET status=?, subtotal=?, total=?, updated_at=? WHERE id=?", (status, subtotal, total, utcnow(), estimate_id))

    # artifacts
    def add_artifact(self, *, session_id: str, name: str, mime_type: str, storage_path: str, size: int, sha256: str, project_id: str | None = None, estimate_id: str | None = None, task_id: str | None = None, revision: int | None = None) -> dict[str, Any]:
        aid = new_id("art"); now=utcnow()
        self.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (aid, session_id, project_id, estimate_id, task_id, revision, name, mime_type, size, sha256, storage_path, "verified", now))
        return self.fetchone("SELECT * FROM artifacts WHERE id=?", (aid,)) or {}

    def list_artifacts(self, session_id: str, project_id: str | None = None, estimate_id: str | None = None) -> list[dict[str, Any]]:
        clauses=["session_id=?"]; params:[Any]=[session_id]
        if project_id: clauses.append("project_id=?"); params.append(project_id)
        if estimate_id: clauses.append("estimate_id=?"); params.append(estimate_id)
        return self.fetchall("SELECT * FROM artifacts WHERE " + " AND ".join(clauses) + " ORDER BY created_at DESC", params)

    def get_artifact(self, artifact_id: str, session_id: str | None = None) -> dict[str, Any] | None:
        sql="SELECT * FROM artifacts WHERE id=?"; params:[Any]=[artifact_id]
        if session_id: sql += " AND session_id=?"; params.append(session_id)
        return self.fetchone(sql, params)

    # tasks/nodes
    def upsert_node(self, node_id: str, hostname: str, capabilities: list[str], status: str = "online") -> dict[str, Any]:
        now=utcnow(); existing=self.fetchone("SELECT * FROM nodes WHERE id=?", (node_id,))
        if existing:
            self.execute("UPDATE nodes SET hostname=?,capabilities_json=?,status=?,last_heartbeat=?,updated_at=? WHERE id=?", (hostname,json_dumps(capabilities),status,now,now,node_id))
        else:
            self.execute("INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?)", (node_id,hostname,json_dumps(capabilities),status,0,now,now,now))
        return self.get_node(node_id) or {}

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        row=self.fetchone("SELECT * FROM nodes WHERE id=?", (node_id,))
        if row: row["capabilities"] = json_loads(row.pop("capabilities_json"), [])
        return row

    def list_nodes(self) -> list[dict[str, Any]]:
        rows=self.fetchall("SELECT * FROM nodes ORDER BY id")
        for row in rows: row["capabilities"] = json_loads(row.pop("capabilities_json"), [])
        return rows

    def create_task(self, payload: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
        tid=new_id("task"); now=utcnow()
        self.execute("INSERT INTO tasks(id,session_id,project_id,kind,title,input_json,required_capabilities_json,required_artifacts_json,max_attempts,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (tid,session_id,payload.get("project_id"),payload.get("kind","generic"),payload.get("title","Kolibri task"),json_dumps(payload.get("input",{})),json_dumps(payload.get("required_capabilities",[])),json_dumps(payload.get("required_artifacts",["RESULT.md"])),int(payload.get("max_attempts",3)),now,now))
        self.append_task_event(tid,"task.created",{"status":"queued"})
        return self.get_task(tid) or {}

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        row=self.fetchone("SELECT * FROM tasks WHERE id=?", (task_id,))
        if row:
            for key, out in [("input_json","input"),("required_capabilities_json","required_capabilities"),("required_artifacts_json","required_artifacts"),("result_json","result")]:
                row[out]=json_loads(row.pop(key), {} if key in {"input_json","result_json"} else [])
        return row

    def list_tasks(self) -> list[dict[str, Any]]:
        return [self.get_task(row["id"]) or {} for row in self.fetchall("SELECT id FROM tasks ORDER BY created_at DESC")]

    def append_task_event(self, task_id: str, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        row=self.fetchone("SELECT COALESCE(MAX(sequence),0)+1 AS seq FROM task_events WHERE task_id=?", (task_id,)); seq=int(row["seq"] if row else 1); now=utcnow()
        self.execute("INSERT INTO task_events VALUES(?,?,?,?,?)", (task_id,seq,event_type,json_dumps(data),now))
        return {"task_id":task_id,"sequence":seq,"type":event_type,"data":data,"created_at":now}

    def list_task_events(self, task_id: str) -> list[dict[str, Any]]:
        rows=self.fetchall("SELECT * FROM task_events WHERE task_id=? ORDER BY sequence", (task_id,))
        for row in rows: row["data"]=json_loads(row.pop("data_json"),{})
        return rows

    def lease_task(self, node_id: str, capabilities: list[str], lease_seconds: int = 60) -> dict[str, Any] | None:
        now_dt=datetime.now(timezone.utc); now=now_dt.isoformat(); until=(now_dt+timedelta(seconds=lease_seconds)).isoformat()
        self.reap_expired_leases()
        with self._lock, self.connection() as conn:
            candidates=conn.execute("SELECT * FROM tasks WHERE status='queued' ORDER BY created_at").fetchall()
            chosen=None
            capset=set(capabilities)
            for candidate in candidates:
                required=set(json_loads(candidate["required_capabilities_json"], []))
                if required.issubset(capset): chosen=candidate; break
            if chosen is None: return None
            attempt=int(chosen["attempt"])+1
            attempt_id=new_id("attempt"); lease_id=new_id("lease"); fence=int(chosen["fencing_token"])+1
            conn.execute("UPDATE tasks SET status='leased',attempt=?,attempt_id=?,lease_id=?,lease_owner=?,fencing_token=?,lease_until=?,updated_at=? WHERE id=? AND status='queued'", (attempt,attempt_id,lease_id,node_id,fence,until,now,chosen["id"]))
        self.append_task_event(chosen["id"],"lease.granted",{"node_id":node_id,"attempt_id":attempt_id,"lease_id":lease_id,"fencing_token":fence,"lease_until":until})
        return self.get_task(chosen["id"])

    def heartbeat_task(self, task_id: str, node_id: str, lease_id: str, fencing_token: int, lease_seconds: int = 60) -> dict[str, Any]:
        task=self.get_task(task_id)
        if not task or task["lease_owner"]!=node_id or task["lease_id"]!=lease_id or int(task["fencing_token"])!=int(fencing_token):
            raise ValueError("stale_lease")
        until=(datetime.now(timezone.utc)+timedelta(seconds=lease_seconds)).isoformat()
        self.execute("UPDATE tasks SET status='running',lease_until=?,updated_at=? WHERE id=?", (until,utcnow(),task_id))
        self.append_task_event(task_id,"lease.heartbeat",{"node_id":node_id,"lease_until":until})
        return self.get_task(task_id) or {}

    def reap_expired_leases(self) -> list[str]:
        now=utcnow(); expired=self.fetchall("SELECT id,attempt,max_attempts FROM tasks WHERE status IN ('leased','running') AND lease_until IS NOT NULL AND lease_until<?", (now,)); ids=[]
        for row in expired:
            ids.append(row["id"]); status="queued" if int(row["attempt"]) < int(row["max_attempts"]) else "dead_letter"
            self.execute("UPDATE tasks SET status=?,attempt_id=NULL,lease_id=NULL,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?", (status,now,row["id"]))
            self.append_task_event(row["id"],"lease.expired",{"next_status":status})
        return ids

    def complete_task(self, task_id: str, node_id: str, lease_id: str, fencing_token: int, result: dict[str, Any]) -> dict[str, Any]:
        task=self.get_task(task_id)
        if not task or task["lease_owner"]!=node_id or task["lease_id"]!=lease_id or int(task["fencing_token"])!=int(fencing_token): raise ValueError("stale_lease")
        artifacts=self.fetchall("SELECT * FROM artifacts WHERE task_id=?", (task_id,)); names={a["name"] for a in artifacts if int(a["size"])>0}
        missing=[name for name in task["required_artifacts"] if name not in names]
        if missing: raise ValueError("missing_artifacts:"+",".join(missing))
        result_hash=hashlib.sha256(json_dumps(result).encode()).hexdigest(); binding=hashlib.sha256((task_id+task["attempt_id"]+str(fencing_token)+result_hash).encode()).hexdigest()
        self.execute("UPDATE tasks SET status='completed',result_json=?,result_hash=?,verifier_binding=?,lease_until=NULL,updated_at=? WHERE id=?", (json_dumps(result),result_hash,binding,utcnow(),task_id))
        self.append_task_event(task_id,"worker.executed",{"result_hash":result_hash})
        self.append_task_event(task_id,"verifier.checked",{"verdict":"accepted","binding":binding})
        self.append_task_event(task_id,"task.completed",{"status":"completed"})
        return self.get_task(task_id) or {}

    def fail_task(self, task_id: str, reason: str) -> dict[str, Any]:
        task=self.get_task(task_id)
        if not task: raise KeyError(task_id)
        status="queued" if int(task["attempt"]) < int(task["max_attempts"]) else "dead_letter"
        self.execute("UPDATE tasks SET status=?,result_json=?,lease_id=NULL,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?", (status,json_dumps({"error":reason}),utcnow(),task_id))
        self.append_task_event(task_id,"task.failed",{"reason":reason,"next_status":status})
        return self.get_task(task_id) or {}
