BEGIN IMMEDIATE;

CREATE TABLE platform_authority_grants (
    authority_id TEXT PRIMARY KEY
        CHECK (authority_id = 'platform_owner'),
    user_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    authority_epoch INTEGER NOT NULL DEFAULT 1 CHECK (authority_epoch >= 1),
    capabilities_json TEXT NOT NULL
        CHECK (
            json_valid(capabilities_json)
            AND json_type(capabilities_json) = 'array'
            AND length(capabilities_json) <= 4096
        ),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE (user_id, tenant_id),
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT
) STRICT;

-- A single unambiguous legacy owner is safe to adopt. If an old database
-- contains several owner roles, migration deliberately grants nobody and the
-- trusted bootstrap command must select the platform authority explicitly.
INSERT INTO platform_authority_grants (
    authority_id,
    user_id,
    tenant_id,
    active,
    authority_epoch,
    capabilities_json,
    created_at,
    updated_at
)
SELECT
    'platform_owner',
    users.id,
    users.tenant_id,
    1,
    1,
    '["platform.admin","platform.policy.write","platform.sessions.revoke","chat.developer.request","chat.use"]',
    unixepoch(),
    unixepoch()
FROM users
WHERE users.role = 'owner'
  AND (SELECT COUNT(*) FROM users WHERE role = 'owner') = 1;

CREATE TABLE platform_tenant_policies (
    tenant_id TEXT PRIMARY KEY,
    lifecycle_status TEXT NOT NULL DEFAULT 'active'
        CHECK (lifecycle_status IN ('active', 'suspended')),
    plan_code TEXT NOT NULL DEFAULT 'legacy'
        CHECK (
            length(plan_code) BETWEEN 1 AND 48
            AND plan_code NOT GLOB '*[^a-z0-9._-]*'
        ),
    user_limit INTEGER
        CHECK (user_limit IS NULL OR user_limit BETWEEN 1 AND 1000000),
    monthly_run_limit INTEGER
        CHECK (
            monthly_run_limit IS NULL
            OR monthly_run_limit BETWEEN 0 AND 1000000000
        ),
    developer_access_enabled INTEGER NOT NULL DEFAULT 0
        CHECK (developer_access_enabled IN (0, 1)),
    allowed_model_ids_json TEXT
        CHECK (
            allowed_model_ids_json IS NULL
            OR (
                json_valid(allowed_model_ids_json)
                AND json_type(allowed_model_ids_json) = 'array'
                AND length(allowed_model_ids_json) <= 32768
            )
        ),
    allowed_provider_ids_json TEXT
        CHECK (
            allowed_provider_ids_json IS NULL
            OR (
                json_valid(allowed_provider_ids_json)
                AND json_type(allowed_provider_ids_json) = 'array'
                AND length(allowed_provider_ids_json) <= 32768
            )
        ),
    block_reason TEXT
        CHECK (block_reason IS NULL OR length(block_reason) BETWEEN 1 AND 500),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    updated_by_user_id TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT
) STRICT;

INSERT INTO platform_tenant_policies (
    tenant_id,
    lifecycle_status,
    plan_code,
    user_limit,
    monthly_run_limit,
    developer_access_enabled,
    allowed_model_ids_json,
    allowed_provider_ids_json,
    block_reason,
    revision,
    created_at,
    updated_at,
    updated_by_user_id
)
SELECT
    tenant.id,
    'active',
    'legacy',
    NULL,
    NULL,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM platform_authority_grants AS authority
            WHERE authority.tenant_id = tenant.id
              AND authority.active = 1
        )
        THEN 1
        ELSE 0
    END,
    NULL,
    NULL,
    NULL,
    1,
    unixepoch(),
    unixepoch(),
    (
        SELECT authority.user_id
        FROM platform_authority_grants AS authority
        WHERE authority.tenant_id = tenant.id
          AND authority.active = 1
        LIMIT 1
    )
FROM tenants AS tenant;

CREATE TRIGGER platform_tenant_policy_after_insert
AFTER INSERT ON tenants
BEGIN
    INSERT INTO platform_tenant_policies (
        tenant_id,
        lifecycle_status,
        plan_code,
        developer_access_enabled,
        revision,
        created_at,
        updated_at
    ) VALUES (
        NEW.id,
        'active',
        'legacy',
        0,
        1,
        unixepoch(),
        unixepoch()
    );
END;

