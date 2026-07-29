PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS price_observations (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    estimate_version INTEGER NOT NULL
        CHECK (estimate_version >= 1),
    row_id TEXT NOT NULL,
    item_key TEXT NOT NULL
        CHECK (
            length(item_key) = 71
            AND item_key LIKE 'sha256:%'
            AND substr(item_key, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    item_kind TEXT NOT NULL
        CHECK (item_kind IN ('work', 'material', 'equipment', 'service')),
    description TEXT NOT NULL,
    normalized_description TEXT NOT NULL,
    region TEXT NOT NULL,
    unit TEXT NOT NULL,
    previous_unit_price_rub TEXT,
    observed_unit_price_rub TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'RUB'
        CHECK (currency = 'RUB'),
    source_type TEXT NOT NULL
        CHECK (
            source_type IN (
                'ai_preliminary',
                'user_edit',
                'official_reference',
                'supplier_offer',
                'customer_approved',
                'contract_price'
            )
        ),
    lifecycle TEXT NOT NULL
        CHECK (lifecycle IN ('draft', 'shared', 'approved', 'contracted')),
    context_json TEXT NOT NULL
        CHECK (json_valid(context_json)),
    evidence_quote_id TEXT,
    aggregate_eligible INTEGER NOT NULL DEFAULT 0
        CHECK (aggregate_eligible IN (0, 1)),
    created_by_user_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (
        tenant_id,
        document_id,
        estimate_version,
        row_id,
        source_type
    ),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, document_id, estimate_version)
        REFERENCES estimate_versions (tenant_id, document_id, version)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, evidence_quote_id)
        REFERENCES pricing_quotes (tenant_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_price_observations_personal_catalog
    ON price_observations (
        tenant_id,
        created_by_user_id,
        region,
        item_key,
        observed_at DESC
    );

CREATE INDEX IF NOT EXISTS ix_price_observations_future_aggregation
    ON price_observations (
        aggregate_eligible,
        region,
        item_key,
        observed_at DESC
    );

PRAGMA user_version = 14;
