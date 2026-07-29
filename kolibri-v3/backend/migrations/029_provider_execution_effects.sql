BEGIN IMMEDIATE;

CREATE TABLE provider_execution_effects (
    tenant_id TEXT NOT NULL,
    effect_key TEXT NOT NULL
        CHECK (
            length(effect_key) BETWEEN 16 AND 200
            AND substr(effect_key, 1, 1) GLOB '[A-Za-z0-9]'
            AND effect_key NOT GLOB '*[^A-Za-z0-9._:~-]*'
        ),
    effect_hash TEXT NOT NULL
        CHECK (
            length(effect_hash) = 71
            AND effect_hash LIKE 'sha256:%'
            AND substr(effect_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    runtime_profile TEXT NOT NULL
        CHECK (
            length(runtime_profile) BETWEEN 2 AND 96
            AND substr(runtime_profile, 1, 1) GLOB '[a-z0-9]'
            AND runtime_profile NOT GLOB '*[^a-z0-9._-]*'
        ),
    task_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    assignment_id TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    fencing_token INTEGER NOT NULL CHECK (fencing_token >= 1),
    slot_id TEXT NOT NULL
        CHECK (
            length(slot_id) BETWEEN 1 AND 200
            AND substr(slot_id, 1, 1) GLOB '[A-Za-z0-9]'
            AND slot_id NOT GLOB '*[^A-Za-z0-9._:@/-]*'
        ),
    execution_owner_id TEXT NOT NULL
        CHECK (
            length(execution_owner_id) = 41
            AND execution_owner_id LIKE 'provider_%'
            AND substr(execution_owner_id, 10)
                NOT GLOB '*[^0-9a-f]*'
        ),
    execution_heartbeat_at TEXT NOT NULL,
    execution_deadline_at TEXT NOT NULL,
    state TEXT NOT NULL
        CHECK (state IN ('executing', 'succeeded', 'failed')),
    result_json TEXT
        CHECK (result_json IS NULL OR json_valid(result_json)),
    error_json TEXT
        CHECK (error_json IS NULL OR json_valid(error_json)),
    activity_json TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(activity_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (tenant_id, effect_key),
    CHECK (
        (
            state = 'executing'
            AND result_json IS NULL
            AND error_json IS NULL
            AND completed_at IS NULL
        )
        OR (
            state = 'succeeded'
            AND result_json IS NOT NULL
            AND error_json IS NULL
            AND completed_at IS NOT NULL
        )
        OR (
            state = 'failed'
            AND result_json IS NULL
            AND error_json IS NOT NULL
            AND completed_at IS NOT NULL
        )
    )
) STRICT;

CREATE INDEX ix_provider_execution_effects_task
    ON provider_execution_effects (
        tenant_id,
        task_id,
        attempt_id,
        assignment_id
    );

CREATE UNIQUE INDEX ux_provider_execution_effects_active_slot
    ON provider_execution_effects (slot_id)
    WHERE state = 'executing';

PRAGMA user_version = 29;

COMMIT;
