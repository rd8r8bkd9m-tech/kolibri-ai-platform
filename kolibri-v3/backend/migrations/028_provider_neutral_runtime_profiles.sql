PRAGMA foreign_keys = OFF;

BEGIN IMMEDIATE;

-- Runtime/profile identifiers are data-owned registry IDs. Keep the legacy
-- values valid while replacing the closed provider enums with the same bounded
-- identifier grammar used by the runtime contract.
CREATE TABLE users_v28 (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    email_normalized TEXT NOT NULL COLLATE NOCASE,
    email TEXT NOT NULL,
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    role TEXT NOT NULL CHECK (role IN ('owner', 'user')),
    preferred_agent_profile TEXT NOT NULL DEFAULT 'auto'
        CHECK (
            length(preferred_agent_profile) BETWEEN 2 AND 96
            AND substr(preferred_agent_profile, 1, 1) GLOB '[a-z0-9]'
            AND preferred_agent_profile NOT GLOB '*[^a-z0-9._-]*'
        ),
    password_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    preferred_model TEXT
        CHECK (
            preferred_model IS NULL
            OR length(preferred_model) BETWEEN 1 AND 120
        ),
    preferred_reasoning_effort TEXT
        CHECK (
            preferred_reasoning_effort IS NULL
            OR (
                length(preferred_reasoning_effort) BETWEEN 1 AND 32
                AND preferred_reasoning_effort
                    NOT GLOB '*[^a-z0-9_-]*'
            )
        ),
    preferred_service_tier TEXT
        CHECK (
            preferred_service_tier IS NULL
            OR (
                length(preferred_service_tier) BETWEEN 1 AND 32
                AND preferred_service_tier NOT GLOB '*[^a-z0-9_-]*'
            )
        ),
    UNIQUE (email_normalized),
    UNIQUE (id, tenant_id),
    FOREIGN KEY (tenant_id)
        REFERENCES tenants (id)
        ON DELETE RESTRICT
) STRICT;

INSERT INTO users_v28 (
    id,
    tenant_id,
    email_normalized,
    email,
    name,
    role,
    preferred_agent_profile,
    password_hash,
    created_at,
    updated_at,
    preferred_model,
    preferred_reasoning_effort,
    preferred_service_tier
)
SELECT
    id,
    tenant_id,
    email_normalized,
    email,
    name,
    role,
    preferred_agent_profile,
    password_hash,
    created_at,
    updated_at,
    preferred_model,
    preferred_reasoning_effort,
    preferred_service_tier
FROM users;

