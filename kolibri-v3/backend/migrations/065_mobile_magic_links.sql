CREATE TABLE IF NOT EXISTS mobile_magic_links (
    id TEXT PRIMARY KEY NOT NULL,
    email_normalized TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    consumed_at INTEGER,
    consumed_device_session_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_mobile_magic_links_email
    ON mobile_magic_links (email_normalized, consumed_at);

CREATE INDEX IF NOT EXISTS idx_mobile_magic_links_expiry
    ON mobile_magic_links (expires_at, consumed_at);

PRAGMA user_version = 65;
