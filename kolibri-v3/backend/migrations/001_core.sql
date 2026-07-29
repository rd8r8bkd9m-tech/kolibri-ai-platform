BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 160),
    created_at INTEGER NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    email_normalized TEXT NOT NULL COLLATE NOCASE,
    email TEXT NOT NULL,
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    role TEXT NOT NULL CHECK (role IN ('owner', 'user')),
    preferred_agent_profile TEXT NOT NULL DEFAULT 'auto'
        CHECK (preferred_agent_profile IN ('auto', 'mimo-code', 'codex-cli')),
    password_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE (email_normalized),
    UNIQUE (id, tenant_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT
) STRICT;

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE
        CHECK (length(token_hash) = 64),
    user_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    revoked_at INTEGER,
    CHECK (expires_at > created_at),
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE CASCADE
) STRICT;

CREATE INDEX IF NOT EXISTS idx_sessions_active_token
    ON sessions(token_hash, expires_at)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_sessions_user
    ON sessions(tenant_id, user_id, expires_at);

CREATE TABLE IF NOT EXISTS identity_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'owner_bootstrapped',
            'user_registered',
            'login_succeeded',
            'logout_succeeded',
            'profile_updated'
        )
    ),
    actor_user_id TEXT,
    tenant_id TEXT,
    subject_user_id TEXT,
    created_at INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(metadata_json))
) STRICT;

PRAGMA user_version = 1;

COMMIT;
