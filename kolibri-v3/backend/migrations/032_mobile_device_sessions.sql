BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS mobile_device_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    platform TEXT NOT NULL CHECK (platform IN ('ios', 'android')),
    device_name TEXT NOT NULL CHECK (length(device_name) BETWEEN 1 AND 120),
    app_version TEXT NOT NULL CHECK (length(app_version) BETWEEN 1 AND 64),
    created_at INTEGER NOT NULL,
    last_refreshed_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    revoked_at INTEGER,
    CHECK (expires_at > created_at),
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE CASCADE
) STRICT;

CREATE INDEX IF NOT EXISTS idx_mobile_device_sessions_user
    ON mobile_device_sessions(tenant_id, user_id, expires_at);

CREATE INDEX IF NOT EXISTS idx_mobile_device_sessions_active
    ON mobile_device_sessions(id, expires_at)
    WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS mobile_refresh_tokens (
    id TEXT PRIMARY KEY,
    device_session_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE CHECK (length(token_hash) = 64),
    generation INTEGER NOT NULL CHECK (generation >= 0),
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    consumed_at INTEGER,
    revoked_at INTEGER,
    replaced_by_id TEXT,
    CHECK (expires_at > created_at),
    UNIQUE (device_session_id, generation),
    FOREIGN KEY (device_session_id)
        REFERENCES mobile_device_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (replaced_by_id)
        REFERENCES mobile_refresh_tokens(id) ON DELETE RESTRICT
) STRICT;

CREATE INDEX IF NOT EXISTS idx_mobile_refresh_active
    ON mobile_refresh_tokens(token_hash, expires_at)
    WHERE consumed_at IS NULL AND revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS mobile_access_tokens (
    id TEXT PRIMARY KEY,
    device_session_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE CHECK (length(token_hash) = 64),
    user_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    revoked_at INTEGER,
    CHECK (expires_at > created_at),
    FOREIGN KEY (device_session_id)
        REFERENCES mobile_device_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE CASCADE
) STRICT;

CREATE INDEX IF NOT EXISTS idx_mobile_access_active
    ON mobile_access_tokens(token_hash, expires_at)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_mobile_access_device
    ON mobile_access_tokens(device_session_id, expires_at);

CREATE TABLE IF NOT EXISTS mobile_auth_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'device_login',
            'device_registered',
            'token_refreshed',
            'device_logout',
            'refresh_replay_detected'
        )
    ),
    device_session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json)),
    FOREIGN KEY (device_session_id)
        REFERENCES mobile_device_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE CASCADE
) STRICT;

CREATE INDEX IF NOT EXISTS idx_mobile_auth_events_subject
    ON mobile_auth_events(tenant_id, user_id, created_at);

PRAGMA user_version = 32;

COMMIT;
