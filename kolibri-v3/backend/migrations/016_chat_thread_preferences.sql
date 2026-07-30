BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS chat_thread_preferences (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    pinned_at TEXT,
    archived_at TEXT,
    hidden_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, user_id, thread_id),
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, thread_id)
        REFERENCES chat_threads (tenant_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_chat_thread_preferences_visible
    ON chat_thread_preferences (
        tenant_id,
        user_id,
        hidden_at,
        archived_at,
        pinned_at DESC
    );

CREATE TABLE IF NOT EXISTS chat_thread_user_events (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    action TEXT NOT NULL
        CHECK (action IN ('archive', 'unarchive', 'pin', 'unpin', 'remove')),
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(metadata_json)),
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, thread_id)
        REFERENCES chat_threads (tenant_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_chat_thread_user_events_subject
    ON chat_thread_user_events (tenant_id, user_id, thread_id, created_at DESC);

PRAGMA user_version = 16;

COMMIT;
