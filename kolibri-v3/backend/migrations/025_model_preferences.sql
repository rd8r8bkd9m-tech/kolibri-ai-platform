BEGIN IMMEDIATE;

ALTER TABLE users
    ADD COLUMN preferred_model TEXT
    CHECK (
        preferred_model IS NULL
        OR length(preferred_model) BETWEEN 1 AND 120
    );

ALTER TABLE users
    ADD COLUMN preferred_reasoning_effort TEXT
    CHECK (
        preferred_reasoning_effort IS NULL
        OR (
            length(preferred_reasoning_effort) BETWEEN 1 AND 32
            AND preferred_reasoning_effort NOT GLOB '*[^a-z0-9_-]*'
        )
    );

ALTER TABLE chat_run_execution_contexts
    ADD COLUMN model_id TEXT
    CHECK (
        model_id IS NULL
        OR length(model_id) BETWEEN 1 AND 120
    );

ALTER TABLE chat_run_execution_contexts
    ADD COLUMN reasoning_effort TEXT
    CHECK (
        reasoning_effort IS NULL
        OR (
            length(reasoning_effort) BETWEEN 1 AND 32
            AND reasoning_effort NOT GLOB '*[^a-z0-9_-]*'
        )
    );

PRAGMA user_version = 25;

COMMIT;
