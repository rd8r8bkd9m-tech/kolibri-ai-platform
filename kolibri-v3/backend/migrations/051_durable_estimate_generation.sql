PRAGMA foreign_keys = ON;

-- Durable, run-local journal for universal estimate generation.  ProjectCase
-- snapshots remain canonical in project_cases.  Run-local technology
-- revisions are immutable proposals until they are explicitly published into
-- the existing technology_cards authority.
CREATE TABLE IF NOT EXISTS estimate_generation_runs (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    source_run_id TEXT,
    project_case_id TEXT NOT NULL,
    project_case_version INTEGER NOT NULL CHECK (project_case_version >= 1),
    status TEXT NOT NULL
        CHECK (status IN (
            'queued', 'running', 'needs_input', 'review', 'ready',
            'failed', 'cancelled'
        )),
    stage TEXT NOT NULL
        CHECK (stage IN (
            'project_case', 'decomposition', 'technology', 'research',
            'pricing', 'expansion', 'reconciliation', 'persisting',
            'complete'
        )),
    quality_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (quality_status IN ('pending', 'failed', 'passed')),
    progress_completed INTEGER NOT NULL DEFAULT 0
        CHECK (progress_completed >= 0),
    progress_total INTEGER NOT NULL DEFAULT 0
        CHECK (progress_total >= 0 AND progress_completed <= progress_total),
    cancel_requested INTEGER NOT NULL DEFAULT 0
        CHECK (cancel_requested IN (0, 1)),
    idempotency_key_hash TEXT NOT NULL
        CHECK (
            length(idempotency_key_hash) = 64
            AND idempotency_key_hash NOT GLOB '*[^0-9a-f]*'
        ),
    request_hash TEXT NOT NULL
        CHECK (
            length(request_hash) = 71
            AND request_hash LIKE 'sha256:%'
            AND substr(request_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    quality_report_json TEXT
        CHECK (quality_report_json IS NULL OR json_valid(quality_report_json)),
    result_document_id TEXT,
    result_estimate_version INTEGER CHECK (result_estimate_version IS NULL OR result_estimate_version >= 1),
    last_error_json TEXT CHECK (last_error_json IS NULL OR json_valid(last_error_json)),
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, idempotency_key_hash),
    UNIQUE (tenant_id, id, project_id),
    CHECK (
        (result_document_id IS NULL AND result_estimate_version IS NULL)
        OR (result_document_id IS NOT NULL AND result_estimate_version IS NOT NULL)
    ),
    CHECK (
        (status IN ('ready', 'failed', 'cancelled') AND finished_at IS NOT NULL)
        OR (status NOT IN ('ready', 'failed', 'cancelled') AND finished_at IS NULL)
    ),
    CHECK (
        status <> 'ready'
        OR (
            stage = 'complete'
            AND quality_status = 'passed'
            AND result_document_id IS NOT NULL
            AND result_estimate_version IS NOT NULL
        )
    ),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, source_run_id)
        REFERENCES chat_runs (tenant_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, project_case_id, project_case_version)
        REFERENCES project_cases (tenant_id, id, version)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, result_document_id, result_estimate_version)
        REFERENCES estimate_versions (tenant_id, document_id, version)
        ON DELETE RESTRICT,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
) STRICT;

CREATE INDEX IF NOT EXISTS ix_estimate_generation_runs_resume
    ON estimate_generation_runs (status, updated_at, tenant_id, id);
CREATE INDEX IF NOT EXISTS ix_estimate_generation_runs_project
    ON estimate_generation_runs (tenant_id, project_id, created_at DESC, id);

CREATE TABLE IF NOT EXISTS estimate_generation_sections (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    section_key TEXT NOT NULL CHECK (length(section_key) BETWEEN 1 AND 160),
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 240),
    wbs_path TEXT NOT NULL CHECK (length(wbs_path) BETWEEN 1 AND 500),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending', 'active', 'needs_input', 'review', 'passed',
            'failed', 'cancelled'
        )),
    expected_task_count INTEGER NOT NULL DEFAULT 0
        CHECK (expected_task_count >= 0),
    completed_task_count INTEGER NOT NULL DEFAULT 0
        CHECK (completed_task_count >= 0 AND completed_task_count <= expected_task_count),
    last_error_json TEXT CHECK (last_error_json IS NULL OR json_valid(last_error_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, run_id, section_key),
    UNIQUE (tenant_id, run_id, id, section_key),
    CHECK (status <> 'passed' OR completed_task_count = expected_task_count),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES estimate_generation_runs (tenant_id, id)
        ON DELETE CASCADE
) STRICT;

