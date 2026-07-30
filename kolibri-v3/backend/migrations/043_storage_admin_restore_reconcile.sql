PRAGMA foreign_keys = OFF;

BEGIN IMMEDIATE;

-- Rebuild the four storage control-plane tables so restore is a first-class
-- typed operation. Existing v42 data is copied unchanged; reconciliation
-- metadata starts empty.
CREATE TABLE storage_admin_previews_v43 (
    id TEXT PRIMARY KEY
        CHECK (
            length(id) = 36
            AND substr(id, 1, 4) = 'spv_'
            AND substr(id, 5) NOT GLOB '*[^0-9a-f]*'
        ),
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
        operation_kind IN ('cleanup', 'quarantine', 'restore', 'purge')
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
            length(quarantine_id) = 36
            AND substr(quarantine_id, 1, 4) = 'sqn_'
            AND substr(quarantine_id, 5) NOT GLOB '*[^0-9a-f]*'
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
            operation_kind IN ('restore', 'purge')
            AND category = 'project-quarantine'
            AND project_id IS NULL
            AND quarantine_id IS NOT NULL
        )
    ),
    FOREIGN KEY (actor_user_id, actor_tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT
) STRICT;

INSERT INTO storage_admin_previews_v43
SELECT * FROM storage_admin_previews;

CREATE TABLE storage_admin_operations_v43 (
    id TEXT PRIMARY KEY
        CHECK (
            length(id) = 36
            AND substr(id, 1, 4) = 'sop_'
            AND substr(id, 5) NOT GLOB '*[^0-9a-f]*'
        ),
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
            length(quarantine_id) = 36
            AND substr(quarantine_id, 1, 4) = 'sqn_'
            AND substr(quarantine_id, 5) NOT GLOB '*[^0-9a-f]*'
        )
    ),
    purge_eligible_at INTEGER,
    error_code TEXT CHECK (
        error_code IS NULL OR length(error_code) BETWEEN 3 AND 128
    ),
    reconcile_attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (reconcile_attempt_count BETWEEN 0 AND 1000000000),
    reconcile_attempted_at INTEGER,
    created_at INTEGER NOT NULL,
    completed_at INTEGER,
    UNIQUE (actor_user_id, actor_tenant_id, idempotency_key_hash),
    FOREIGN KEY (preview_id)
        REFERENCES storage_admin_previews(id) ON DELETE RESTRICT,
    FOREIGN KEY (actor_user_id, actor_tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT
) STRICT;

INSERT INTO storage_admin_operations_v43 (
    id, preview_id, actor_user_id, actor_tenant_id, authority_epoch,
    idempotency_key_hash, request_hash, status, affected_item_count,
    reclaimed_bytes, quarantine_id, purge_eligible_at, error_code,
    reconcile_attempt_count, reconcile_attempted_at, created_at, completed_at
)
SELECT
    id, preview_id, actor_user_id, actor_tenant_id, authority_epoch,
    idempotency_key_hash, request_hash, status, affected_item_count,
    reclaimed_bytes, quarantine_id, purge_eligible_at, error_code,
    0, NULL, created_at, completed_at
FROM storage_admin_operations;

CREATE TABLE storage_project_quarantines_v43 (
    id TEXT PRIMARY KEY
        CHECK (
            length(id) = 36
            AND substr(id, 1, 4) = 'sqn_'
            AND substr(id, 5) NOT GLOB '*[^0-9a-f]*'
        ),
    node_id TEXT NOT NULL CHECK (node_id IN ('home', 'primary')),
    project_id TEXT NOT NULL CHECK (
        length(project_id) BETWEEN 3 AND 160
        AND project_id NOT GLOB '*[^A-Za-z0-9._~-]*'
    ),
    status TEXT NOT NULL CHECK (
        status IN ('retained', 'restored', 'purged')
    ),
    size_bytes INTEGER NOT NULL
        CHECK (size_bytes BETWEEN 0 AND 9223372036854775807),
    quarantined_operation_id TEXT NOT NULL UNIQUE,
    quarantined_at INTEGER NOT NULL,
    purge_eligible_at INTEGER NOT NULL,
    restored_operation_id TEXT UNIQUE,
    restored_at INTEGER,
    purged_operation_id TEXT UNIQUE,
    purged_at INTEGER,
    CHECK (
        (
            status = 'retained'
            AND restored_operation_id IS NULL
            AND restored_at IS NULL
            AND purged_operation_id IS NULL
            AND purged_at IS NULL
        )
        OR (
            status = 'restored'
            AND restored_operation_id IS NOT NULL
            AND restored_at IS NOT NULL
            AND purged_operation_id IS NULL
            AND purged_at IS NULL
        )
        OR (
            status = 'purged'
            AND restored_operation_id IS NULL
            AND restored_at IS NULL
            AND purged_operation_id IS NOT NULL
            AND purged_at IS NOT NULL
        )
    ),
    FOREIGN KEY (quarantined_operation_id)
        REFERENCES storage_admin_operations(id) ON DELETE RESTRICT,
    FOREIGN KEY (restored_operation_id)
        REFERENCES storage_admin_operations(id) ON DELETE RESTRICT,
    FOREIGN KEY (purged_operation_id)
        REFERENCES storage_admin_operations(id) ON DELETE RESTRICT
) STRICT;

INSERT INTO storage_project_quarantines_v43 (
    id, node_id, project_id, status, size_bytes,
    quarantined_operation_id, quarantined_at, purge_eligible_at,
    restored_operation_id, restored_at, purged_operation_id, purged_at
)
SELECT
    id, node_id, project_id, status, size_bytes,
    quarantined_operation_id, quarantined_at, purge_eligible_at,
    NULL, NULL, purged_operation_id, purged_at
FROM storage_project_quarantines;

CREATE TABLE storage_admin_audit_events_v43 (
    id TEXT PRIMARY KEY
        CHECK (
            length(id) = 39
            AND substr(id, 1, 7) = 'saudit_'
            AND substr(id, 8) NOT GLOB '*[^0-9a-f]*'
        ),
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
        operation_kind IN ('cleanup', 'quarantine', 'restore', 'purge')
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

INSERT INTO storage_admin_audit_events_v43
SELECT * FROM storage_admin_audit_events;

DROP TABLE storage_admin_audit_events;
DROP TABLE storage_project_quarantines;
DROP TABLE storage_admin_operations;
DROP TABLE storage_admin_previews;

ALTER TABLE storage_admin_previews_v43
    RENAME TO storage_admin_previews;
ALTER TABLE storage_admin_operations_v43
    RENAME TO storage_admin_operations;
ALTER TABLE storage_project_quarantines_v43
    RENAME TO storage_project_quarantines;
ALTER TABLE storage_admin_audit_events_v43
    RENAME TO storage_admin_audit_events;

CREATE INDEX ix_storage_admin_previews_expiry
    ON storage_admin_previews (expires_at, id);
CREATE INDEX ix_storage_admin_operations_recent
    ON storage_admin_operations (created_at DESC, id DESC);
CREATE UNIQUE INDEX ux_storage_project_quarantine_retained_project
    ON storage_project_quarantines (node_id, project_id)
    WHERE status = 'retained';
CREATE INDEX ix_storage_project_quarantine_retention
    ON storage_project_quarantines (
        status,
        purge_eligible_at,
        node_id,
        id
    );
CREATE INDEX ix_storage_admin_audit_recent
    ON storage_admin_audit_events (created_at DESC, id DESC);

PRAGMA user_version = 43;

COMMIT;

PRAGMA foreign_keys = ON;
