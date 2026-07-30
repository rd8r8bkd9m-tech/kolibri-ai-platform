BEGIN IMMEDIATE;

-- R1 has one server-derived platform owner. This composite key lets every
-- durable trusted-agent record bind to that exact subject and epoch instead
-- of trusting a tenant role copied into an API request.
CREATE UNIQUE INDEX uq_platform_authority_grants_subject
    ON platform_authority_grants (authority_id, user_id, tenant_id);

CREATE TABLE trusted_agent_workspace_bindings (
    id TEXT PRIMARY KEY
        CHECK (
            length(id) = 36
            AND substr(id, 1, 4) = 'wsb_'
            AND substr(id, 5) NOT GLOB '*[^0-9a-f]*'
        ),
    authority_id TEXT NOT NULL DEFAULT 'platform_owner'
        CHECK (authority_id = 'platform_owner'),
    owner_user_id TEXT NOT NULL,
    owner_tenant_id TEXT NOT NULL,
    authority_epoch INTEGER NOT NULL CHECK (authority_epoch >= 1),
    server_ref TEXT NOT NULL UNIQUE
        CHECK (
            length(server_ref) = 38
            AND substr(server_ref, 1, 6) = 'wsref_'
            AND substr(server_ref, 7) NOT GLOB '*[^0-9a-f]*'
        ),
    environment TEXT NOT NULL
        CHECK (environment IN ('development', 'staging', 'production')),
    fingerprint_token TEXT NOT NULL
        CHECK (
            length(fingerprint_token) = 71
            AND substr(fingerprint_token, 1, 7) = 'sha256:'
            AND substr(fingerprint_token, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    lifecycle_status TEXT NOT NULL DEFAULT 'active'
        CHECK (lifecycle_status IN ('active', 'revoked')),
    workspace_epoch INTEGER NOT NULL DEFAULT 1
        CHECK (workspace_epoch >= 1),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    created_by_user_id TEXT NOT NULL,
    revoked_at INTEGER,
    revoked_by_user_id TEXT,
    CHECK (updated_at >= created_at),
    CHECK (
        (
            lifecycle_status = 'active'
            AND revoked_at IS NULL
            AND revoked_by_user_id IS NULL
        )
        OR (
            lifecycle_status = 'revoked'
            AND revoked_at IS NOT NULL
            AND revoked_at >= created_at
            AND revoked_by_user_id IS NOT NULL
        )
    ),
    FOREIGN KEY (authority_id, owner_user_id, owner_tenant_id)
        REFERENCES platform_authority_grants(
            authority_id,
            user_id,
            tenant_id
        ) ON DELETE RESTRICT,
    FOREIGN KEY (owner_user_id, owner_tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT,
    FOREIGN KEY (created_by_user_id, owner_tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT,
    FOREIGN KEY (revoked_by_user_id, owner_tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT
) STRICT;

CREATE UNIQUE INDEX uq_r1_active_trusted_workspace
    ON trusted_agent_workspace_bindings (authority_id)
    WHERE lifecycle_status = 'active';

CREATE INDEX ix_trusted_workspace_owner_history
    ON trusted_agent_workspace_bindings (
        owner_tenant_id,
        owner_user_id,
        created_at DESC,
        id DESC
    );

CREATE TRIGGER trusted_workspace_authority_before_insert
BEFORE INSERT ON trusted_agent_workspace_bindings
WHEN NOT EXISTS (
    SELECT 1
    FROM platform_authority_grants AS authority
    WHERE authority.authority_id = NEW.authority_id
      AND authority.user_id = NEW.owner_user_id
      AND authority.tenant_id = NEW.owner_tenant_id
      AND authority.active = 1
      AND authority.authority_epoch = NEW.authority_epoch
      AND EXISTS (
          SELECT 1
          FROM json_each(authority.capabilities_json)
          WHERE value = 'chat.developer.request'
      )
)
BEGIN
    SELECT RAISE(ABORT, 'trusted workspace authority is not active');
END;

CREATE TRIGGER trusted_workspace_authority_before_update
BEFORE UPDATE ON trusted_agent_workspace_bindings
WHEN NOT EXISTS (
    SELECT 1
    FROM platform_authority_grants AS authority
    WHERE authority.authority_id = NEW.authority_id
      AND authority.user_id = NEW.owner_user_id
      AND authority.tenant_id = NEW.owner_tenant_id
      AND authority.active = 1
      AND authority.authority_epoch = NEW.authority_epoch
      AND EXISTS (
          SELECT 1
          FROM json_each(authority.capabilities_json)
          WHERE value = 'chat.developer.request'
      )
)
BEGIN
    SELECT RAISE(ABORT, 'trusted workspace authority is not active');
END;

CREATE TABLE trusted_agent_profiles (
    id TEXT PRIMARY KEY
        CHECK (
            length(id) = 36
            AND substr(id, 1, 4) = 'tap_'
            AND substr(id, 5) NOT GLOB '*[^0-9a-f]*'
        ),
    authority_id TEXT NOT NULL DEFAULT 'platform_owner'
        CHECK (authority_id = 'platform_owner'),
    owner_user_id TEXT NOT NULL,
    owner_tenant_id TEXT NOT NULL,
    authority_epoch INTEGER NOT NULL CHECK (authority_epoch >= 1),
    workspace_binding_id TEXT NOT NULL,
    workspace_binding_epoch INTEGER NOT NULL
        CHECK (workspace_binding_epoch >= 1),
    display_name TEXT NOT NULL CHECK (length(display_name) BETWEEN 1 AND 120),
    runtime_profile TEXT NOT NULL
        CHECK (
            length(runtime_profile) BETWEEN 2 AND 96
            AND substr(runtime_profile, 1, 1) GLOB '[a-z0-9]'
            AND runtime_profile NOT GLOB '*[^a-z0-9._-]*'
        ),
    agent_card_id TEXT NOT NULL
        CHECK (
            length(agent_card_id) BETWEEN 3 AND 128
            AND substr(agent_card_id, 1, 1) GLOB '[a-z0-9]'
            AND agent_card_id NOT GLOB '*[^a-z0-9._-]*'
        ),
    agent_card_version INTEGER NOT NULL CHECK (agent_card_version >= 1),
    capabilities_json TEXT NOT NULL
        DEFAULT '["developer.runtime.execute"]'
        CHECK (capabilities_json = '["developer.runtime.execute"]'),
    tool_policy_id TEXT NOT NULL DEFAULT 'developer.full.v1'
        CHECK (tool_policy_id = 'developer.full.v1'),
    access_mode TEXT NOT NULL DEFAULT 'full'
        CHECK (access_mode = 'full'),
    sandbox_profile TEXT NOT NULL DEFAULT 'danger-full-access'
        CHECK (sandbox_profile = 'danger-full-access'),
    approval_policy TEXT NOT NULL DEFAULT 'never'
        CHECK (approval_policy = 'never'),
    approvals_reviewer TEXT DEFAULT NULL
        CHECK (approvals_reviewer IS NULL),
    max_concurrency INTEGER NOT NULL DEFAULT 1
        CHECK (max_concurrency = 1),
    lifecycle_status TEXT NOT NULL DEFAULT 'active'
        CHECK (lifecycle_status IN ('active', 'revoked')),
    profile_epoch INTEGER NOT NULL DEFAULT 1 CHECK (profile_epoch >= 1),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    created_by_user_id TEXT NOT NULL,
    revoked_at INTEGER,
    revoked_by_user_id TEXT,
    CHECK (updated_at >= created_at),
    CHECK (
        (
            lifecycle_status = 'active'
            AND revoked_at IS NULL
            AND revoked_by_user_id IS NULL
        )
        OR (
            lifecycle_status = 'revoked'
            AND revoked_at IS NOT NULL
            AND revoked_at >= created_at
            AND revoked_by_user_id IS NOT NULL
        )
    ),
    FOREIGN KEY (authority_id, owner_user_id, owner_tenant_id)
        REFERENCES platform_authority_grants(
            authority_id,
            user_id,
            tenant_id
        ) ON DELETE RESTRICT,
    FOREIGN KEY (owner_user_id, owner_tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_binding_id)
        REFERENCES trusted_agent_workspace_bindings(id) ON DELETE RESTRICT,
    FOREIGN KEY (created_by_user_id, owner_tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT,
    FOREIGN KEY (revoked_by_user_id, owner_tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT
) STRICT;

CREATE UNIQUE INDEX uq_r1_active_trusted_agent_profile
    ON trusted_agent_profiles (authority_id)
    WHERE lifecycle_status = 'active';

CREATE UNIQUE INDEX uq_r1_active_profile_per_workspace
    ON trusted_agent_profiles (workspace_binding_id)
    WHERE lifecycle_status = 'active';

CREATE INDEX ix_trusted_profile_owner_history
    ON trusted_agent_profiles (
        owner_tenant_id,
        owner_user_id,
        created_at DESC,
        id DESC
    );

CREATE TRIGGER trusted_profile_authority_before_insert
BEFORE INSERT ON trusted_agent_profiles
WHEN NOT EXISTS (
    SELECT 1
    FROM platform_authority_grants AS authority
    WHERE authority.authority_id = NEW.authority_id
      AND authority.user_id = NEW.owner_user_id
      AND authority.tenant_id = NEW.owner_tenant_id
      AND authority.active = 1
      AND authority.authority_epoch = NEW.authority_epoch
      AND EXISTS (
          SELECT 1
          FROM json_each(authority.capabilities_json)
          WHERE value = 'chat.developer.request'
      )
)
BEGIN
    SELECT RAISE(ABORT, 'trusted agent authority is not active');
END;

CREATE TRIGGER trusted_profile_authority_before_update
BEFORE UPDATE ON trusted_agent_profiles
WHEN NOT EXISTS (
    SELECT 1
    FROM platform_authority_grants AS authority
    WHERE authority.authority_id = NEW.authority_id
      AND authority.user_id = NEW.owner_user_id
      AND authority.tenant_id = NEW.owner_tenant_id
      AND authority.active = 1
      AND authority.authority_epoch = NEW.authority_epoch
      AND EXISTS (
          SELECT 1
          FROM json_each(authority.capabilities_json)
          WHERE value = 'chat.developer.request'
      )
)
BEGIN
    SELECT RAISE(ABORT, 'trusted agent authority is not active');
END;

CREATE TRIGGER trusted_profile_workspace_before_insert
BEFORE INSERT ON trusted_agent_profiles
WHEN NEW.lifecycle_status = 'active'
 AND NOT EXISTS (
    SELECT 1
    FROM trusted_agent_workspace_bindings AS binding
    WHERE binding.id = NEW.workspace_binding_id
      AND binding.authority_id = NEW.authority_id
      AND binding.owner_user_id = NEW.owner_user_id
      AND binding.owner_tenant_id = NEW.owner_tenant_id
      AND binding.authority_epoch = NEW.authority_epoch
      AND binding.workspace_epoch = NEW.workspace_binding_epoch
      AND binding.lifecycle_status = 'active'
)
BEGIN
    SELECT RAISE(ABORT, 'trusted agent workspace binding is not active');
END;

CREATE TRIGGER trusted_profile_workspace_before_update
BEFORE UPDATE ON trusted_agent_profiles
WHEN NEW.lifecycle_status = 'active'
 AND NOT EXISTS (
    SELECT 1
    FROM trusted_agent_workspace_bindings AS binding
    WHERE binding.id = NEW.workspace_binding_id
      AND binding.authority_id = NEW.authority_id
      AND binding.owner_user_id = NEW.owner_user_id
      AND binding.owner_tenant_id = NEW.owner_tenant_id
      AND binding.authority_epoch = NEW.authority_epoch
      AND binding.workspace_epoch = NEW.workspace_binding_epoch
      AND binding.lifecycle_status = 'active'
)
BEGIN
    SELECT RAISE(ABORT, 'trusted agent workspace binding is not active');
END;

-- Execution integration lands in migration 036. The lease table exists here
-- so that
-- R1 concurrency is a database invariant, not an in-process convention.
CREATE TABLE trusted_agent_workspace_leases (
    id TEXT PRIMARY KEY
        CHECK (
            length(id) = 36
            AND substr(id, 1, 4) = 'tal_'
            AND substr(id, 5) NOT GLOB '*[^0-9a-f]*'
        ),
    authority_id TEXT NOT NULL DEFAULT 'platform_owner'
        CHECK (authority_id = 'platform_owner'),
    owner_user_id TEXT NOT NULL,
    owner_tenant_id TEXT NOT NULL,
    authority_epoch INTEGER NOT NULL CHECK (authority_epoch >= 1),
    profile_id TEXT NOT NULL,
    profile_epoch INTEGER NOT NULL CHECK (profile_epoch >= 1),
    workspace_binding_id TEXT NOT NULL,
    workspace_binding_epoch INTEGER NOT NULL
        CHECK (workspace_binding_epoch >= 1),
    state TEXT NOT NULL DEFAULT 'active'
        CHECK (state IN ('active', 'released', 'revoked', 'expired')),
    fencing_token INTEGER NOT NULL CHECK (fencing_token >= 1),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    terminal_at INTEGER,
    CHECK (updated_at >= created_at),
    CHECK (expires_at > created_at),
    CHECK (
        (state = 'active' AND terminal_at IS NULL)
        OR (
            state != 'active'
            AND terminal_at IS NOT NULL
            AND terminal_at >= created_at
        )
    ),
    FOREIGN KEY (authority_id, owner_user_id, owner_tenant_id)
        REFERENCES platform_authority_grants(
            authority_id,
            user_id,
            tenant_id
        ) ON DELETE RESTRICT,
    FOREIGN KEY (owner_user_id, owner_tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT,
    FOREIGN KEY (profile_id)
        REFERENCES trusted_agent_profiles(id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_binding_id)
        REFERENCES trusted_agent_workspace_bindings(id) ON DELETE RESTRICT
) STRICT;

CREATE UNIQUE INDEX uq_r1_active_lease_per_profile
    ON trusted_agent_workspace_leases (profile_id)
    WHERE state = 'active';

CREATE UNIQUE INDEX uq_r1_active_lease_per_workspace
    ON trusted_agent_workspace_leases (workspace_binding_id)
    WHERE state = 'active';

CREATE UNIQUE INDEX uq_trusted_agent_lease_fencing
    ON trusted_agent_workspace_leases (
        workspace_binding_id,
        fencing_token
    );

CREATE INDEX ix_trusted_agent_lease_expiry
    ON trusted_agent_workspace_leases (state, expires_at, id);

CREATE TRIGGER trusted_lease_scope_before_insert
BEFORE INSERT ON trusted_agent_workspace_leases
WHEN NEW.state = 'active'
 AND (
    NOT EXISTS (
        SELECT 1
        FROM platform_authority_grants AS authority
        WHERE authority.authority_id = NEW.authority_id
          AND authority.user_id = NEW.owner_user_id
          AND authority.tenant_id = NEW.owner_tenant_id
          AND authority.active = 1
          AND authority.authority_epoch = NEW.authority_epoch
          AND EXISTS (
              SELECT 1
              FROM json_each(authority.capabilities_json)
              WHERE value = 'chat.developer.request'
          )
    )
    OR NOT EXISTS (
        SELECT 1
        FROM trusted_agent_profiles AS profile
        WHERE profile.id = NEW.profile_id
          AND profile.authority_id = NEW.authority_id
          AND profile.owner_user_id = NEW.owner_user_id
          AND profile.owner_tenant_id = NEW.owner_tenant_id
          AND profile.authority_epoch = NEW.authority_epoch
          AND profile.profile_epoch = NEW.profile_epoch
          AND profile.workspace_binding_id = NEW.workspace_binding_id
          AND profile.workspace_binding_epoch = NEW.workspace_binding_epoch
          AND profile.lifecycle_status = 'active'
    )
    OR NOT EXISTS (
        SELECT 1
        FROM trusted_agent_workspace_bindings AS binding
        WHERE binding.id = NEW.workspace_binding_id
          AND binding.authority_id = NEW.authority_id
          AND binding.owner_user_id = NEW.owner_user_id
          AND binding.owner_tenant_id = NEW.owner_tenant_id
          AND binding.authority_epoch = NEW.authority_epoch
          AND binding.workspace_epoch = NEW.workspace_binding_epoch
          AND binding.lifecycle_status = 'active'
    )
)
BEGIN
    SELECT RAISE(ABORT, 'trusted agent lease scope is not active');
END;

CREATE TRIGGER trusted_lease_scope_before_update
BEFORE UPDATE ON trusted_agent_workspace_leases
WHEN NEW.state = 'active'
 AND (
    NOT EXISTS (
        SELECT 1
        FROM platform_authority_grants AS authority
        WHERE authority.authority_id = NEW.authority_id
          AND authority.user_id = NEW.owner_user_id
          AND authority.tenant_id = NEW.owner_tenant_id
          AND authority.active = 1
          AND authority.authority_epoch = NEW.authority_epoch
          AND EXISTS (
              SELECT 1
              FROM json_each(authority.capabilities_json)
              WHERE value = 'chat.developer.request'
          )
    )
    OR NOT EXISTS (
        SELECT 1
        FROM trusted_agent_profiles AS profile
        WHERE profile.id = NEW.profile_id
          AND profile.authority_id = NEW.authority_id
          AND profile.owner_user_id = NEW.owner_user_id
          AND profile.owner_tenant_id = NEW.owner_tenant_id
          AND profile.authority_epoch = NEW.authority_epoch
          AND profile.profile_epoch = NEW.profile_epoch
          AND profile.workspace_binding_id = NEW.workspace_binding_id
          AND profile.workspace_binding_epoch = NEW.workspace_binding_epoch
          AND profile.lifecycle_status = 'active'
    )
    OR NOT EXISTS (
        SELECT 1
        FROM trusted_agent_workspace_bindings AS binding
        WHERE binding.id = NEW.workspace_binding_id
          AND binding.authority_id = NEW.authority_id
          AND binding.owner_user_id = NEW.owner_user_id
          AND binding.owner_tenant_id = NEW.owner_tenant_id
          AND binding.authority_epoch = NEW.authority_epoch
          AND binding.workspace_epoch = NEW.workspace_binding_epoch
          AND binding.lifecycle_status = 'active'
    )
)
BEGIN
    SELECT RAISE(ABORT, 'trusted agent lease scope is not active');
END;

CREATE TABLE trusted_agent_audit_events (
    id TEXT PRIMARY KEY
        CHECK (
            length(id) = 39
            AND substr(id, 1, 7) = 'taudit_'
            AND substr(id, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    actor_user_id TEXT NOT NULL,
    actor_tenant_id TEXT NOT NULL,
    authority_epoch INTEGER NOT NULL CHECK (authority_epoch >= 1),
    authorization_decision_id TEXT NOT NULL
        CHECK (
            length(authorization_decision_id) = 41
            AND substr(authorization_decision_id, 1, 9) = 'decision_'
            AND substr(authorization_decision_id, 10)
                NOT GLOB '*[^0-9a-f]*'
        ),
    action TEXT NOT NULL
        CHECK (
            action IN (
                'binding.created',
                'binding.updated',
                'binding.revoked',
                'profile.created',
                'profile.updated',
                'profile.revoked',
                'profile.revoked_by_binding'
            )
        ),
    target_type TEXT NOT NULL CHECK (target_type IN ('binding', 'profile')),
    target_id TEXT NOT NULL CHECK (length(target_id) = 36),
    target_revision INTEGER NOT NULL CHECK (target_revision >= 1),
    target_epoch INTEGER NOT NULL CHECK (target_epoch >= 1),
    before_json TEXT NOT NULL
        CHECK (
            json_valid(before_json)
            AND json_type(before_json) = 'object'
            AND length(before_json) <= 65536
        ),
    after_json TEXT NOT NULL
        CHECK (
            json_valid(after_json)
            AND json_type(after_json) = 'object'
            AND length(after_json) <= 65536
        ),
    created_at INTEGER NOT NULL,
    FOREIGN KEY (actor_user_id, actor_tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT
) STRICT;

CREATE INDEX ix_trusted_agent_audit_created
    ON trusted_agent_audit_events (created_at DESC, id DESC);

CREATE INDEX ix_trusted_agent_audit_target
    ON trusted_agent_audit_events (
        target_type,
        target_id,
        created_at DESC,
        id DESC
    );

CREATE TRIGGER trusted_agent_audit_append_only_update
BEFORE UPDATE ON trusted_agent_audit_events
BEGIN
    SELECT RAISE(ABORT, 'trusted-agent audit is append-only');
END;

CREATE TRIGGER trusted_agent_audit_append_only_delete
BEFORE DELETE ON trusted_agent_audit_events
BEGIN
    SELECT RAISE(ABORT, 'trusted-agent audit is append-only');
END;

PRAGMA user_version = 34;

COMMIT;
