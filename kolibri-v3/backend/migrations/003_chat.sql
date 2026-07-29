PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    created_by_user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    primary_thread_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, primary_thread_id),
    FOREIGN KEY (tenant_id)
        REFERENCES tenants (id)
        ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_projects_tenant_updated
    ON projects (tenant_id, updated_at DESC, id);

CREATE TABLE IF NOT EXISTS construction_objects (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    name_source TEXT NOT NULL DEFAULT 'placeholder'
        CHECK (name_source IN ('placeholder', 'user', 'verified')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, project_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_threads (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'primary'
        CHECK (kind IN ('primary', 'branch')),
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'regular'
        CHECK (status IN ('regular', 'archived')),
    message_count INTEGER NOT NULL DEFAULT 0
        CHECK (message_count >= 0),
    run_count INTEGER NOT NULL DEFAULT 0
        CHECK (run_count >= 0),
    last_message_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_chat_threads_tenant_updated
    ON chat_threads (tenant_id, updated_at DESC, id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_threads_tenant_primary
    ON chat_threads (tenant_id, project_id)
    WHERE kind = 'primary';

CREATE TABLE IF NOT EXISTS document_slots (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    slot_type TEXT NOT NULL
        CHECK (
            slot_type IN (
                'source-data',
                'estimate',
                'commercial-proposal',
                'contract'
            )
        ),
    version INTEGER NOT NULL DEFAULT 1
        CHECK (version >= 1),
    status TEXT NOT NULL DEFAULT 'empty'
        CHECK (status IN ('empty', 'draft', 'ready', 'stale', 'revoked')),
    content_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, project_id, slot_type),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_document_slots_tenant_project
    ON document_slots (tenant_id, project_id, slot_type);

CREATE TABLE IF NOT EXISTS chat_messages (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    sequence INTEGER NOT NULL
        CHECK (sequence >= 1),
    client_message_id TEXT,
    run_id TEXT,
    role TEXT NOT NULL
        CHECK (role IN ('user', 'assistant')),
    content_text TEXT NOT NULL
        CHECK (length(content_text) BETWEEN 1 AND 200000),
    created_by_user_id TEXT,
    created_at TEXT NOT NULL,
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

CREATE INDEX IF NOT EXISTS ix_chat_messages_tenant_thread_sequence
    ON chat_messages (tenant_id, thread_id, sequence);

CREATE TABLE IF NOT EXISTS chat_runs (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    client_run_id TEXT NOT NULL,
    request_hash TEXT NOT NULL
        CHECK (request_hash GLOB 'sha256:[0-9a-f]*'),
    input_message_id TEXT NOT NULL,
    assistant_message_id TEXT,
    requested_by_user_id TEXT NOT NULL,
    selected_profile TEXT NOT NULL
        CHECK (selected_profile IN ('auto', 'mimo-code', 'codex-cli')),
    status TEXT NOT NULL
        CHECK (status IN ('running', 'succeeded', 'failed')),
    outcome TEXT
        CHECK (outcome IS NULL OR outcome IN ('success', 'failure')),
    last_event_sequence INTEGER NOT NULL DEFAULT 0
        CHECK (last_event_sequence >= 0),
    error_code TEXT,
    heartbeat_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, thread_id, client_run_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, thread_id)
        REFERENCES chat_threads (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, input_message_id)
        REFERENCES chat_messages (tenant_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, assistant_message_id)
        REFERENCES chat_messages (tenant_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (requested_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_chat_runs_tenant_thread_created
    ON chat_runs (tenant_id, thread_id, created_at DESC, id);

CREATE INDEX IF NOT EXISTS ix_chat_runs_tenant_status_heartbeat
    ON chat_runs (tenant_id, status, heartbeat_at);

CREATE TABLE IF NOT EXISTS chat_run_events (
    tenant_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL
        CHECK (sequence >= 1),
    event_type TEXT NOT NULL
        CHECK (
            event_type IN (
                'RUN_STARTED',
                'TEXT_MESSAGE_START',
                'TEXT_MESSAGE_CONTENT',
                'TEXT_MESSAGE_END',
                'RUN_FINISHED',
                'RUN_ERROR'
            )
        ),
    event_json TEXT NOT NULL
        CHECK (json_valid(event_json)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, event_id),
    UNIQUE (tenant_id, run_id, sequence),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES chat_runs (tenant_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_chat_run_events_tenant_run_sequence
    ON chat_run_events (tenant_id, run_id, sequence);

PRAGMA user_version = 3;
