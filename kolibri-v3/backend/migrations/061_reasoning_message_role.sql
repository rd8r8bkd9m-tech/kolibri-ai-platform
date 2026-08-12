PRAGMA foreign_keys = OFF;

CREATE TABLE chat_messages_new (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    sequence INTEGER NOT NULL
        CHECK (sequence >= 1),
    client_message_id TEXT,
    run_id TEXT,
    role TEXT NOT NULL
        CHECK (role IN ('user', 'assistant', 'reasoning')),
    content_text TEXT NOT NULL
        CHECK (length(content_text) BETWEEN 1 AND 200000),
    created_by_user_id TEXT,
    created_at TEXT NOT NULL,
    content_json TEXT
        CHECK (content_json IS NULL OR json_valid(content_json)),
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, thread_id, sequence),
    UNIQUE (tenant_id, thread_id, client_message_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, thread_id)
        REFERENCES chat_threads (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

INSERT INTO chat_messages_new (
    tenant_id,
    id,
    project_id,
    thread_id,
    sequence,
    client_message_id,
    run_id,
    role,
    content_text,
    created_by_user_id,
    created_at,
    content_json
)
SELECT
    tenant_id,
    id,
    project_id,
    thread_id,
    sequence,
    client_message_id,
    run_id,
    role,
    content_text,
    created_by_user_id,
    created_at,
    content_json
FROM chat_messages;

DROP TABLE chat_messages;

ALTER TABLE chat_messages_new RENAME TO chat_messages;

CREATE INDEX ix_chat_messages_tenant_thread_sequence
    ON chat_messages (tenant_id, thread_id, sequence);

PRAGMA foreign_key_check;

PRAGMA foreign_keys = ON;

PRAGMA user_version = 61;
