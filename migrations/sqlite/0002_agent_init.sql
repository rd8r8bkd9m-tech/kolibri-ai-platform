CREATE TABLE IF NOT EXISTS agent_state (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  current_task_id TEXT,
  last_heartbeat_at TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_cache (
  task_id TEXT PRIMARY KEY,
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

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

CREATE TABLE IF NOT EXISTS workspace_cache (
  id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS artifact_queue (
  id TEXT PRIMARY KEY,
  task_run_id TEXT NOT NULL,
  artifact_type TEXT NOT NULL,
  name TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'queued',
  created_at TEXT NOT NULL
);
