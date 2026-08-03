PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS chat_run_workspace_contexts (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    schema_version TEXT NOT NULL
        CHECK (schema_version = '1.0'),
    context_json TEXT NOT NULL
        CHECK (json_valid(context_json)),
    context_hash TEXT NOT NULL
        CHECK (
            length(context_hash) = 71
            AND context_hash LIKE 'sha256:%'
            AND substr(context_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, run_id),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES chat_runs (tenant_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_chat_run_workspace_contexts_created
    ON chat_run_workspace_contexts (tenant_id, created_at DESC, run_id);

PRAGMA user_version = 54;
