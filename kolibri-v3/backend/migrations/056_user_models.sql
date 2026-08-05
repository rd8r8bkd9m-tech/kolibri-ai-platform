-- User-managed AI models with encrypted API keys.
-- Allows non-admin users to add their own models from OpenAI, Anthropic, Qwen, or custom providers.

CREATE TABLE IF NOT EXISTS user_models (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    provider_type TEXT NOT NULL CHECK (provider_type IN ('openai', 'anthropic', 'qwen', 'custom')),
    provider_name TEXT NOT NULL,
    api_key_encrypted BLOB NOT NULL,
    base_url TEXT,
    model_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    auto_priority INTEGER NOT NULL DEFAULT 50 CHECK (auto_priority BETWEEN 0 AND 100),
    is_enabled INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
    last_tested_at TEXT,
    last_test_status TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_user_models_tenant_user
    ON user_models(tenant_id, user_id);

CREATE INDEX IF NOT EXISTS idx_user_models_enabled
    ON user_models(tenant_id, user_id, is_enabled);

PRAGMA user_version = 56;
