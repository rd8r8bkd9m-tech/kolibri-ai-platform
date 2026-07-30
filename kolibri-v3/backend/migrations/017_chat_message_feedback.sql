BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS chat_message_feedback (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    feedback_type TEXT NOT NULL
        CHECK (feedback_type IN ('positive', 'negative')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, user_id, message_id),
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, thread_id)
        REFERENCES chat_threads (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, message_id)
        REFERENCES chat_messages (tenant_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_chat_message_feedback_thread
    ON chat_message_feedback (
        tenant_id,
        thread_id,
        message_id,
        feedback_type
    );

CREATE TABLE IF NOT EXISTS chat_message_feedback_events (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    feedback_type TEXT NOT NULL
        CHECK (feedback_type IN ('positive', 'negative')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, thread_id)
        REFERENCES chat_threads (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, message_id)
        REFERENCES chat_messages (tenant_id, id)
        ON DELETE CASCADE
);

PRAGMA user_version = 17;

COMMIT;