CREATE INDEX IF NOT EXISTS ix_estimate_generation_sections_progress
    ON estimate_generation_sections (tenant_id, run_id, status, ordinal, section_key);

CREATE TABLE IF NOT EXISTS estimate_generation_tasks (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    section_id TEXT NOT NULL,
    section_key TEXT NOT NULL,
    section_revision INTEGER NOT NULL CHECK (section_revision >= 1),
    task_key TEXT NOT NULL CHECK (length(task_key) BETWEEN 1 AND 240),
    role TEXT NOT NULL
        CHECK (role IN (
            'technologist', 'quantity_engineer', 'resource_normer',
            'technical_researcher', 'procurement', 'logistics',
            'reviewer', 'orchestrator'
        )),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN (
            'queued', 'leased', 'succeeded', 'failed', 'cancelled',
            'superseded'
        )),
    attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    fencing_token INTEGER NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
    depends_on_roles_json TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(depends_on_roles_json)),
    input_json TEXT NOT NULL CHECK (json_valid(input_json)),
    input_hash TEXT NOT NULL
        CHECK (
            length(input_hash) = 71
            AND input_hash LIKE 'sha256:%'
            AND substr(input_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
    result_hash TEXT
        CHECK (
            result_hash IS NULL
            OR (
                length(result_hash) = 71
                AND result_hash LIKE 'sha256:%'
                AND substr(result_hash, 8) NOT GLOB '*[^0-9a-f]*'
            )
        ),
    error_json TEXT CHECK (error_json IS NULL OR json_valid(error_json)),
    retryable INTEGER NOT NULL DEFAULT 1 CHECK (retryable IN (0, 1)),
    retry_of_task_id TEXT,
    lease_owner TEXT,
    lease_token TEXT,
    lease_until TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, run_id, task_key),
    UNIQUE (tenant_id, run_id, id),
    CHECK (
        (
            status = 'leased'
            AND lease_owner IS NOT NULL
            AND lease_token IS NOT NULL
            AND lease_until IS NOT NULL
        )
        OR (
            status <> 'leased'
            AND lease_owner IS NULL
            AND lease_token IS NULL
            AND lease_until IS NULL
        )
    ),
    CHECK (
        (status IN ('succeeded', 'failed', 'cancelled', 'superseded') AND completed_at IS NOT NULL)
        OR (status IN ('queued', 'leased') AND completed_at IS NULL)
    ),
    CHECK ((result_json IS NULL) = (result_hash IS NULL)),
    CHECK (status <> 'succeeded' OR result_json IS NOT NULL),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES estimate_generation_runs (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, run_id, section_id, section_key)
        REFERENCES estimate_generation_sections (tenant_id, run_id, id, section_key)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, run_id, retry_of_task_id)
        REFERENCES estimate_generation_tasks (tenant_id, run_id, id)
        ON DELETE RESTRICT
) STRICT;

CREATE INDEX IF NOT EXISTS ix_estimate_generation_tasks_claim
    ON estimate_generation_tasks (
        tenant_id, run_id, status, role, section_revision,
        created_at, id
    );
CREATE INDEX IF NOT EXISTS ix_estimate_generation_tasks_lease
    ON estimate_generation_tasks (status, lease_until, tenant_id, run_id, id);

CREATE TABLE IF NOT EXISTS estimate_generation_checkpoints (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    section_key TEXT,
    task_id TEXT,
    checkpoint_key TEXT NOT NULL CHECK (length(checkpoint_key) BETWEEN 1 AND 240),
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    stage TEXT NOT NULL
        CHECK (stage IN (
            'project_case', 'decomposition', 'technology', 'research',
            'pricing', 'expansion', 'reconciliation', 'persisting',
            'complete'
        )),
    status TEXT NOT NULL
        CHECK (status IN ('started', 'completed', 'failed', 'needs_input')),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    payload_hash TEXT NOT NULL
        CHECK (
            length(payload_hash) = 71
            AND payload_hash LIKE 'sha256:%'
            AND substr(payload_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, run_id, checkpoint_key),
    UNIQUE (tenant_id, run_id, sequence),
    UNIQUE (tenant_id, run_id, id),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES estimate_generation_runs (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, run_id, section_key)
        REFERENCES estimate_generation_sections (tenant_id, run_id, section_key)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, run_id, task_id)
        REFERENCES estimate_generation_tasks (tenant_id, run_id, id)
        ON DELETE CASCADE
) STRICT;

