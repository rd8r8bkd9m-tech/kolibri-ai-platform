CREATE TABLE IF NOT EXISTS local_events (
  id TEXT PRIMARY KEY,
  stream TEXT NOT NULL,
  subject TEXT NOT NULL,
  event_type TEXT NOT NULL,
  aggregate_id TEXT,
  payload_json TEXT NOT NULL,
  trace_id TEXT,
  correlation_id TEXT,
  actor TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS local_nodes (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  hostname TEXT NOT NULL,
  ip TEXT NOT NULL,
  region TEXT,
  status TEXT NOT NULL,
  capabilities_json TEXT NOT NULL DEFAULT '[]',
  last_seen_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS local_agents (
  id TEXT PRIMARY KEY,
  node_id TEXT NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  version TEXT,
  capabilities_json TEXT NOT NULL DEFAULT '[]',
  current_task_id TEXT,
  last_heartbeat_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS local_tasks (
  id TEXT PRIMARY KEY,
  project_id TEXT,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  status TEXT NOT NULL,
  priority TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS local_settings (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
  id TEXT PRIMARY KEY,
  actor TEXT,
  action TEXT NOT NULL,
  resource TEXT,
  decision TEXT,
  reason TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}',
  trace_id TEXT,
  created_at TEXT NOT NULL
);
