PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS estimate_versions (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    version INTEGER NOT NULL
        CHECK (version >= 1),
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'ready', 'stale', 'revoked')),
    content_json TEXT NOT NULL
        CHECK (json_valid(content_json)),
    content_hash TEXT NOT NULL
        CHECK (
            length(content_hash) = 71
            AND content_hash LIKE 'sha256:%'
            AND substr(content_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    origin_type TEXT NOT NULL
        CHECK (origin_type IN ('ai_proposal', 'manual_edit')),
    origin_run_id TEXT,
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, document_id, version),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, document_id)
        REFERENCES document_slots (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, origin_run_id)
        REFERENCES chat_runs (tenant_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_estimate_versions_tenant_project_created
    ON estimate_versions (tenant_id, project_id, created_at DESC, version DESC);

PRAGMA user_version = 7;