CREATE TABLE platform_user_controls (
    user_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    access_status TEXT NOT NULL DEFAULT 'active'
        CHECK (access_status IN ('active', 'blocked')),
    developer_access TEXT NOT NULL DEFAULT 'inherit'
        CHECK (developer_access IN ('inherit', 'allow', 'deny')),
    block_reason TEXT
        CHECK (block_reason IS NULL OR length(block_reason) BETWEEN 1 AND 500),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    updated_by_user_id TEXT,
    UNIQUE (user_id, tenant_id),
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE CASCADE
) STRICT;

INSERT INTO platform_user_controls (
    user_id,
    tenant_id,
    access_status,
    developer_access,
    block_reason,
    revision,
    created_at,
    updated_at,
    updated_by_user_id
)
SELECT
    users.id,
    users.tenant_id,
    'active',
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM platform_authority_grants AS authority
            WHERE authority.user_id = users.id
              AND authority.tenant_id = users.tenant_id
              AND authority.active = 1
        )
        THEN 'allow'
        ELSE 'inherit'
    END,
    NULL,
    1,
    unixepoch(),
    unixepoch(),
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM platform_authority_grants AS authority
            WHERE authority.user_id = users.id
              AND authority.tenant_id = users.tenant_id
              AND authority.active = 1
        )
        THEN users.id
        ELSE NULL
    END
FROM users;

CREATE INDEX ix_platform_user_controls_tenant_status
    ON platform_user_controls (tenant_id, access_status, user_id);

CREATE TRIGGER platform_user_control_after_insert
AFTER INSERT ON users
BEGIN
    INSERT INTO platform_user_controls (
        user_id,
        tenant_id,
        access_status,
        developer_access,
        revision,
        created_at,
        updated_at
    ) VALUES (
        NEW.id,
        NEW.tenant_id,
        'active',
        'inherit',
        1,
        unixepoch(),
        unixepoch()
    );
END;

CREATE TABLE platform_admin_audit_events (
    id TEXT PRIMARY KEY,
    actor_user_id TEXT NOT NULL,
    actor_tenant_id TEXT NOT NULL,
    action TEXT NOT NULL
        CHECK (length(action) BETWEEN 3 AND 120),
    target_type TEXT NOT NULL
        CHECK (target_type IN ('tenant', 'user', 'sessions', 'policy')),
    target_id TEXT NOT NULL CHECK (length(target_id) BETWEEN 1 AND 160),
    target_tenant_id TEXT NOT NULL,
    before_json TEXT NOT NULL
        CHECK (json_valid(before_json) AND length(before_json) <= 65536),
    after_json TEXT NOT NULL
        CHECK (json_valid(after_json) AND length(after_json) <= 65536),
    created_at INTEGER NOT NULL,
    FOREIGN KEY (actor_user_id, actor_tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT,
    FOREIGN KEY (target_tenant_id)
        REFERENCES tenants(id) ON DELETE RESTRICT
) STRICT;

CREATE INDEX ix_platform_admin_audit_created
    ON platform_admin_audit_events (created_at DESC, id DESC);

CREATE INDEX ix_platform_admin_audit_target
    ON platform_admin_audit_events (
        target_tenant_id,
        target_type,
        target_id,
        created_at DESC
    );

ALTER TABLE chat_run_execution_contexts
    ADD COLUMN execution_plane TEXT NOT NULL DEFAULT 'home'
        CHECK (execution_plane IN ('direct', 'home'));

ALTER TABLE chat_run_execution_contexts
    ADD COLUMN platform_authority_epoch INTEGER
        CHECK (
            platform_authority_epoch IS NULL
            OR platform_authority_epoch >= 1
        );

UPDATE chat_run_execution_contexts AS context
SET execution_plane = 'direct'
WHERE NOT EXISTS (
    SELECT 1
    FROM product_run_outbox AS outbox
    WHERE outbox.tenant_id = context.tenant_id
      AND outbox.run_id = context.run_id
);

UPDATE chat_run_execution_contexts AS context
SET platform_authority_epoch = (
    SELECT authority.authority_epoch
    FROM platform_authority_grants AS authority
    WHERE authority.authority_id = 'platform_owner'
      AND authority.user_id = context.authority_user_id
      AND authority.tenant_id = context.tenant_id
      AND authority.active = 1
)
WHERE context.execution_mode = 'developer';

PRAGMA user_version = 33;

COMMIT;
