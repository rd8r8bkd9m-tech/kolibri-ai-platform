PRAGMA foreign_keys = ON;

-- Immutable releases of an estimate document.  The snapshot is the only
-- input to a renderer; project/profile edits never mutate an issued release.
CREATE TABLE IF NOT EXISTS estimate_document_sequences (
    tenant_id TEXT NOT NULL,
    document_kind TEXT NOT NULL
        CHECK (document_kind IN ('pack', 'commercial_offer', 'local_estimate', 'conjunctural_analysis', 'invoice')),
    document_year INTEGER NOT NULL CHECK (document_year BETWEEN 2000 AND 9999),
    next_number INTEGER NOT NULL CHECK (next_number >= 1 AND next_number <= 999999),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, document_kind, document_year),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
) STRICT;

CREATE TABLE IF NOT EXISTS estimate_document_issues (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    estimate_version INTEGER NOT NULL CHECK (estimate_version >= 1),
    document_kind TEXT NOT NULL
        CHECK (document_kind IN ('pack', 'commercial_offer', 'local_estimate', 'conjunctural_analysis', 'invoice')),
    mode TEXT NOT NULL CHECK (mode IN ('preliminary', 'issue')),
    status TEXT NOT NULL CHECK (status IN ('preliminary', 'issued', 'revoked')),
    document_year INTEGER NOT NULL CHECK (document_year BETWEEN 2000 AND 9999),
    sequence_number INTEGER NOT NULL CHECK (sequence_number BETWEEN 1 AND 999999),
    document_number TEXT NOT NULL
        CHECK (length(document_number) BETWEEN 12 AND 32),
    snapshot_json TEXT NOT NULL CHECK (json_valid(snapshot_json)),
    source_hash TEXT NOT NULL
        CHECK (length(source_hash) = 71 AND source_hash LIKE 'sha256:%'
               AND substr(source_hash, 8) NOT GLOB '*[^0-9a-f]*'),
    renderer_version TEXT NOT NULL
        CHECK (length(renderer_version) BETWEEN 1 AND 64),
    requested_kinds_json TEXT NOT NULL CHECK (json_valid(requested_kinds_json)),
    idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 16 AND 160),
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    issued_at TEXT,
    revoked_at TEXT,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, document_number),
    UNIQUE (tenant_id, idempotency_key),
    UNIQUE (tenant_id, project_id, document_id, estimate_version, document_kind, mode, renderer_version),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, document_id, estimate_version)
        REFERENCES estimate_versions(tenant_id, document_id, version) ON DELETE RESTRICT,
    FOREIGN KEY (created_by_user_id, tenant_id) REFERENCES users(id, tenant_id) ON DELETE RESTRICT
) STRICT;

CREATE INDEX IF NOT EXISTS ix_estimate_document_issues_scope
    ON estimate_document_issues(tenant_id, project_id, created_at DESC, id);

CREATE TABLE IF NOT EXISTS estimate_document_artifacts (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    issue_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    artifact_kind TEXT NOT NULL
        CHECK (artifact_kind IN ('pdf', 'xlsx', 'docx', 'zip')),
    filename TEXT NOT NULL
        CHECK (length(filename) BETWEEN 1 AND 240
               AND instr(filename, '/') = 0 AND instr(filename, char(92)) = 0
               AND instr(filename, char(0)) = 0),
    media_type TEXT NOT NULL CHECK (length(media_type) BETWEEN 3 AND 160),
    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 52428800),
    storage_ref TEXT NOT NULL
        CHECK (length(storage_ref) BETWEEN 32 AND 240 AND storage_ref LIKE 'cas://sha256/%'),
    artifact_hash TEXT NOT NULL
        CHECK (length(artifact_hash) = 71 AND artifact_hash LIKE 'sha256:%'
               AND substr(artifact_hash, 8) NOT GLOB '*[^0-9a-f]*'),
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, issue_id, artifact_kind),
    FOREIGN KEY (tenant_id, issue_id) REFERENCES estimate_document_issues(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id, tenant_id) REFERENCES users(id, tenant_id) ON DELETE RESTRICT
) STRICT;

CREATE INDEX IF NOT EXISTS ix_estimate_document_artifacts_scope
    ON estimate_document_artifacts(tenant_id, project_id, issue_id, artifact_kind);

-- Payment requisites are explicit tenant-owned data.  No production invoice
-- can be rendered from placeholders or from a different project/tenant.
CREATE TABLE IF NOT EXISTS counterparty_requisites (
    tenant_id TEXT NOT NULL,
    counterparty_id TEXT NOT NULL,
    legal_name TEXT NOT NULL CHECK (length(legal_name) BETWEEN 1 AND 240),
    tax_id TEXT NOT NULL CHECK (length(tax_id) IN (10, 12) AND tax_id NOT GLOB '*[^0-9]*'),
    registration_code TEXT CHECK (registration_code IS NULL OR (length(registration_code) = 9 AND registration_code NOT GLOB '*[^0-9]*')),
    bank_name TEXT NOT NULL CHECK (length(bank_name) BETWEEN 1 AND 240),
    bank_identification_code TEXT NOT NULL CHECK (length(bank_identification_code) = 9 AND bank_identification_code NOT GLOB '*[^0-9]*'),
    settlement_account TEXT NOT NULL CHECK (length(settlement_account) = 20 AND settlement_account NOT GLOB '*[^0-9]*'),
    correspondent_account TEXT NOT NULL CHECK (length(correspondent_account) = 20 AND correspondent_account NOT GLOB '*[^0-9]*'),
    legal_address TEXT,
    basis TEXT NOT NULL CHECK (length(basis) BETWEEN 1 AND 500),
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, counterparty_id),
    FOREIGN KEY (tenant_id, counterparty_id) REFERENCES counterparties(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id, tenant_id) REFERENCES users(id, tenant_id) ON DELETE RESTRICT
) STRICT;

PRAGMA user_version = 50;
