CREATE SCHEMA IF NOT EXISTS kolibri;

CREATE TABLE IF NOT EXISTS kolibri.idempotency_records (
    principal_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    replay_json JSONB,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (principal_id, scope, idempotency_key),
    CONSTRAINT idempotency_request_sha256_format
        CHECK (request_sha256 ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT idempotency_resource_binding_complete
        CHECK (
            (resource_id IS NULL AND replay_json IS NULL)
            OR (resource_id IS NOT NULL AND replay_json IS NOT NULL)
        )
);

CREATE TABLE IF NOT EXISTS kolibri.responses (
    id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    session_id TEXT,
    project_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT 'kolibri',
    task_type TEXT NOT NULL,
    status TEXT NOT NULL,
    request_json JSONB NOT NULL,
    request_sha256 TEXT NOT NULL,
    output_json JSONB NOT NULL DEFAULT '[]'::JSONB,
    output_text TEXT NOT NULL DEFAULT '',
    error_json JSONB,
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT responses_public_model CHECK (model = 'kolibri'),
    CONSTRAINT responses_status CHECK (
        status IN (
            'queued', 'planning', 'running', 'waiting_for_input',
            'approval_required', 'verifying', 'completed', 'failed',
            'cancelled', 'incomplete'
        )
    ),
    CONSTRAINT responses_request_sha256_format
        CHECK (request_sha256 ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT responses_request_is_object
        CHECK (jsonb_typeof(request_json) = 'object'),
    CONSTRAINT responses_output_is_array
        CHECK (jsonb_typeof(output_json) = 'array')
);

CREATE INDEX IF NOT EXISTS responses_principal_project_created_idx
    ON kolibri.responses (principal_id, project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS kolibri.messages (
    id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    session_id TEXT,
    project_id TEXT NOT NULL,
    response_id TEXT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT messages_role CHECK (role IN ('user', 'assistant')),
    CONSTRAINT messages_response_fk
        FOREIGN KEY (response_id) REFERENCES kolibri.responses(id) ON DELETE CASCADE,
    CONSTRAINT messages_one_role_per_response UNIQUE (response_id, role)
);

CREATE INDEX IF NOT EXISTS messages_project_history_idx
    ON kolibri.messages (principal_id, project_id, created_at, id);

CREATE TABLE IF NOT EXISTS kolibri.event_stream_heads (
    subject TEXT PRIMARY KEY,
    last_sequence BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT event_stream_sequence_positive CHECK (last_sequence >= 1)
);

CREATE TABLE IF NOT EXISTS kolibri.events (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    subject TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    sequence BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    data JSONB NOT NULL,
    provenance JSONB NOT NULL,
    authority_epoch BIGINT NOT NULL,
    idempotency_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT events_schema_v1 CHECK (schema_version = 'kolibri.event.v1'),
    CONSTRAINT events_home_source CHECK (source = 'control-plane/home'),
    CONSTRAINT events_sequence_positive CHECK (sequence >= 1),
    CONSTRAINT events_authority_epoch_positive CHECK (authority_epoch >= 1),
    CONSTRAINT events_data_is_object CHECK (jsonb_typeof(data) = 'object'),
    CONSTRAINT events_provenance_is_object CHECK (jsonb_typeof(provenance) = 'object'),
    CONSTRAINT events_subject_sequence_unique UNIQUE (subject, sequence),
    CONSTRAINT events_source_idempotency_unique UNIQUE (source, idempotency_key)
);

CREATE INDEX IF NOT EXISTS events_trace_idx
    ON kolibri.events (trace_id, occurred_at, id);

CREATE TABLE IF NOT EXISTS kolibri.outbox (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    topic TEXT NOT NULL,
    payload JSONB NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL,
    claimed_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT outbox_event_fk
        FOREIGN KEY (event_id) REFERENCES kolibri.events(id) ON DELETE RESTRICT,
    CONSTRAINT outbox_state CHECK (state IN ('pending', 'publishing', 'published', 'failed')),
    CONSTRAINT outbox_attempts_nonnegative CHECK (attempts >= 0),
    CONSTRAINT outbox_payload_is_object CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX IF NOT EXISTS outbox_dispatch_idx
    ON kolibri.outbox (state, available_at, created_at)
    WHERE state IN ('pending', 'failed');
