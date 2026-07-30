BEGIN IMMEDIATE;

-- Lease credentials are capabilities. Persist only a SHA-256 digest; the raw
-- claim token remains in the worker process and is presented at every fence.
ALTER TABLE trusted_agent_workspace_leases
    ADD COLUMN assignment_ref TEXT
        CHECK (
            assignment_ref IS NULL
            OR (
                length(assignment_ref) BETWEEN 1 AND 160
                AND substr(assignment_ref, 1, 1) GLOB '[A-Za-z0-9]'
                AND assignment_ref NOT GLOB '*[^A-Za-z0-9._~-]*'
            )
        );

ALTER TABLE trusted_agent_workspace_leases
    ADD COLUMN claim_owner TEXT
        CHECK (
            claim_owner IS NULL
            OR (
                length(claim_owner) BETWEEN 3 AND 160
                AND substr(claim_owner, 1, 1) GLOB '[A-Za-z0-9]'
                AND claim_owner NOT GLOB '*[^A-Za-z0-9._~-]*'
            )
        );

ALTER TABLE trusted_agent_workspace_leases
    ADD COLUMN claim_token_hash TEXT
        CHECK (
            claim_token_hash IS NULL
            OR (
                length(claim_token_hash) = 71
                AND substr(claim_token_hash, 1, 7) = 'sha256:'
                AND substr(claim_token_hash, 8)
                    NOT GLOB '*[^0-9a-f]*'
            )
        );

ALTER TABLE trusted_agent_workspace_leases
    ADD COLUMN last_claimed_at INTEGER
        CHECK (
            last_claimed_at IS NULL
            OR last_claimed_at >= created_at
        );

ALTER TABLE trusted_agent_workspace_leases
    ADD COLUMN terminal_reason TEXT
        CHECK (
            terminal_reason IS NULL
            OR (
                length(terminal_reason) BETWEEN 3 AND 120
                AND substr(terminal_reason, 1, 1) GLOB '[a-z]'
                AND terminal_reason NOT GLOB '*[^a-z0-9._-]*'
            )
        );

CREATE UNIQUE INDEX uq_trusted_agent_assignment_ref
    ON trusted_agent_workspace_leases (
        owner_tenant_id,
        assignment_ref
    )
    WHERE assignment_ref IS NOT NULL;

-- R1 is one trusted agent, not one agent per historical profile.  This closes
-- the gap where a stale active lease on a revoked profile could otherwise
-- coexist with a lease on its replacement profile/workspace.
CREATE UNIQUE INDEX uq_r1_single_active_trusted_agent_lease
    ON trusted_agent_workspace_leases (authority_id)
    WHERE state = 'active';

CREATE INDEX ix_trusted_agent_lease_claim
    ON trusted_agent_workspace_leases (
        state,
        claim_owner,
        expires_at,
        workspace_binding_id,
        id
    )
    WHERE assignment_ref IS NOT NULL;

CREATE TRIGGER trusted_lease_v37_active_shape_before_insert
BEFORE INSERT ON trusted_agent_workspace_leases
WHEN NEW.state = 'active'
 AND (
    NEW.assignment_ref IS NULL
    OR (
        NEW.claim_owner IS NULL
        AND (
            NEW.claim_token_hash IS NOT NULL
            OR NEW.last_claimed_at IS NOT NULL
        )
    )
    OR (
        NEW.claim_owner IS NOT NULL
        AND (
            NEW.claim_token_hash IS NULL
            OR NEW.last_claimed_at IS NULL
        )
    )
    OR NEW.terminal_reason IS NOT NULL
)
BEGIN
    SELECT RAISE(ABORT, 'trusted agent lease active shape is invalid');
END;

CREATE TRIGGER trusted_lease_v37_active_shape_before_update
BEFORE UPDATE ON trusted_agent_workspace_leases
WHEN NEW.state = 'active'
 AND (
    NEW.assignment_ref IS NULL
    OR (
        NEW.claim_owner IS NULL
        AND (
            NEW.claim_token_hash IS NOT NULL
            OR NEW.last_claimed_at IS NOT NULL
        )
    )
    OR (
        NEW.claim_owner IS NOT NULL
        AND (
            NEW.claim_token_hash IS NULL
            OR NEW.last_claimed_at IS NULL
        )
    )
    OR NEW.terminal_reason IS NOT NULL
)
BEGIN
    SELECT RAISE(ABORT, 'trusted agent lease active shape is invalid');
END;

