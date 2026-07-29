PRAGMA foreign_keys = OFF;

BEGIN IMMEDIATE;

-- Migration 026 was already applied on local development databases before
-- access_policy_version was added to its source file. Rebuild the table
-- instead of relying on ALTER TABLE so this migration is valid for both:
--   1. the originally deployed v26 schema without the column; and
--   2. a fresh v26 schema that already contains the column.
CREATE TABLE chat_run_execution_contexts_v27 (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    execution_mode TEXT NOT NULL DEFAULT 'standard'
        CHECK (execution_mode IN ('standard', 'developer')),
    access_mode TEXT NOT NULL DEFAULT 'standard'
        CHECK (access_mode IN ('standard', 'auto', 'full')),
    access_policy_version INTEGER NOT NULL DEFAULT 2
        CHECK (access_policy_version IN (1, 2)),
    authority_role TEXT NOT NULL
        CHECK (authority_role IN ('owner', 'user')),
    authority_user_id TEXT NOT NULL,
    workspace_ref TEXT
        CHECK (
            workspace_ref IS NULL
            OR workspace_ref IN ('repository')
        ),
    sandbox_profile TEXT NOT NULL
        CHECK (
            sandbox_profile IN (
                'read-only',
                'workspace-write',
                'danger-full-access'
            )
        ),
    approval_policy TEXT NOT NULL
        CHECK (approval_policy IN ('never', 'on-request')),
    approvals_reviewer TEXT
        CHECK (
            approvals_reviewer IS NULL
            OR approvals_reviewer IN ('auto_review')
        ),
    model_id TEXT
        CHECK (
            model_id IS NULL
            OR length(model_id) BETWEEN 1 AND 120
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
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, run_id),
    CHECK (
        (
            execution_mode = 'standard'
            AND access_mode = 'standard'
            AND access_policy_version = 2
            AND workspace_ref IS NULL
            AND sandbox_profile = 'read-only'
            AND approval_policy = 'never'
            AND approvals_reviewer IS NULL
        )
        OR (
            execution_mode = 'developer'
            AND access_mode = 'auto'
            AND access_policy_version = 2
            AND authority_role = 'owner'
            AND workspace_ref = 'repository'
            AND sandbox_profile = 'workspace-write'
            AND approval_policy = 'on-request'
            AND approvals_reviewer = 'auto_review'
        )
        OR (
            execution_mode = 'developer'
            AND access_mode = 'full'
            AND access_policy_version = 2
            AND authority_role = 'owner'
            AND workspace_ref = 'repository'
            AND sandbox_profile = 'danger-full-access'
            AND approval_policy = 'never'
            AND approvals_reviewer IS NULL
        )
        OR (
            execution_mode = 'developer'
            AND access_mode = 'auto'
            AND access_policy_version = 1
            AND authority_role = 'owner'
            AND workspace_ref = 'repository'
            AND sandbox_profile = 'workspace-write'
            AND approval_policy = 'never'
            AND approvals_reviewer IS NULL
        )
    ),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES chat_runs (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (authority_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

INSERT INTO chat_run_execution_contexts_v27 (
    tenant_id,
    run_id,
    execution_mode,
    access_mode,
    access_policy_version,
    authority_role,
    authority_user_id,
    workspace_ref,
    sandbox_profile,
    approval_policy,
    approvals_reviewer,
    model_id,
    reasoning_effort,
    service_tier,
    created_at
)
SELECT
    tenant_id,
    run_id,
    execution_mode,
    access_mode,
    CASE
        WHEN execution_mode = 'developer'
             AND access_mode = 'auto'
             AND approval_policy = 'never'
             AND approvals_reviewer IS NULL
            THEN 1
        ELSE 2
    END,
    authority_role,
    authority_user_id,
    workspace_ref,
    sandbox_profile,
    approval_policy,
    approvals_reviewer,
    model_id,
    reasoning_effort,
    service_tier,
    created_at
FROM chat_run_execution_contexts;

DROP TABLE chat_run_execution_contexts;
ALTER TABLE chat_run_execution_contexts_v27
    RENAME TO chat_run_execution_contexts;

CREATE INDEX ix_chat_run_execution_contexts_mode
    ON chat_run_execution_contexts (
        tenant_id,
        execution_mode,
        created_at DESC,
        run_id
    );

PRAGMA user_version = 27;

COMMIT;

PRAGMA foreign_keys = ON;
