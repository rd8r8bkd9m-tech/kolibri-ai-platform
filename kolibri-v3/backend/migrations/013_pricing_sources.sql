PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pricing_source_snapshots (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    source_type TEXT NOT NULL
        CHECK (source_type IN ('fgis_cs', 'supplier_offer')),
    source_uri TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    fresh_until TEXT NOT NULL,
    payload_hash TEXT NOT NULL
        CHECK (
            length(payload_hash) = 71
            AND payload_hash LIKE 'sha256:%'
            AND substr(payload_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    payload_json TEXT NOT NULL
        CHECK (json_valid(payload_json)),
    created_by_user_id TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, source_type, source_uri, payload_hash),
    FOREIGN KEY (tenant_id)
        REFERENCES tenants (id)
        ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS pricing_quotes (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    quote_type TEXT NOT NULL
        CHECK (quote_type IN ('official_indicative', 'supplier_offer')),
    binding_status TEXT NOT NULL
        CHECK (
            binding_status IN (
                'indicative',
                'user_attested_indicative',
                'user_attested_binding'
            )
        ),
    supplier_name TEXT,
    source_reference TEXT NOT NULL,
    region TEXT NOT NULL,
    price_zone TEXT,
    period_label TEXT,
    price_date TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    material_code TEXT,
    material_name TEXT NOT NULL,
    unit TEXT NOT NULL,
    unit_price_rub TEXT NOT NULL,
    delivery_per_unit_rub TEXT NOT NULL,
    landed_unit_price_rub TEXT NOT NULL,
    tax_status TEXT NOT NULL
        CHECK (tax_status IN ('excluded', 'included', 'unknown')),
    availability TEXT NOT NULL
        CHECK (availability IN ('available', 'unknown', 'unavailable')),
    lead_time_days INTEGER
        CHECK (
            lead_time_days IS NULL
            OR lead_time_days BETWEEN 0 AND 3650
        ),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, snapshot_id)
        REFERENCES pricing_source_snapshots (tenant_id, id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_pricing_quotes_lookup
    ON pricing_quotes (
        tenant_id,
        region,
        material_code,
        valid_until DESC
    );

CREATE TABLE IF NOT EXISTS estimate_price_links (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    estimate_version INTEGER NOT NULL
        CHECK (estimate_version >= 1),
    row_id TEXT NOT NULL,
    quote_id TEXT NOT NULL,
    applied_unit_price_rub TEXT NOT NULL,
    linked_by_user_id TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, document_id, estimate_version, row_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, document_id, estimate_version)
        REFERENCES estimate_versions (tenant_id, document_id, version)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, quote_id)
        REFERENCES pricing_quotes (tenant_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (linked_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_estimate_price_links_quote
    ON estimate_price_links (tenant_id, quote_id, linked_at DESC);

CREATE TABLE IF NOT EXISTS pricing_commands (
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
    command_type TEXT NOT NULL
        CHECK (command_type IN ('fgis_refresh', 'supplier_offer')),
    status TEXT NOT NULL
        CHECK (status IN ('running', 'succeeded', 'failed')),
    response_json TEXT
        CHECK (response_json IS NULL OR json_valid(response_json)),
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id)
        REFERENCES tenants (id)
        ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

PRAGMA user_version = 13;