CREATE TRIGGER trusted_lease_v37_terminal_shape_before_insert
BEFORE INSERT ON trusted_agent_workspace_leases
WHEN NEW.assignment_ref IS NOT NULL
 AND NEW.state != 'active'
 AND NEW.terminal_reason IS NULL
BEGIN
    SELECT RAISE(ABORT, 'trusted agent lease terminal reason is required');
END;

CREATE TRIGGER trusted_lease_v37_terminal_shape_before_update
BEFORE UPDATE ON trusted_agent_workspace_leases
WHEN NEW.assignment_ref IS NOT NULL
 AND NEW.state != 'active'
 AND NEW.terminal_reason IS NULL
BEGIN
    SELECT RAISE(ABORT, 'trusted agent lease terminal reason is required');
END;

CREATE TRIGGER trusted_lease_v37_scope_immutable
BEFORE UPDATE ON trusted_agent_workspace_leases
WHEN OLD.assignment_ref IS NOT NULL
 AND (
    NEW.assignment_ref IS NOT OLD.assignment_ref
    OR NEW.authority_id IS NOT OLD.authority_id
    OR NEW.owner_user_id IS NOT OLD.owner_user_id
    OR NEW.owner_tenant_id IS NOT OLD.owner_tenant_id
    OR NEW.authority_epoch IS NOT OLD.authority_epoch
    OR NEW.profile_id IS NOT OLD.profile_id
    OR NEW.profile_epoch IS NOT OLD.profile_epoch
    OR NEW.workspace_binding_id IS NOT OLD.workspace_binding_id
    OR NEW.workspace_binding_epoch IS NOT OLD.workspace_binding_epoch
)
BEGIN
    SELECT RAISE(ABORT, 'trusted agent lease scope is immutable');
END;

CREATE TRIGGER trusted_lease_v37_fence_monotonic
BEFORE UPDATE ON trusted_agent_workspace_leases
WHEN OLD.assignment_ref IS NOT NULL
 AND NEW.fencing_token < OLD.fencing_token
BEGIN
    SELECT RAISE(ABORT, 'trusted agent lease fence cannot decrease');
END;

CREATE TRIGGER trusted_lease_v37_terminal_immutable
BEFORE UPDATE ON trusted_agent_workspace_leases
WHEN OLD.assignment_ref IS NOT NULL
 AND OLD.state != 'active'
BEGIN
    SELECT RAISE(ABORT, 'trusted agent terminal lease is immutable');
END;

CREATE TABLE trusted_agent_lease_operations (
    id TEXT PRIMARY KEY
        CHECK (
            length(id) = 38
            AND substr(id, 1, 6) = 'talop_'
            AND substr(id, 7) NOT GLOB '*[^0-9a-f]*'
        ),
    owner_user_id TEXT NOT NULL,
    owner_tenant_id TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    operation_kind TEXT NOT NULL
        CHECK (
            operation_kind IN (
                'issue',
                'claim_or_renew',
                'terminalize',
                'revoke'
            )
        ),
    idempotency_key_hash TEXT NOT NULL
        CHECK (
            length(idempotency_key_hash) = 71
            AND substr(idempotency_key_hash, 1, 7) = 'sha256:'
            AND substr(idempotency_key_hash, 8)
                NOT GLOB '*[^0-9a-f]*'
        ),
    request_hash TEXT NOT NULL
        CHECK (
            length(request_hash) = 71
            AND substr(request_hash, 1, 7) = 'sha256:'
            AND substr(request_hash, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    response_json TEXT NOT NULL
        CHECK (
            json_valid(response_json)
            AND json_type(response_json) = 'object'
            AND length(response_json) <= 8192
        ),
    created_at INTEGER NOT NULL,
    UNIQUE (
        owner_tenant_id,
        operation_kind,
        idempotency_key_hash
    ),
    FOREIGN KEY (owner_user_id, owner_tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT,
    FOREIGN KEY (lease_id)
        REFERENCES trusted_agent_workspace_leases(id) ON DELETE RESTRICT
) STRICT;

CREATE INDEX ix_trusted_agent_lease_operation_target
    ON trusted_agent_lease_operations (
        lease_id,
        created_at,
        id
    );

CREATE TRIGGER trusted_agent_lease_operation_append_only_update
BEFORE UPDATE ON trusted_agent_lease_operations
BEGIN
    SELECT RAISE(ABORT, 'trusted agent lease operation is append-only');
END;

CREATE TRIGGER trusted_agent_lease_operation_append_only_delete
BEFORE DELETE ON trusted_agent_lease_operations
BEGIN
    SELECT RAISE(ABORT, 'trusted agent lease operation is append-only');
END;

PRAGMA user_version = 37;

COMMIT;
