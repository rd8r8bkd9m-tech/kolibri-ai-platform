BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS auth_throttles (
    key_hash TEXT PRIMARY KEY
        CHECK (length(key_hash) = 64),
    failure_count INTEGER NOT NULL
        CHECK (failure_count >= 0),
    window_started_at INTEGER NOT NULL,
    blocked_until INTEGER,
    updated_at INTEGER NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS idx_auth_throttles_updated
    ON auth_throttles(updated_at);

PRAGMA user_version = 2;

COMMIT;
