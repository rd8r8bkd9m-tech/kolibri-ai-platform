PRAGMA foreign_keys = OFF;

CREATE TABLE estimate_versions_v18 (
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
        CHECK (
            origin_type IN (
                'ai_proposal',
                'manual_edit',
                'engine_calculation'
            )
        ),
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

INSERT INTO estimate_versions_v18 (
    tenant_id, id, project_id, document_id, version, status,
    content_json, content_hash, origin_type, origin_run_id,
    created_by_user_id, created_at
)
SELECT
    tenant_id, id, project_id, document_id, version, status,
    content_json, content_hash, origin_type, origin_run_id,
    created_by_user_id, created_at
FROM estimate_versions;

DROP TABLE estimate_versions;
ALTER TABLE estimate_versions_v18 RENAME TO estimate_versions;

CREATE INDEX ix_estimate_versions_tenant_project_created
    ON estimate_versions (tenant_id, project_id, created_at DESC, version DESC);

CREATE TABLE project_cases (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    version INTEGER NOT NULL
        CHECK (version >= 1),
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'ready', 'stale', 'superseded')),
    region TEXT NOT NULL
        CHECK (length(region) BETWEEN 1 AND 160),
    snapshot_json TEXT NOT NULL
        CHECK (json_valid(snapshot_json)),
    content_hash TEXT NOT NULL
        CHECK (
            length(content_hash) = 71
            AND content_hash LIKE 'sha256:%'
            AND substr(content_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    source_message_id TEXT,
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id, version),
    UNIQUE (tenant_id, project_id, version),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, source_message_id)
        REFERENCES chat_messages (tenant_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE INDEX ix_project_cases_tenant_project_version
    ON project_cases (tenant_id, project_id, version DESC);

CREATE TABLE technology_cards (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    project_case_id TEXT NOT NULL,
    project_case_version INTEGER NOT NULL,
    rules_version TEXT NOT NULL,
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
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (
        tenant_id,
        project_case_id,
        project_case_version,
        rules_version
    ),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, project_case_id, project_case_version)
        REFERENCES project_cases (tenant_id, id, version)
        ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE INDEX ix_technology_cards_tenant_project_created
    ON technology_cards (tenant_id, project_id, created_at DESC, id);

CREATE TABLE estimate_calculations (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    project_case_id TEXT NOT NULL,
    project_case_version INTEGER NOT NULL,
    technology_card_id TEXT NOT NULL,
    document_id TEXT,
    estimate_version INTEGER,
    engine_version TEXT NOT NULL,
    rules_version TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('complete', 'blocked')),
    input_hash TEXT NOT NULL
        CHECK (
            length(input_hash) = 71
            AND input_hash LIKE 'sha256:%'
            AND substr(input_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    result_hash TEXT NOT NULL
        CHECK (
            length(result_hash) = 71
            AND result_hash LIKE 'sha256:%'
            AND substr(result_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    result_json TEXT NOT NULL
        CHECK (json_valid(result_json)),
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, input_hash),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, project_case_id, project_case_version)
        REFERENCES project_cases (tenant_id, id, version)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, technology_card_id)
        REFERENCES technology_cards (tenant_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, document_id, estimate_version)
        REFERENCES estimate_versions (tenant_id, document_id, version)
        ON DELETE RESTRICT,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT,
    CHECK (
        (document_id IS NULL AND estimate_version IS NULL)
        OR (document_id IS NOT NULL AND estimate_version IS NOT NULL)
    )
);

CREATE INDEX ix_estimate_calculations_tenant_project_created
    ON estimate_calculations (tenant_id, project_id, created_at DESC, id);

CREATE TABLE api_command_idempotency (
    tenant_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    key_hash TEXT NOT NULL
        CHECK (
            length(key_hash) = 64
            AND key_hash NOT GLOB '*[^0-9a-f]*'
        ),
    request_hash TEXT NOT NULL
        CHECK (
            length(request_hash) = 71
            AND request_hash LIKE 'sha256:%'
            AND substr(request_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    result_type TEXT NOT NULL,
    result_id TEXT NOT NULL,
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, operation, key_hash),
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE TABLE audit_events (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    actor_user_id TEXT,
    action TEXT NOT NULL
        CHECK (length(action) BETWEEN 3 AND 160),
    subject_type TEXT NOT NULL
        CHECK (length(subject_type) BETWEEN 1 AND 80),
    subject_id TEXT NOT NULL
        CHECK (length(subject_id) BETWEEN 1 AND 160),
    project_id TEXT,
    metadata_json TEXT NOT NULL
        CHECK (json_valid(metadata_json)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (actor_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE INDEX ix_audit_events_tenant_subject_created
    ON audit_events (
        tenant_id,
        subject_type,
        subject_id,
        created_at DESC,
        id
    );

PRAGMA foreign_keys = ON;
PRAGMA user_version = 18;
