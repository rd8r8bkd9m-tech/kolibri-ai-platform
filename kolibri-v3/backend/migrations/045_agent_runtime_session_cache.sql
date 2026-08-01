BEGIN IMMEDIATE;

-- Provider sessions are an acceleration cache only. Product messages remain
-- canonical in chat_messages, and every lookup is bound to the full execution
-- and authority scope before a provider thread can be resumed.
CREATE TABLE agent_runtime_session_cache (
    scope_key TEXT PRIMARY KEY
        CHECK (
            length(scope_key) = 71
            AND scope_key GLOB 'sha256:*'
            AND substr(scope_key, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    product_thread_id TEXT NOT NULL,
    credential_tenant_id TEXT NOT NULL,
    runtime_profile TEXT NOT NULL,
    runtime_id TEXT NOT NULL,
    runtime_mode TEXT NOT NULL
        CHECK (runtime_mode IN ('chat', 'structured', 'developer')),
    execution_profile TEXT NOT NULL,
    workspace_fingerprint TEXT NOT NULL
        CHECK (
            length(workspace_fingerprint) = 71
            AND workspace_fingerprint GLOB 'sha256:*'
            AND substr(workspace_fingerprint, 8)
                NOT GLOB '*[^0-9a-f]*'
        ),
    model_id TEXT NOT NULL,
    reasoning_effort TEXT NOT NULL,
    service_tier TEXT NOT NULL,
    sandbox_profile TEXT NOT NULL,
    approval_policy TEXT NOT NULL,
    approvals_reviewer TEXT NOT NULL,
    instructions_hash TEXT NOT NULL
        CHECK (
            length(instructions_hash) = 71
            AND instructions_hash GLOB 'sha256:*'
            AND substr(instructions_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    output_schema_hash TEXT NOT NULL
        CHECK (
            length(output_schema_hash) = 71
            AND output_schema_hash GLOB 'sha256:*'
            AND substr(output_schema_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    provider_thread_id TEXT NOT NULL
        CHECK (length(provider_thread_id) BETWEEN 1 AND 512),
    canonical_history_hash TEXT NOT NULL
        CHECK (
            length(canonical_history_hash) = 71
            AND canonical_history_hash GLOB 'sha256:*'
            AND substr(canonical_history_hash, 8)
                NOT GLOB '*[^0-9a-f]*'
        ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (
        tenant_id,
        user_id,
        project_id,
        product_thread_id,
        credential_tenant_id,
        runtime_profile,
        runtime_id,
        runtime_mode,
        execution_profile,
        workspace_fingerprint,
        model_id,
        reasoning_effort,
        service_tier,
        sandbox_profile,
        approval_policy,
        approvals_reviewer,
        instructions_hash,
        output_schema_hash
    ),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    FOREIGN KEY (credential_tenant_id)
        REFERENCES tenants(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, product_thread_id)
        REFERENCES chat_threads(tenant_id, id) ON DELETE CASCADE
) STRICT;

CREATE INDEX ix_agent_runtime_session_cache_updated
    ON agent_runtime_session_cache(updated_at DESC, scope_key);

PRAGMA user_version = 45;

COMMIT;
