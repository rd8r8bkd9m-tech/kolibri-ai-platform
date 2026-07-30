PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS estimate_copy_lineage (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL
        CHECK (length(idempotency_key) BETWEEN 16 AND 128),
    request_hash TEXT NOT NULL
        CHECK (
            length(request_hash) = 71
            AND request_hash LIKE 'sha256:%'
            AND substr(request_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    source_project_id TEXT NOT NULL,
    source_document_id TEXT NOT NULL,
    source_version INTEGER NOT NULL
        CHECK (source_version >= 1),
    source_content_hash TEXT NOT NULL
        CHECK (
            length(source_content_hash) = 71
            AND source_content_hash LIKE 'sha256:%'
            AND substr(source_content_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    target_project_id TEXT NOT NULL,
    target_document_id TEXT NOT NULL,
    target_version INTEGER NOT NULL DEFAULT 1
        CHECK (target_version >= 1),
    target_content_hash TEXT NOT NULL
        CHECK (
            length(target_content_hash) = 71
            AND target_content_hash LIKE 'sha256:%'
            AND substr(target_content_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, idempotency_key),
    UNIQUE (tenant_id, target_document_id, target_version),
    FOREIGN KEY (tenant_id, source_project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, source_document_id, source_version)
        REFERENCES estimate_versions (tenant_id, document_id, version)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, target_project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, target_document_id, target_version)
        REFERENCES estimate_versions (tenant_id, document_id, version)
        ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_estimate_copy_lineage_source
    ON estimate_copy_lineage (
        tenant_id,
        source_document_id,
        source_version,
        created_at DESC
    );

PRAGMA user_version = 10;
