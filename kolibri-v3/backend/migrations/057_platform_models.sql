-- Platform-wide AI models managed by the superadmin.
-- These models are available to all users with a shared API key.

CREATE TABLE IF NOT EXISTS platform_models (
    id TEXT PRIMARY KEY,
    provider_type TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    api_key_encrypted BLOB NOT NULL,
    base_url TEXT,
    model_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    auto_priority INTEGER NOT NULL DEFAULT 50 CHECK (auto_priority BETWEEN 0 AND 100),
    is_enabled INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    supported_reasoning_efforts_json TEXT,
    service_tiers_json TEXT,
    last_tested_at TEXT,
    last_test_status TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_platform_models_enabled
    ON platform_models(is_enabled);

CREATE INDEX IF NOT EXISTS idx_platform_models_priority
    ON platform_models(is_enabled, auto_priority DESC);

PRAGMA user_version = 57;
