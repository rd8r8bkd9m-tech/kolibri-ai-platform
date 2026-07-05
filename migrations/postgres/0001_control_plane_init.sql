CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS nodes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text not null,
  hostname text,
  ip text,
  region text,
  status text not null,
  capabilities jsonb not null default '{}'::jsonb,
  last_seen_at timestamptz,
  created_at timestamptz not null,
  updated_at timestamptz not null
);

CREATE TABLE IF NOT EXISTS agents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  node_id uuid references nodes(id),
  name text not null,
  kind text not null,
  status text not null,
  version text,
  capabilities jsonb not null default '{}'::jsonb,
  current_task_id uuid,
  last_heartbeat_at timestamptz,
  created_at timestamptz not null,
  updated_at timestamptz not null
);

CREATE TABLE IF NOT EXISTS tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid,
  title text not null,
  description text,
  status text not null,
  priority text not null,
  created_by text not null,
  created_at timestamptz not null,
  updated_at timestamptz not null
);

CREATE TABLE IF NOT EXISTS task_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id uuid references tasks(id),
  agent_id uuid references agents(id),
  node_id uuid references nodes(id),
  status text not null,
  started_at timestamptz,
  finished_at timestamptz,
  exit_code integer,
  error_summary text,
  artifact_ids jsonb not null default '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS command_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_run_id uuid references task_runs(id),
  command text not null,
  cwd text,
  sandbox_profile text,
  status text not null,
  exit_code integer,
  stdout_ref text,
  stderr_ref text,
  started_at timestamptz,
  finished_at timestamptz
);

CREATE TABLE IF NOT EXISTS events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  stream text not null,
  subject text not null,
  event_type text not null,
  aggregate_id uuid,
  payload_json jsonb not null,
  trace_id text,
  correlation_id text,
  actor text,
  created_at timestamptz not null
);

CREATE TABLE IF NOT EXISTS audit_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor text,
  action text not null,
  resource text,
  decision text,
  reason text,
  payload_json jsonb not null default '{}'::jsonb,
  trace_id text,
  created_at timestamptz not null
);

CREATE TABLE IF NOT EXISTS artifacts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_run_id uuid references task_runs(id),
  artifact_type text not null,
  name text not null,
  path text not null,
  sha256 text not null,
  size_bytes bigint,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null
);

CREATE TABLE IF NOT EXISTS policies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text not null,
  version text not null,
  body_json jsonb not null,
  created_at timestamptz not null
);

CREATE TABLE IF NOT EXISTS secret_refs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider text not null,
  path text not null,
  scope text not null,
  version text,
  created_at timestamptz not null
);

CREATE TABLE IF NOT EXISTS model_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id uuid,
  provider text not null,
  model text not null,
  input_tokens integer,
  output_tokens integer,
  cost_estimate numeric,
  latency_ms integer,
  finish_reason text,
  trace_id text,
  created_at timestamptz not null
);