CREATE TABLE chat_runs_v28 (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    client_run_id TEXT NOT NULL,
    request_hash TEXT NOT NULL
        CHECK (request_hash GLOB 'sha256:[0-9a-f]*'),
    input_message_id TEXT NOT NULL,
    assistant_message_id TEXT,
    requested_by_user_id TEXT NOT NULL,
    selected_profile TEXT NOT NULL
        CHECK (
            length(selected_profile) BETWEEN 2 AND 96
            AND substr(selected_profile, 1, 1) GLOB '[a-z0-9]'
            AND selected_profile NOT GLOB '*[^a-z0-9._-]*'
        ),
    status TEXT NOT NULL
        CHECK (status IN ('running', 'succeeded', 'failed')),
    outcome TEXT
        CHECK (outcome IS NULL OR outcome IN ('success', 'failure')),
    last_event_sequence INTEGER NOT NULL DEFAULT 0
        CHECK (last_event_sequence >= 0),
    error_code TEXT,
    heartbeat_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, thread_id, client_run_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, thread_id)
        REFERENCES chat_threads (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, input_message_id)
        REFERENCES chat_messages (tenant_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, assistant_message_id)
        REFERENCES chat_messages (tenant_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (requested_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

INSERT INTO chat_runs_v28 (
    tenant_id,
    id,
    project_id,
    thread_id,
    client_run_id,
    request_hash,
    input_message_id,
    assistant_message_id,
    requested_by_user_id,
    selected_profile,
    status,
    outcome,
    last_event_sequence,
    error_code,
    heartbeat_at,
    created_at,
    updated_at,
    finished_at
)
SELECT
    tenant_id,
    id,
    project_id,
    thread_id,
    client_run_id,
    request_hash,
    input_message_id,
    assistant_message_id,
    requested_by_user_id,
    selected_profile,
    status,
    outcome,
    last_event_sequence,
    error_code,
    heartbeat_at,
    created_at,
    updated_at,
    finished_at
FROM chat_runs;

CREATE TABLE product_run_runtime_v28 (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    execution_id TEXT,
    resolved_profile TEXT
        CHECK (
            resolved_profile IS NULL
            OR (
                length(resolved_profile) BETWEEN 2 AND 96
                AND substr(resolved_profile, 1, 1) GLOB '[a-z0-9]'
                AND resolved_profile NOT GLOB '*[^a-z0-9._-]*'
            )
        ),
    verification_status TEXT NOT NULL DEFAULT 'not_applicable'
        CHECK (
            verification_status IN (
                'not_applicable',
                'unverified',
                'verified'
            )
        ),
    result_hash TEXT
        CHECK (
            result_hash IS NULL
            OR (
                length(result_hash) = 71
                AND result_hash LIKE 'sha256:%'
                AND substr(result_hash, 8) NOT GLOB '*[^0-9a-f]*'
            )
        ),
    evidence_json TEXT
        CHECK (evidence_json IS NULL OR json_valid(evidence_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, run_id),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES chat_runs (tenant_id, id)
        ON DELETE CASCADE
);

INSERT INTO product_run_runtime_v28 (
    tenant_id,
    run_id,
    execution_id,
    resolved_profile,
    verification_status,
    result_hash,
    evidence_json,
    created_at,
    updated_at
)
SELECT
    tenant_id,
    run_id,
    execution_id,
    resolved_profile,
    verification_status,
    result_hash,
    evidence_json,
    created_at,
    updated_at
FROM product_run_runtime;

CREATE TABLE provider_connections_v28 (
    tenant_id TEXT NOT NULL,
    provider_id TEXT NOT NULL
        CHECK (
            length(provider_id) BETWEEN 2 AND 96
            AND substr(provider_id, 1, 1) GLOB '[a-z0-9]'
            AND provider_id NOT GLOB '*[^a-z0-9._-]*'
        ),
    status TEXT NOT NULL DEFAULT 'not_configured'
        CHECK (
            status IN ('not_configured', 'pending', 'connected', 'error')
        ),
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

INSERT INTO provider_connections_v28 (
    tenant_id,
    provider_id,
    status,
    auth_flow_supported,
    authority_observed,
    last_verified_at,
    last_evidence_hash,
    last_intent_id,
    last_error_code,
    created_at,
    updated_at
)
SELECT
    tenant_id,
    provider_id,
    status,
    auth_flow_supported,
    authority_observed,
    last_verified_at,
    last_evidence_hash,
    last_intent_id,
    last_error_code,
    created_at,
    updated_at
FROM provider_connections;

CREATE TABLE provider_enrollment_intents_v28 (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    provider_id TEXT NOT NULL
        CHECK (
            length(provider_id) BETWEEN 2 AND 96
            AND substr(provider_id, 1, 1) GLOB '[a-z0-9]'
            AND provider_id NOT GLOB '*[^a-z0-9._-]*'
        ),
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
            OR authority_status IN ('connected', 'failed')
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

INSERT INTO provider_enrollment_intents_v28 (
    tenant_id,
    id,
    provider_id,
    requested_by_user_id,
    owner_authorization_decision_id,
    idempotency_key_hash,
    request_hash,
    command_json,
    command_hash,
    api_response_json,
    state,
    authority_status,
    authority_response_hash,
    attempts,
    max_attempts,
    available_at,
    lease_owner,
    lease_token,
    lease_until,
    fencing_token,
    last_error_code,
    created_at,
    updated_at,
    completed_at
)
SELECT
    tenant_id,
    id,
    provider_id,
    requested_by_user_id,
    owner_authorization_decision_id,
    idempotency_key_hash,
    request_hash,
    command_json,
    command_hash,
    api_response_json,
    state,
    authority_status,
    authority_response_hash,
    attempts,
    max_attempts,
    available_at,
    lease_owner,
    lease_token,
    lease_until,
    fencing_token,
    last_error_code,
    created_at,
    updated_at,
    completed_at
FROM provider_enrollment_intents;

DROP TABLE provider_enrollment_intents;
DROP TABLE provider_connections;
DROP TABLE product_run_runtime;
DROP TABLE chat_runs;
DROP TABLE users;

ALTER TABLE users_v28 RENAME TO users;
ALTER TABLE chat_runs_v28 RENAME TO chat_runs;
ALTER TABLE product_run_runtime_v28 RENAME TO product_run_runtime;
ALTER TABLE provider_connections_v28 RENAME TO provider_connections;
ALTER TABLE provider_enrollment_intents_v28
    RENAME TO provider_enrollment_intents;

CREATE TABLE user_model_preferences (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    runtime_profile TEXT NOT NULL
        CHECK (
            length(runtime_profile) BETWEEN 2 AND 96
            AND substr(runtime_profile, 1, 1) GLOB '[a-z0-9]'
            AND runtime_profile NOT GLOB '*[^a-z0-9._-]*'
        ),
    model_id TEXT NOT NULL
        CHECK (
            length(model_id) BETWEEN 1 AND 120
            AND substr(model_id, 1, 1) GLOB '[A-Za-z0-9]'
            AND model_id NOT GLOB '*[^A-Za-z0-9._-]*'
        ),
    reasoning_effort TEXT
        CHECK (
            reasoning_effort IS NULL
            OR (
                length(reasoning_effort) BETWEEN 1 AND 32
                AND reasoning_effort NOT GLOB '*[^a-z0-9_-]*'
            )
        ),
    service_tier TEXT
        CHECK (
            service_tier IS NULL
            OR (
                length(service_tier) BETWEEN 1 AND 32
                AND service_tier NOT GLOB '*[^a-z0-9_-]*'
            )
        ),
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, user_id, runtime_profile),
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE CASCADE
) STRICT;

-- v25-v27 only persisted these legacy columns after validating an explicit
-- Codex selection. A null model has no safely attributable preference and is
-- deliberately not backfilled.
INSERT INTO user_model_preferences (
    tenant_id,
    user_id,
    runtime_profile,
    model_id,
    reasoning_effort,
    service_tier,
    updated_at
)
SELECT
    tenant_id,
    id,
    'codex-cli',
    preferred_model,
    preferred_reasoning_effort,
    preferred_service_tier,
    updated_at
FROM users
WHERE preferred_model IS NOT NULL
  AND length(preferred_model) BETWEEN 1 AND 120
  AND substr(preferred_model, 1, 1) GLOB '[A-Za-z0-9]'
  AND preferred_model NOT GLOB '*[^A-Za-z0-9._-]*';

-- Keep the legacy columns as an exact projection of the currently selected
-- profile. A saved Codex preference therefore cannot leak into MiMo, auto, or
-- a future runtime profile.
UPDATE users
SET preferred_model = (
        SELECT preference.model_id
        FROM user_model_preferences AS preference
        WHERE preference.tenant_id = users.tenant_id
          AND preference.user_id = users.id
          AND preference.runtime_profile = users.preferred_agent_profile
    ),
    preferred_reasoning_effort = (
        SELECT preference.reasoning_effort
        FROM user_model_preferences AS preference
        WHERE preference.tenant_id = users.tenant_id
          AND preference.user_id = users.id
          AND preference.runtime_profile = users.preferred_agent_profile
    ),
    preferred_service_tier = (
        SELECT preference.service_tier
        FROM user_model_preferences AS preference
        WHERE preference.tenant_id = users.tenant_id
          AND preference.user_id = users.id
          AND preference.runtime_profile = users.preferred_agent_profile
    );

CREATE INDEX ix_chat_runs_tenant_thread_created
    ON chat_runs (tenant_id, thread_id, created_at DESC, id);

CREATE INDEX ix_chat_runs_tenant_status_heartbeat
    ON chat_runs (tenant_id, status, heartbeat_at);

CREATE UNIQUE INDEX uq_product_run_runtime_execution
    ON product_run_runtime (tenant_id, execution_id)
    WHERE execution_id IS NOT NULL;

CREATE INDEX ix_provider_connections_tenant_status
    ON provider_connections (tenant_id, status, provider_id);

CREATE UNIQUE INDEX uq_provider_enrollment_active
    ON provider_enrollment_intents (tenant_id, provider_id)
    WHERE state IN ('queued', 'leased', 'retry');

CREATE INDEX ix_provider_enrollment_claim
    ON provider_enrollment_intents (
        state,
        available_at,
        lease_until,
        created_at,
        tenant_id,
        id
    );

CREATE INDEX ix_provider_enrollment_tenant_provider
    ON provider_enrollment_intents (
        tenant_id,
        provider_id,
        created_at DESC,
        id
    );

PRAGMA user_version = 28;

COMMIT;

PRAGMA foreign_keys = ON;
