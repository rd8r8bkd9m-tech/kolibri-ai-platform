CREATE TABLE IF NOT EXISTS kolibri.public_sessions (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL DEFAULT 'kolibri.public-session.v1',
    credential_sha256 TEXT NOT NULL UNIQUE,
    origin TEXT NOT NULL,
    current_project_id TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT public_sessions_schema_v1
        CHECK (schema_version = 'kolibri.public-session.v1'),
    CONSTRAINT public_sessions_credential_sha256_format
        CHECK (credential_sha256 ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT public_sessions_origin_not_blank
        CHECK (length(btrim(origin)) BETWEEN 8 AND 2048),
    CONSTRAINT public_sessions_project_not_blank
        CHECK (length(btrim(current_project_id)) BETWEEN 3 AND 200),
    CONSTRAINT public_sessions_expiry_after_creation
        CHECK (expires_at > created_at),
    CONSTRAINT public_sessions_revocation_after_creation
        CHECK (revoked_at IS NULL OR revoked_at >= created_at)
);

CREATE INDEX IF NOT EXISTS public_sessions_active_expiry_idx
    ON kolibri.public_sessions (expires_at, id)
    WHERE revoked_at IS NULL;
