PRAGMA foreign_keys = ON;

-- Attachment bytes live in the configured content-addressed filesystem store.
-- This table owns only immutable metadata and the authorization scope.
CREATE TABLE IF NOT EXISTS product_attachments (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    artifact_version INTEGER NOT NULL DEFAULT 1
        CHECK (artifact_version >= 1),
    content_hash TEXT NOT NULL
        CHECK (
            length(content_hash) = 71
            AND substr(content_hash, 1, 7) = 'sha256:'
            AND substr(content_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    filename TEXT NOT NULL
        CHECK (
            length(filename) BETWEEN 1 AND 240
            AND instr(filename, '/') = 0
            AND instr(filename, char(92)) = 0
            AND instr(filename, char(0)) = 0
            AND instr(filename, char(10)) = 0
            AND instr(filename, char(13)) = 0
        ),
    mime_type TEXT NOT NULL
        CHECK (length(mime_type) BETWEEN 3 AND 160),
    size_bytes INTEGER NOT NULL
        CHECK (size_bytes BETWEEN 1 AND 52428800),
    storage_ref TEXT NOT NULL
        CHECK (
            length(storage_ref) BETWEEN 32 AND 240
            AND storage_ref LIKE 'cas://sha256/%'
        ),
    upload_idempotency_key TEXT NOT NULL
        CHECK (length(upload_idempotency_key) BETWEEN 16 AND 160),
    status TEXT NOT NULL DEFAULT 'available'
        CHECK (status = 'available'),
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, artifact_id, artifact_version),
    UNIQUE (tenant_id, user_id, upload_idempotency_key),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, thread_id)
        REFERENCES chat_threads (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_product_attachments_scope
    ON product_attachments (
        tenant_id,
        user_id,
        project_id,
        thread_id,
        created_at DESC,
        id
    );

CREATE INDEX IF NOT EXISTS ix_product_attachments_storage_ref
    ON product_attachments (storage_ref);

-- A message keeps an immutable attachment_ref snapshot.  No bytes and no
-- base64 data are ever copied into chat JSON or chat_messages.content_text.
CREATE TABLE IF NOT EXISTS chat_message_attachment_refs (
    tenant_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    position INTEGER NOT NULL
        CHECK (position BETWEEN 0 AND 9),
    attachment_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    artifact_version INTEGER NOT NULL
        CHECK (artifact_version >= 1),
    content_hash TEXT NOT NULL
        CHECK (
            length(content_hash) = 71
            AND substr(content_hash, 1, 7) = 'sha256:'
            AND substr(content_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    filename TEXT NOT NULL
        CHECK (length(filename) BETWEEN 1 AND 240),
    mime_type TEXT NOT NULL
        CHECK (length(mime_type) BETWEEN 3 AND 160),
    size_bytes INTEGER NOT NULL
        CHECK (size_bytes BETWEEN 1 AND 52428800),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, message_id, position),
    UNIQUE (tenant_id, message_id, attachment_id),
    UNIQUE (tenant_id, attachment_id),
    FOREIGN KEY (tenant_id, message_id)
        REFERENCES chat_messages (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, attachment_id)
        REFERENCES product_attachments (tenant_id, id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_chat_message_attachment_refs_attachment
    ON chat_message_attachment_refs (tenant_id, attachment_id);

PRAGMA user_version = 40;
