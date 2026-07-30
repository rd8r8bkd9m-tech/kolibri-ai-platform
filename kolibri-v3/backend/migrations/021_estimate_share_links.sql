BEGIN IMMEDIATE;

CREATE TABLE estimate_share_links (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE
        CHECK (
            length(token_hash) = 71
            AND token_hash LIKE 'sha256:%'
            AND substr(token_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    project_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    estimate_version INTEGER NOT NULL CHECK (estimate_version >= 1),
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, document_id, estimate_version)
        REFERENCES estimate_versions (tenant_id, document_id, version)
        ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE INDEX ix_estimate_share_links_project_version
    ON estimate_share_links (
        tenant_id,
        project_id,
        document_id,
        estimate_version,
        created_at DESC
    );

CREATE INDEX ix_estimate_share_links_expiry
    ON estimate_share_links (expires_at, revoked_at);

PRAGMA user_version = 21;

COMMIT;
