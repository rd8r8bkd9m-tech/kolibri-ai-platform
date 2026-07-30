PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS provider_connections (
    tenant_id TEXT NOT NULL,
    provider_id TEXT NOT NULL
        CHECK (provider_id IN ('mimo-code', 'codex-cli')),
    status TEXT NOT NULL DEFAULT 'not_configured'
        CHECK (status IN ('not_configured', 'pending', 'connected', 'error')),
    auth_flow_supported INTEGER NOT NULL DEFAULT 0
        CHECK (auth_flow_supported IN (0, 1)),
    authority_observed INTEGER NOT NULL DEFAULT 0
        CHECK (authority_observed IN (0, 1)),
    last_verified_at TEXT,
    last_evidence_hash TEXT
        CHECK (
            last_evidence_hash IS NULL
            OR (
                length(last_evidence_hash) = 71
                AND last_evidence_hash LIKE 'sha256:%'
                AND substr(last_evidence_hash, 8)
                    NOT GLOB '*[^0-9a-f]*'
            )
        ),
    last_intent_id TEXT,
    last_error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, provider_id),
    CHECK (
        status <> 'connected'
        OR (
            authority_observed = 1
            AND last_verified_at IS NOT NULL
            AND last_error_code IS NULL
        )
    ),
    CHECK (
        last_error_code IS NULL
        OR length(last_error_code) BETWEEN 3 AND 128
    ),
    FOREIGN KEY (tenant_id)
        REFERENCES tenants (id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_provider_connections_tenant_status
    ON provider_connections (tenant_id, status, provider_id);

CREATE TABLE IF NOT EXISTS provider_enrollment_intents (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    provider_id TEXT NOT NULL
        CHECK (provider_id IN ('mimo-code', 'codex-cli')),
    requested_by_user_id TEXT NOT NULL,
    owner_authorization_decision_id TEXT NOT NULL
        CHECK (
            length(owner_authorization_decision_id) BETWEEN 8 AND 160
            AND owner_authorization_decision_id
                GLOB 'decision_[A-Za-z0-9._~-]*'
        ),
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
    command_json TEXT NOT NULL
        CHECK (json_valid(command_json)),
    command_hash TEXT NOT NULL
        CHECK (
            length(command_hash) = 71
            AND command_hash LIKE 'sha256:%'
            AND substr(command_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    api_response_json TEXT NOT NULL
        CHECK (json_valid(api_response_json)),
    state TEXT NOT NULL DEFAULT 'queued'
        CHECK (
            state IN (
                'queued',
                'leased',
                'retry',
                'blocked',
                'completed'
            )
        ),
    authority_status TEXT
        CHECK (
            authority_status IS NULL
            OR authority_status IN (
                'connected',
                'failed'
            )
        ),
    authority_response_hash TEXT
        CHECK (
            authority_response_hash IS NULL
            OR (
                length(authority_response_hash) = 71
                AND authority_response_hash LIKE 'sha256:%'
                AND substr(authority_response_hash, 8)
                    NOT GLOB '*[^0-9a-f]*'
            )
        ),
    attempts INTEGER NOT NULL DEFAULT 0
        CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 8
        CHECK (max_attempts BETWEEN 1 AND 100),
    available_at TEXT NOT NULL,
    lease_owner TEXT,
    lease_token TEXT,
    lease_until TEXT,
    fencing_token INTEGER NOT NULL DEFAULT 0
        CHECK (fencing_token >= 0),
    last_error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (
        tenant_id,
        requested_by_user_id,
        provider_id,
        idempotency_key_hash
    ),
    CHECK (attempts <= max_attempts),
    CHECK (
        (
            state = 'leased'
            AND lease_owner IS NOT NULL
            AND lease_token IS NOT NULL
            AND lease_until IS NOT NULL
        )
        OR (
            state <> 'leased'
            AND lease_owner IS NULL
            AND lease_token IS NULL
            AND lease_until IS NULL
        )
    ),
    CHECK (
        (
            state IN ('blocked', 'completed')
            AND completed_at IS NOT NULL
        )
        OR (
            state NOT IN ('blocked', 'completed')
            AND completed_at IS NULL
        )
    ),
    CHECK (
        (
            state = 'completed'
            AND authority_status IS NOT NULL
            AND authority_response_hash IS NOT NULL
        )
        OR state <> 'completed'
    ),
    CHECK (
        last_error_code IS NULL
        OR length(last_error_code) BETWEEN 3 AND 128
    ),
    FOREIGN KEY (tenant_id, provider_id)
        REFERENCES provider_connections (tenant_id, provider_id)
        ON DELETE CASCADE,
    FOREIGN KEY (requested_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_provider_enrollment_active
    ON provider_enrollment_intents (tenant_id, provider_id)
    WHERE state IN ('queued', 'leased', 'retry');

CREATE INDEX IF NOT EXISTS ix_provider_enrollment_claim
    ON provider_enrollment_intents (
        state,
        available_at,
        lease_until,
        created_at,
        tenant_id,
        id
    );

CREATE INDEX IF NOT EXISTS ix_provider_enrollment_tenant_provider
    ON provider_enrollment_intents (
        tenant_id,
        provider_id,
        created_at DESC,
        id
    );

PRAGMA user_version = 5;
