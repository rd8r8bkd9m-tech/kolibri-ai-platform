BEGIN IMMEDIATE;

-- Storage maintenance is a separate, explicit authority. A legacy tenant
-- owner role never receives it. Existing active platform owners are upgraded
-- only when they already hold the platform-admin capability.
UPDATE platform_authority_grants
SET capabilities_json = json_insert(
        capabilities_json,
        '$[#]',
        'platform.storage.manage'
    ),
    updated_at = unixepoch()
WHERE authority_id = 'platform_owner'
  AND active = 1
  AND json_array_length(capabilities_json) < 32
  AND EXISTS (
      SELECT 1
      FROM json_each(platform_authority_grants.capabilities_json)
      WHERE value = 'platform.admin'
  )
  AND NOT EXISTS (
      SELECT 1
      FROM json_each(platform_authority_grants.capabilities_json)
      WHERE value = 'platform.storage.manage'
  );

CREATE TABLE IF NOT EXISTS storage_admin_previews (
    id TEXT PRIMARY KEY
        CHECK (id GLOB 'spv_[0-9a-f]*' AND length(id) = 36),
    actor_user_id TEXT NOT NULL,
    actor_tenant_id TEXT NOT NULL,
    authority_epoch INTEGER NOT NULL CHECK (authority_epoch >= 1),
    idempotency_key_hash TEXT NOT NULL
        CHECK (length(idempotency_key_hash) = 64),
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    node_id TEXT NOT NULL CHECK (node_id IN ('home', 'primary')),
    category TEXT NOT NULL CHECK (
        category IN (
            'build',
            'cache',
            'log',
            'stopped-container',
            'project-quarantine'
        )
    ),
    operation_kind TEXT NOT NULL CHECK (
        operation_kind IN ('cleanup', 'quarantine', 'purge')
    ),
    project_id TEXT CHECK (
        project_id IS NULL
        OR (
            length(project_id) BETWEEN 3 AND 160
            AND project_id NOT GLOB '*[^A-Za-z0-9._~-]*'
        )
    ),
    quarantine_id TEXT CHECK (
        quarantine_id IS NULL
        OR (
            quarantine_id GLOB 'sqn_[0-9a-f]*'
            AND length(quarantine_id) = 36
        )
    ),
    executor_preview_ref TEXT NOT NULL
        CHECK (length(executor_preview_ref) BETWEEN 3 AND 192),
    node_generation TEXT NOT NULL
        CHECK (length(node_generation) BETWEEN 1 AND 128),
    candidate_count INTEGER NOT NULL
        CHECK (candidate_count BETWEEN 0 AND 1000000000),
    reclaimable_bytes INTEGER NOT NULL
        CHECK (reclaimable_bytes BETWEEN 0 AND 9223372036854775807),
    protected_item_count INTEGER NOT NULL DEFAULT 0
        CHECK (protected_item_count = 0),
    protected_scopes_json TEXT NOT NULL CHECK (
        json_valid(protected_scopes_json)
        AND json_type(protected_scopes_json) = 'array'
        AND length(protected_scopes_json) <= 2048
    ),
    expires_at INTEGER NOT NULL,
    consumed_at INTEGER,
    created_at INTEGER NOT NULL,
    UNIQUE (actor_user_id, actor_tenant_id, idempotency_key_hash),
    CHECK (
        (
            operation_kind = 'cleanup'
            AND category IN ('build', 'cache', 'log', 'stopped-container')
            AND project_id IS NULL
            AND quarantine_id IS NULL
        )
        OR (
            operation_kind = 'quarantine'
            AND category = 'project-quarantine'
            AND project_id IS NOT NULL
            AND quarantine_id IS NULL
        )
        OR (
            operation_kind = 'purge'
            AND category = 'project-quarantine'
            AND project_id IS NULL
            AND quarantine_id IS NOT NULL
        )
    ),
    FOREIGN KEY (actor_user_id, actor_tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT
) STRICT;

CREATE INDEX IF NOT EXISTS ix_storage_admin_previews_expiry
    ON storage_admin_previews (expires_at, id);

CREATE TABLE IF NOT EXISTS storage_admin_operations (
    id TEXT PRIMARY KEY
        CHECK (id GLOB 'sop_[0-9a-f]*' AND length(id) = 36),
    preview_id TEXT NOT NULL UNIQUE,
    actor_user_id TEXT NOT NULL,
    actor_tenant_id TEXT NOT NULL,
    authority_epoch INTEGER NOT NULL CHECK (authority_epoch >= 1),
    idempotency_key_hash TEXT NOT NULL
        CHECK (length(idempotency_key_hash) = 64),
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    status TEXT NOT NULL CHECK (status IN ('pending', 'succeeded', 'failed')),
    affected_item_count INTEGER NOT NULL DEFAULT 0
        CHECK (affected_item_count BETWEEN 0 AND 1000000000),
    reclaimed_bytes INTEGER NOT NULL DEFAULT 0
        CHECK (reclaimed_bytes BETWEEN 0 AND 9223372036854775807),
    quarantine_id TEXT CHECK (
        quarantine_id IS NULL
        OR (
            quarantine_id GLOB 'sqn_[0-9a-f]*'
            AND length(quarantine_id) = 36
        )
    ),
    purge_eligible_at INTEGER,
    error_code TEXT CHECK (
        error_code IS NULL OR length(error_code) BETWEEN 3 AND 128
    ),
    created_at INTEGER NOT NULL,
    completed_at INTEGER,
    UNIQUE (actor_user_id, actor_tenant_id, idempotency_key_hash),
    FOREIGN KEY (preview_id)
        REFERENCES storage_admin_previews(id) ON DELETE RESTRICT,
    FOREIGN KEY (actor_user_id, actor_tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT
) STRICT;

CREATE INDEX IF NOT EXISTS ix_storage_admin_operations_recent
    ON storage_admin_operations (created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS storage_project_quarantines (
    id TEXT PRIMARY KEY
        CHECK (id GLOB 'sqn_[0-9a-f]*' AND length(id) = 36),
    node_id TEXT NOT NULL CHECK (node_id IN ('home', 'primary')),
    project_id TEXT NOT NULL CHECK (
        length(project_id) BETWEEN 3 AND 160
        AND project_id NOT GLOB '*[^A-Za-z0-9._~-]*'
    ),
    status TEXT NOT NULL CHECK (status IN ('retained', 'purged')),
    size_bytes INTEGER NOT NULL
        CHECK (size_bytes BETWEEN 0 AND 9223372036854775807),
    quarantined_operation_id TEXT NOT NULL UNIQUE,
    quarantined_at INTEGER NOT NULL,
    purge_eligible_at INTEGER NOT NULL,
    purged_operation_id TEXT UNIQUE,
    purged_at INTEGER,
    CHECK (
        (
            status = 'retained'
            AND purged_operation_id IS NULL
            AND purged_at IS NULL
        )
        OR (
            status = 'purged'
            AND purged_operation_id IS NOT NULL
            AND purged_at IS NOT NULL
        )
    ),
    FOREIGN KEY (quarantined_operation_id)
        REFERENCES storage_admin_operations(id) ON DELETE RESTRICT,
    FOREIGN KEY (purged_operation_id)
        REFERENCES storage_admin_operations(id) ON DELETE RESTRICT
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS ux_storage_project_quarantine_retained_project
    ON storage_project_quarantines (node_id, project_id)
    WHERE status = 'retained';

CREATE INDEX IF NOT EXISTS ix_storage_project_quarantine_retention
    ON storage_project_quarantines (
        status,
        purge_eligible_at,
        node_id,
        id
    );

CREATE TABLE IF NOT EXISTS storage_admin_audit_events (
    id TEXT PRIMARY KEY
        CHECK (id GLOB 'saudit_[0-9a-f]*' AND length(id) = 39),
    actor_user_id TEXT NOT NULL,
    actor_tenant_id TEXT NOT NULL,
    authority_epoch INTEGER NOT NULL CHECK (authority_epoch >= 1),
    action TEXT NOT NULL CHECK (
        action IN (
            'storage.preview.created',
            'storage.operation.succeeded',
            'storage.operation.failed'
        )
    ),
    node_id TEXT NOT NULL CHECK (node_id IN ('home', 'primary')),
    category TEXT NOT NULL CHECK (
        category IN (
            'build',
            'cache',
            'log',
            'stopped-container',
            'project-quarantine'
        )
    ),
    operation_kind TEXT NOT NULL CHECK (
        operation_kind IN ('cleanup', 'quarantine', 'purge')
    ),
    target_ref TEXT NOT NULL CHECK (
        length(target_ref) BETWEEN 1 AND 160
        AND target_ref NOT GLOB '*[^A-Za-z0-9._~-]*'
    ),
    preview_id TEXT NOT NULL,
    operation_id TEXT,
    details_json TEXT NOT NULL CHECK (
        json_valid(details_json)
        AND json_type(details_json) = 'object'
        AND length(details_json) <= 8192
    ),
    created_at INTEGER NOT NULL,
    FOREIGN KEY (actor_user_id, actor_tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT,
    FOREIGN KEY (preview_id)
        REFERENCES storage_admin_previews(id) ON DELETE RESTRICT,
    FOREIGN KEY (operation_id)
        REFERENCES storage_admin_operations(id) ON DELETE RESTRICT
) STRICT;

CREATE INDEX IF NOT EXISTS ix_storage_admin_audit_recent
    ON storage_admin_audit_events (created_at DESC, id DESC);

PRAGMA user_version = 42;

COMMIT;
