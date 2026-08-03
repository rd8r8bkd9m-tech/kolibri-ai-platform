PRAGMA foreign_keys = ON;

-- Platform-owner overrides for the professional Agent Cards shipped by the
-- construction module.  The source Agent Card remains the reviewed fallback;
-- each accepted edit creates an immutable revision so a prompt change is
-- observable and can be pinned by durable work.
CREATE TABLE construction_agent_configurations (
    agent_id TEXT PRIMARY KEY
        CHECK (
            length(agent_id) BETWEEN 3 AND 128
            AND substr(agent_id, 1, 1) GLOB '[a-z0-9]'
            AND agent_id NOT GLOB '*[^a-z0-9._-]*'
        ),
    system_prompt TEXT NOT NULL
        CHECK (length(system_prompt) BETWEEN 20 AND 32768),
    model_profile TEXT NOT NULL
        CHECK (
            length(model_profile) BETWEEN 2 AND 96
            AND substr(model_profile, 1, 1) GLOB '[a-z0-9]'
            AND model_profile NOT GLOB '*[^a-z0-9._-]*'
        ),
    revision INTEGER NOT NULL CHECK (revision >= 1),
    updated_at INTEGER NOT NULL CHECK (updated_at >= 0),
    updated_by_user_id TEXT NOT NULL,
    FOREIGN KEY (updated_by_user_id)
        REFERENCES users (id)
        ON DELETE RESTRICT
) STRICT;

CREATE TABLE construction_agent_configuration_history (
    agent_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    system_prompt TEXT NOT NULL
        CHECK (length(system_prompt) BETWEEN 20 AND 32768),
    model_profile TEXT NOT NULL
        CHECK (
            length(model_profile) BETWEEN 2 AND 96
            AND substr(model_profile, 1, 1) GLOB '[a-z0-9]'
            AND model_profile NOT GLOB '*[^a-z0-9._-]*'
        ),
    created_at INTEGER NOT NULL CHECK (created_at >= 0),
    created_by_user_id TEXT NOT NULL,
    PRIMARY KEY (agent_id, revision),
    FOREIGN KEY (created_by_user_id)
        REFERENCES users (id)
        ON DELETE RESTRICT
) STRICT;

CREATE INDEX ix_construction_agent_configuration_history_recent
    ON construction_agent_configuration_history (agent_id, revision DESC);

PRAGMA user_version = 53;
