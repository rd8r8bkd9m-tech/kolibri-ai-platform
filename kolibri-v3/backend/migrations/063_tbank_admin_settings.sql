-- Admin-managed T-Bank terminal settings (test/demo only).
--
-- Secrets are stored encrypted with the same AES-256-GCM master key vault
-- as platform model keys. Production terminal activation stays env-only:
-- this table cannot hold mode='production', so an accidental admin save can
-- never enable real charges.

CREATE TABLE billing_provider_settings (
    provider TEXT PRIMARY KEY CHECK (provider = 'tbank'),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    mode TEXT NOT NULL CHECK (mode IN ('test', 'demo')),
    terminal_key_encrypted BLOB,
    password_encrypted BLOB,
    notification_url TEXT,
    return_origin TEXT,
    receipt_mode TEXT NOT NULL DEFAULT 'disabled'
        CHECK (receipt_mode IN ('disabled', 'required')),
    taxation TEXT,
    terminal_fingerprint TEXT NOT NULL DEFAULT '',
    updated_at INTEGER NOT NULL,
    updated_by_user_id TEXT NOT NULL
) STRICT;

PRAGMA user_version = 63;
