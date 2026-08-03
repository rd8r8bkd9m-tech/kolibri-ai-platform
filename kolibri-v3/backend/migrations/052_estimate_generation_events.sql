PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS estimate_generation_events (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    event_type TEXT NOT NULL CHECK (length(event_type) BETWEEN 1 AND 120),
    event_json TEXT NOT NULL CHECK (json_valid(event_json)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, run_id, sequence),
    FOREIGN KEY (tenant_id, run_id) REFERENCES estimate_generation_runs (tenant_id, id) ON DELETE CASCADE
) STRICT;

CREATE INDEX IF NOT EXISTS ix_estimate_generation_events_replay
    ON estimate_generation_events (tenant_id, run_id, sequence);

PRAGMA user_version = 52;