CREATE INDEX IF NOT EXISTS ix_estimate_generation_checkpoints_run
    ON estimate_generation_checkpoints (tenant_id, run_id, sequence);

CREATE TABLE IF NOT EXISTS estimate_generation_technology_revisions (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    project_case_id TEXT NOT NULL,
    project_case_version INTEGER NOT NULL CHECK (project_case_version >= 1),
    previous_revision_id TEXT,
    published_technology_card_id TEXT,
    status TEXT NOT NULL
        CHECK (status IN (
            'draft', 'review', 'accepted', 'rejected', 'superseded'
        )),
    rules_version TEXT NOT NULL CHECK (length(rules_version) BETWEEN 1 AND 120),
    snapshot_json TEXT NOT NULL CHECK (json_valid(snapshot_json)),
    snapshot_hash TEXT NOT NULL
        CHECK (
            length(snapshot_hash) = 71
            AND snapshot_hash LIKE 'sha256:%'
            AND substr(snapshot_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    validation_json TEXT NOT NULL CHECK (json_valid(validation_json)),
    validation_hash TEXT NOT NULL
        CHECK (
            length(validation_hash) = 71
            AND validation_hash LIKE 'sha256:%'
            AND substr(validation_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, run_id, revision),
    UNIQUE (tenant_id, run_id, snapshot_hash),
    UNIQUE (tenant_id, run_id, id),
    FOREIGN KEY (tenant_id, run_id, project_id)
        REFERENCES estimate_generation_runs (tenant_id, id, project_id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, project_case_id, project_case_version)
        REFERENCES project_cases (tenant_id, id, version)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, run_id, previous_revision_id)
        REFERENCES estimate_generation_technology_revisions (tenant_id, run_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, project_id, published_technology_card_id)
        REFERENCES technology_cards (tenant_id, project_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
) STRICT;

CREATE INDEX IF NOT EXISTS ix_estimate_generation_technology_run
    ON estimate_generation_technology_revisions (tenant_id, run_id, revision DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_technology_cards_tenant_project_id
    ON technology_cards (tenant_id, project_id, id);

CREATE TABLE IF NOT EXISTS estimate_generation_evidence (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    section_key TEXT,
    evidence_key TEXT NOT NULL CHECK (length(evidence_key) BETWEEN 1 AND 240),
    kind TEXT NOT NULL CHECK (kind IN ('technical', 'price')),
    source_type TEXT NOT NULL
        CHECK (source_type IN (
            'user_input', 'approved_catalog', 'official_reference',
            'supplier_offer', 'market_aggregate', 'ai_candidate'
        )),
    confidence_status TEXT NOT NULL
        CHECK (confidence_status IN ('preliminary', 'source_backed', 'verified')),
    confidence TEXT NOT NULL
        CHECK (confidence GLOB '[0-1]' OR confidence GLOB '[0-1].[0-9]*'),
    source_title TEXT NOT NULL CHECK (length(source_title) BETWEEN 1 AND 300),
    source_uri TEXT,
    source_reference TEXT NOT NULL CHECK (length(source_reference) BETWEEN 1 AND 500),
    region TEXT,
    unit TEXT,
    unit_price TEXT,
    currency TEXT CHECK (currency IS NULL OR currency = 'RUB'),
    tax_treatment TEXT
        CHECK (tax_treatment IS NULL OR tax_treatment IN (
            'included', 'excluded', 'unknown', 'not_applicable'
        )),
    delivery_treatment TEXT
        CHECK (delivery_treatment IS NULL OR delivery_treatment IN (
            'included', 'excluded', 'unknown'
        )),
    observed_at TEXT,
    valid_until TEXT,
    snapshot_json TEXT NOT NULL CHECK (json_valid(snapshot_json)),
    snapshot_hash TEXT NOT NULL
        CHECK (
            length(snapshot_hash) = 71
            AND snapshot_hash LIKE 'sha256:%'
            AND substr(snapshot_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    verification_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(verification_json)),
    verified_by_user_id TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, run_id, evidence_key, snapshot_hash),
    UNIQUE (tenant_id, run_id, id),
    CHECK (source_type <> 'ai_candidate' OR confidence_status = 'preliminary'),
    CHECK (
        kind <> 'price'
        OR (
            region IS NOT NULL
            AND unit IS NOT NULL
            AND unit_price IS NOT NULL
            AND currency = 'RUB'
            AND observed_at IS NOT NULL
        )
    ),
    CHECK (
        confidence_status <> 'verified'
        OR (
            source_type IN ('user_input', 'official_reference', 'supplier_offer')
            AND verified_by_user_id IS NOT NULL
            AND verification_json <> '{}'
        )
    ),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES estimate_generation_runs (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, run_id, section_key)
        REFERENCES estimate_generation_sections (tenant_id, run_id, section_key)
        ON DELETE CASCADE,
    FOREIGN KEY (verified_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
) STRICT;

CREATE INDEX IF NOT EXISTS ix_estimate_generation_evidence_lookup
    ON estimate_generation_evidence (
        tenant_id, run_id, evidence_key, kind, confidence_status, created_at DESC
    );

CREATE TABLE IF NOT EXISTS estimate_generation_lineage (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    technology_revision_id TEXT NOT NULL,
    producing_task_id TEXT,
    producing_checkpoint_id TEXT,
    row_id TEXT NOT NULL CHECK (length(row_id) BETWEEN 1 AND 120),
    section_key TEXT NOT NULL,
    operation_id TEXT NOT NULL CHECK (length(operation_id) BETWEEN 1 AND 160),
    resource_id TEXT NOT NULL CHECK (length(resource_id) BETWEEN 1 AND 160),
    evidence_id TEXT,
    line_confidence TEXT NOT NULL
        CHECK (line_confidence IN (
            'missing', 'preliminary', 'source_backed', 'verified'
        )),
    line_snapshot_json TEXT NOT NULL CHECK (json_valid(line_snapshot_json)),
    line_snapshot_hash TEXT NOT NULL
        CHECK (
            length(line_snapshot_hash) = 71
            AND line_snapshot_hash LIKE 'sha256:%'
            AND substr(line_snapshot_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, run_id, technology_revision_id, row_id),
    CHECK (
        line_confidence NOT IN ('source_backed', 'verified')
        OR evidence_id IS NOT NULL
    ),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES estimate_generation_runs (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, run_id, technology_revision_id)
        REFERENCES estimate_generation_technology_revisions (tenant_id, run_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, run_id, producing_task_id)
        REFERENCES estimate_generation_tasks (tenant_id, run_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, run_id, producing_checkpoint_id)
        REFERENCES estimate_generation_checkpoints (tenant_id, run_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, run_id, evidence_id)
        REFERENCES estimate_generation_evidence (tenant_id, run_id, id)
        ON DELETE RESTRICT
) STRICT;

CREATE INDEX IF NOT EXISTS ix_estimate_generation_lineage_operation
    ON estimate_generation_lineage (
        tenant_id, run_id, technology_revision_id, operation_id, resource_id
    );

-- Generic command ledger makes retries safe even when a worker receives the
-- same transition after losing its acknowledgement.
CREATE TABLE IF NOT EXISTS estimate_generation_commands (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (length(operation) BETWEEN 1 AND 160),
    idempotency_key_hash TEXT NOT NULL
        CHECK (
            length(idempotency_key_hash) = 64
            AND idempotency_key_hash NOT GLOB '*[^0-9a-f]*'
        ),
    request_hash TEXT NOT NULL
        CHECK (
            length(request_hash) = 71
            AND request_hash LIKE 'sha256:%'
            AND substr(request_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    result_json TEXT NOT NULL CHECK (json_valid(result_json)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, run_id, operation, idempotency_key_hash),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES estimate_generation_runs (tenant_id, id)
        ON DELETE CASCADE
) STRICT;

PRAGMA user_version = 51;
