PRAGMA foreign_keys = ON;

ALTER TABLE estimate_exports RENAME TO estimate_exports_before_zip;

CREATE TABLE estimate_exports (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    estimate_version INTEGER NOT NULL
        CHECK (estimate_version >= 1),
    format TEXT NOT NULL
        CHECK (format IN ('pdf', 'xlsx', 'docx', 'csv', 'zip')),
    media_type TEXT NOT NULL,
    filename TEXT NOT NULL,
    source_content_hash TEXT NOT NULL
        CHECK (
            length(source_content_hash) = 71
            AND source_content_hash LIKE 'sha256:%'
            AND substr(source_content_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    artifact_hash TEXT NOT NULL
        CHECK (
            length(artifact_hash) = 71
            AND artifact_hash LIKE 'sha256:%'
            AND substr(artifact_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    size_bytes INTEGER NOT NULL
        CHECK (size_bytes > 0),
    content_blob BLOB NOT NULL,
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, document_id, estimate_version, format),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, document_id)
        REFERENCES document_slots (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, document_id, estimate_version)
        REFERENCES estimate_versions (tenant_id, document_id, version)
        ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

INSERT INTO estimate_exports (
    tenant_id, id, project_id, document_id, estimate_version,
    format, media_type, filename, source_content_hash,
    artifact_hash, size_bytes, content_blob,
    created_by_user_id, created_at
)
SELECT
    tenant_id, id, project_id, document_id, estimate_version,
    format, media_type, filename, source_content_hash,
    artifact_hash, size_bytes, content_blob,
    created_by_user_id, created_at
FROM estimate_exports_before_zip;

DROP TABLE estimate_exports_before_zip;

CREATE INDEX ix_estimate_exports_tenant_project
    ON estimate_exports (
        tenant_id,
        project_id,
        estimate_version DESC,
        format
    );

PRAGMA user_version = 12;
