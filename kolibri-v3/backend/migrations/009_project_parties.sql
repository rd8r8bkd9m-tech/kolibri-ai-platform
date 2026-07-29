PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS counterparties (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    entity_type TEXT NOT NULL
        CHECK (entity_type IN ('person', 'organization')),
    display_name TEXT NOT NULL
        CHECK (length(display_name) BETWEEN 1 AND 240),
    tax_id TEXT
        CHECK (
            tax_id IS NULL
            OR (
                length(tax_id) IN (10, 12)
                AND tax_id NOT GLOB '*[^0-9]*'
            )
        ),
    registration_code TEXT
        CHECK (
            registration_code IS NULL
            OR (
                length(registration_code) = 9
                AND registration_code NOT GLOB '*[^0-9]*'
            )
        ),
    source_type TEXT NOT NULL
        CHECK (source_type IN ('user', 'imported', 'verified')),
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id)
        REFERENCES tenants (id)
        ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_counterparties_tenant_name
    ON counterparties (tenant_id, display_name, id);

CREATE TABLE IF NOT EXISTS project_parties (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    counterparty_id TEXT NOT NULL,
    role TEXT NOT NULL
        CHECK (role IN ('client', 'contractor')),
    is_primary INTEGER NOT NULL DEFAULT 0
        CHECK (is_primary IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, counterparty_id, role),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, counterparty_id)
        REFERENCES counterparties (tenant_id, id)
        ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_project_parties_primary_role
    ON project_parties (tenant_id, project_id, role)
    WHERE is_primary = 1 AND status = 'active';

PRAGMA user_version = 9;
