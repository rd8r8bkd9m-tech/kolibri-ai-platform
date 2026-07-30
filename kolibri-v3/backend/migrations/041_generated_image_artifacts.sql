PRAGMA foreign_keys = ON;

-- Immutable canonical metadata for generated image versions.  The bytes are
-- owned by the shared CAS referenced by product_attachments; chat JSON keeps
-- only the bounded tool projection.
CREATE TABLE IF NOT EXISTS artifact_versions (
    tenant_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    artifact_version INTEGER NOT NULL
        CHECK (artifact_version >= 1),
    attachment_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    input_message_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL
        CHECK (artifact_type = 'image.generated'),
    content_hash TEXT NOT NULL
        CHECK (
            length(content_hash) = 71
            AND content_hash LIKE 'sha256:%'
            AND substr(content_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    storage_ref TEXT NOT NULL
        CHECK (
            length(storage_ref) BETWEEN 32 AND 240
            AND storage_ref LIKE 'cas://sha256/%'
        ),
    media_type TEXT NOT NULL
        CHECK (media_type IN ('image/png', 'image/jpeg', 'image/webp')),
    size_bytes INTEGER NOT NULL
        CHECK (size_bytes BETWEEN 1 AND 52428800),
    filename TEXT NOT NULL
        CHECK (
            length(filename) BETWEEN 1 AND 240
            AND instr(filename, '/') = 0
            AND instr(filename, char(92)) = 0
            AND instr(filename, char(0)) = 0
            AND instr(filename, char(10)) = 0
            AND instr(filename, char(13)) = 0
        ),
    generator_id TEXT NOT NULL
        CHECK (length(generator_id) BETWEEN 3 AND 128),
    generator_version TEXT NOT NULL
        CHECK (length(generator_version) BETWEEN 1 AND 64),
    execution_ref TEXT NOT NULL
        CHECK (length(execution_ref) BETWEEN 8 AND 160),
    prompt_hash TEXT NOT NULL
        CHECK (
            length(prompt_hash) = 71
            AND prompt_hash LIKE 'sha256:%'
            AND substr(prompt_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    manifest_json TEXT NOT NULL
        CHECK (json_valid(manifest_json)),
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, artifact_id, artifact_version),
    UNIQUE (tenant_id, attachment_id),
    UNIQUE (tenant_id, run_id),
    UNIQUE (tenant_id, execution_ref),
    FOREIGN KEY (tenant_id, attachment_id)
        REFERENCES product_attachments (tenant_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, thread_id)
        REFERENCES chat_threads (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES chat_runs (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, input_message_id)
        REFERENCES chat_messages (tenant_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_artifact_versions_project_created
    ON artifact_versions (
        tenant_id,
        project_id,
        created_at DESC,
        artifact_id,
        artifact_version
    );

CREATE INDEX IF NOT EXISTS ix_artifact_versions_content_hash
    ON artifact_versions (tenant_id, content_hash);

PRAGMA user_version = 41;
