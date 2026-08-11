PRAGMA foreign_keys = OFF;

BEGIN IMMEDIATE;

ALTER TABLE user_model_preferences RENAME TO user_model_preferences_v58;

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
            AND model_id NOT GLOB '*[^A-Za-z0-9._:-]*'
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

INSERT INTO user_model_preferences (
    tenant_id, user_id, runtime_profile, model_id, reasoning_effort, service_tier, updated_at
)
SELECT tenant_id, user_id, runtime_profile, model_id, reasoning_effort, service_tier, updated_at
FROM user_model_preferences_v58;

DROP TABLE user_model_preferences_v58;

PRAGMA foreign_keys = ON;

PRAGMA user_version = 58;

COMMIT;
