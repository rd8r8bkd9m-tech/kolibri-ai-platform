PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS chat_client_threads (
    tenant_id TEXT NOT NULL,
    client_thread_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, client_thread_id),
    UNIQUE (tenant_id, thread_id),
    FOREIGN KEY (tenant_id, thread_id)
        REFERENCES chat_threads (tenant_id, id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS product_project_runtime (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    goal_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    goal_state TEXT NOT NULL DEFAULT 'pending'
        CHECK (goal_state IN ('pending', 'initialized', 'failed')),
    goal_error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id),
    UNIQUE (tenant_id, goal_id),
    UNIQUE (tenant_id, case_id),
    CHECK (
        (goal_state IN ('pending', 'initialized') AND goal_error_code IS NULL)
        OR (
            goal_state = 'failed'
            AND goal_error_code IS NOT NULL
            AND length(goal_error_code) BETWEEN 3 AND 128
        )
    ),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_product_project_runtime_goal_state
    ON product_project_runtime (goal_state, updated_at, tenant_id, project_id);

CREATE TABLE IF NOT EXISTS product_run_runtime (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    execution_id TEXT,
    resolved_profile TEXT
        CHECK (
            resolved_profile IS NULL
            OR resolved_profile IN ('mimo-code', 'codex-cli')
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

CREATE UNIQUE INDEX IF NOT EXISTS uq_product_run_runtime_execution
    ON product_run_runtime (tenant_id, execution_id)
    WHERE execution_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS product_runtime_exchanges (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    phase TEXT NOT NULL
        CHECK (phase IN ('goal_initialize', 'case_resolve', 'run_execute')),
    request_method TEXT NOT NULL
        CHECK (request_method IN ('GET', 'POST')),
    path TEXT NOT NULL
        CHECK (
            length(path) BETWEEN 4 AND 256
            AND substr(path, 1, 4) = '/v1/'
            AND instr(path, '://') = 0
            AND instr(path, '?') = 0
            AND instr(path, '#') = 0
            AND instr(path, '\') = 0
        ),
    request_json TEXT NOT NULL
        CHECK (json_valid(request_json)),
    request_hash TEXT NOT NULL
        CHECK (
            length(request_hash) = 71
            AND request_hash LIKE 'sha256:%'
            AND substr(request_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    response_status INTEGER
        CHECK (
            response_status IS NULL
            OR response_status BETWEEN 100 AND 599
        ),
    response_json TEXT
        CHECK (response_json IS NULL OR json_valid(response_json)),
    response_hash TEXT
        CHECK (
            response_hash IS NULL
            OR (
                length(response_hash) = 71
                AND response_hash LIKE 'sha256:%'
                AND substr(response_hash, 8) NOT GLOB '*[^0-9a-f]*'
            )
        ),
    execution_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, run_id, phase),
    CHECK (
        (
            response_status IS NULL
            AND response_json IS NULL
            AND response_hash IS NULL
        )
        OR (
            response_status IS NOT NULL
            AND response_json IS NOT NULL
            AND response_hash IS NOT NULL
        )
    ),
    CHECK (execution_id IS NULL OR response_status IS NOT NULL),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES chat_runs (tenant_id, id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_product_runtime_exchanges_execution
    ON product_runtime_exchanges (tenant_id, execution_id)
    WHERE execution_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_product_runtime_exchanges_run
    ON product_runtime_exchanges (tenant_id, run_id, phase, updated_at);

CREATE TABLE IF NOT EXISTS product_run_outbox (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    command_kind TEXT NOT NULL
        CHECK (
            command_kind IN (
                'product.goal.initialize',
                'product.run.execute'
            )
        ),
    phase TEXT NOT NULL
        CHECK (phase IN ('goal_required', 'run_execute')),
    state TEXT NOT NULL DEFAULT 'queued'
        CHECK (
            state IN (
                'queued',
                'leased',
                'polling',
                'retry',
                'blocked',
                'completed'
            )
        ),
    command_json TEXT NOT NULL
        CHECK (json_valid(command_json)),
    command_hash TEXT NOT NULL
        CHECK (
            length(command_hash) = 71
            AND command_hash LIKE 'sha256:%'
            AND substr(command_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    attempts INTEGER NOT NULL DEFAULT 0
        CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL
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
    UNIQUE (tenant_id, run_id),
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
        last_error_code IS NULL
        OR length(last_error_code) BETWEEN 3 AND 128
    ),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES chat_runs (tenant_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_product_run_outbox_claim
    ON product_run_outbox (
        state,
        available_at,
        lease_until,
        created_at,
        tenant_id,
        id
    );

CREATE INDEX IF NOT EXISTS ix_product_run_outbox_run_state
    ON product_run_outbox (tenant_id, run_id, state);

PRAGMA user_version = 4;
