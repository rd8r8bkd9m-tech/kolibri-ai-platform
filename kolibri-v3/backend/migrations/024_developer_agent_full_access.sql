PRAGMA foreign_keys = OFF;

CREATE TABLE chat_run_execution_contexts_v24 (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    execution_mode TEXT NOT NULL DEFAULT 'standard'
        CHECK (execution_mode IN ('standard', 'developer')),
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
        CHECK (approval_policy IN ('never')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, run_id),
    CHECK (
        (
            execution_mode = 'standard'
            AND workspace_ref IS NULL
            AND sandbox_profile = 'read-only'
        )
        OR (
            execution_mode = 'developer'
            AND authority_role = 'owner'
            AND workspace_ref = 'repository'
            AND sandbox_profile IN (
                'workspace-write',
                'danger-full-access'
            )
        )
    ),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES chat_runs (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (authority_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

INSERT INTO chat_run_execution_contexts_v24 (
    tenant_id, run_id, execution_mode, authority_role, authority_user_id,
    workspace_ref, sandbox_profile, approval_policy, created_at
)
SELECT
    tenant_id, run_id, execution_mode, authority_role, authority_user_id,
    workspace_ref, sandbox_profile, approval_policy, created_at
FROM chat_run_execution_contexts;

DROP TABLE chat_run_execution_contexts;
ALTER TABLE chat_run_execution_contexts_v24
    RENAME TO chat_run_execution_contexts;

CREATE INDEX ix_chat_run_execution_contexts_mode
    ON chat_run_execution_contexts (
        tenant_id,
        execution_mode,
        created_at DESC,
        run_id
    );

PRAGMA foreign_keys = ON;
PRAGMA user_version = 24;
