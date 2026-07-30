CREATE TABLE IF NOT EXISTS direct_run_outbox (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    public_thread_id TEXT NOT NULL
        CHECK (length(public_thread_id) BETWEEN 1 AND 200),
    public_run_id TEXT NOT NULL
        CHECK (length(public_run_id) BETWEEN 1 AND 200),
    state TEXT NOT NULL DEFAULT 'queued'
        CHECK (state IN ('queued', 'leased', 'blocked', 'completed')),
    lease_owner TEXT,
    lease_token TEXT,
    lease_until TEXT,
    fencing_token INTEGER NOT NULL DEFAULT 0
        CHECK (fencing_token >= 0),
    last_error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (tenant_id, run_id),
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
        last_error_code IS NULL
        OR length(last_error_code) BETWEEN 3 AND 128
    ),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES chat_runs (tenant_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_direct_run_outbox_claim
    ON direct_run_outbox (
        state,
        lease_until,
        created_at,
        tenant_id,
        run_id
    );

-- A run that predates this durable queue may already have crossed an
-- irreversible provider boundary.  Preserve it as an expired lease so the
-- recovery scheduler terminalizes it instead of replaying an ambiguous effect.
INSERT INTO direct_run_outbox (
    tenant_id,
    run_id,
    public_thread_id,
    public_run_id,
    state,
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
    run.tenant_id,
    run.id,
    COALESCE(
        json_extract(started.event_json, '$.threadId'),
        run.thread_id
    ),
    COALESCE(
        json_extract(started.event_json, '$.runId'),
        run.client_run_id
    ),
    'leased',
    'migration-recovery',
    'lease_migration_recovery',
    '1970-01-01T00:00:00+00:00',
    1,
    NULL,
    run.created_at,
    run.updated_at,
    NULL
FROM chat_runs AS run
JOIN chat_run_execution_contexts AS context
  ON context.tenant_id = run.tenant_id
 AND context.run_id = run.id
 AND context.execution_plane = 'direct'
LEFT JOIN chat_run_events AS started
  ON started.tenant_id = run.tenant_id
 AND started.run_id = run.id
 AND started.sequence = 1
 AND started.event_type = 'RUN_STARTED'
WHERE run.status = 'running'
ON CONFLICT(tenant_id, run_id) DO NOTHING;

PRAGMA user_version = 39;
