BEGIN IMMEDIATE;

-- This is provenance for the reviewed, server-owned prompt constraints used
-- by a Product Chat run.  It is deliberately not an AgentAssignment: only
-- Logical Home owns workflow, leases, A2A tasks and authority decisions.
CREATE TABLE chat_run_skill_contexts (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    stage TEXT NOT NULL
        CHECK (length(stage) BETWEEN 3 AND 96),
    skill_id TEXT NOT NULL
        CHECK (length(skill_id) BETWEEN 3 AND 160),
    skill_version TEXT NOT NULL
        CHECK (length(skill_version) BETWEEN 3 AND 160),
    role TEXT NOT NULL
        CHECK (length(role) BETWEEN 3 AND 96),
    authority_boundary TEXT NOT NULL
        CHECK (length(authority_boundary) BETWEEN 3 AND 160),
    instruction_hash TEXT NOT NULL
        CHECK (
            length(instruction_hash) = 71
            AND instruction_hash LIKE 'sha256:%'
            AND substr(instruction_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    registry_version TEXT NOT NULL
        CHECK (length(registry_version) BETWEEN 3 AND 160),
    schema_version TEXT NOT NULL
        CHECK (length(schema_version) BETWEEN 1 AND 32),
    plan_hash TEXT NOT NULL
        CHECK (
            length(plan_hash) = 71
            AND plan_hash LIKE 'sha256:%'
            AND substr(plan_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, run_id, stage, skill_id, skill_version),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES chat_runs (tenant_id, id)
        ON DELETE RESTRICT
);

CREATE INDEX ix_chat_run_skill_contexts_run
    ON chat_run_skill_contexts (tenant_id, run_id, stage, id);

PRAGMA user_version = 22;

COMMIT;
