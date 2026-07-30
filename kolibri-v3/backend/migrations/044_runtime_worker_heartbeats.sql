PRAGMA foreign_keys = ON;

BEGIN IMMEDIATE;

CREATE TABLE runtime_worker_heartbeats (
    worker_kind TEXT PRIMARY KEY
        CHECK (worker_kind IN ('product-run', 'provider-enrollment')),
    instance_id TEXT NOT NULL
        CHECK (
            length(instance_id) BETWEEN 8 AND 160
            AND instance_id NOT GLOB '*[^A-Za-z0-9._:-]*'
        ),
    release_id TEXT NOT NULL
        CHECK (
            length(release_id) BETWEEN 1 AND 128
            AND release_id NOT GLOB '*[^A-Za-z0-9._-]*'
        ),
    release_commit TEXT NOT NULL
        CHECK (
            length(release_commit) = 40
            AND release_commit NOT GLOB '*[^0-9a-f]*'
        ),
    process_id INTEGER NOT NULL CHECK (process_id >= 1),
    started_at INTEGER NOT NULL CHECK (started_at >= 0),
    heartbeat_at INTEGER NOT NULL CHECK (heartbeat_at >= started_at)
) STRICT;

CREATE INDEX ix_runtime_worker_heartbeats_freshness
    ON runtime_worker_heartbeats (heartbeat_at, worker_kind);

PRAGMA user_version = 44;

COMMIT;
