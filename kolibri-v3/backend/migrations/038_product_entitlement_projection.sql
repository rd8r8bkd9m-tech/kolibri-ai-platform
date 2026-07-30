BEGIN IMMEDIATE;

-- Product entitlements are server-owned grants. They are deliberately
-- independent from role labels, browser/mobile payloads and platform
-- administration authority.
CREATE TABLE product_entitlement_grants (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    entitlement_code TEXT NOT NULL
        CHECK (
            entitlement_code = 'construction.estimates.use'
        ),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'revoked')),
    grant_epoch INTEGER NOT NULL DEFAULT 1 CHECK (grant_epoch >= 1),
    source TEXT NOT NULL
        CHECK (
            source IN (
                'release_bootstrap',
                'trusted_server_operator',
                'subscription_policy',
                'platform_admin'
            )
        ),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, user_id, entitlement_code),
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE CASCADE
) STRICT;

CREATE INDEX ix_product_entitlement_active_subject
    ON product_entitlement_grants (
        tenant_id,
        user_id,
        status,
        entitlement_code
    );

-- The first construction release is explicitly provisioned only for the
-- trusted singleton owner. All other users remain denied until a server-side
-- subscription/admin operation creates a grant.
INSERT INTO product_entitlement_grants (
    tenant_id,
    user_id,
    entitlement_code,
    status,
    grant_epoch,
    source,
    created_at,
    updated_at
)
SELECT
    authority.tenant_id,
    authority.user_id,
    'construction.estimates.use',
    'active',
    1,
    'release_bootstrap',
    unixepoch(),
    unixepoch()
FROM platform_authority_grants AS authority
WHERE authority.authority_id = 'platform_owner'
  AND authority.active = 1;

-- Scope and entitlement identity are immutable. Revoke/regrant is an
-- epoch-fenced state transition, not a row retarget.
CREATE TRIGGER product_entitlement_scope_immutable
BEFORE UPDATE ON product_entitlement_grants
WHEN NEW.tenant_id != OLD.tenant_id
  OR NEW.user_id != OLD.user_id
  OR NEW.entitlement_code != OLD.entitlement_code
BEGIN
    SELECT RAISE(ABORT, 'product entitlement scope is immutable');
END;

CREATE TRIGGER product_entitlement_epoch_fenced
BEFORE UPDATE ON product_entitlement_grants
WHEN NEW.grant_epoch != OLD.grant_epoch + 1
  OR NEW.updated_at < OLD.updated_at
BEGIN
    SELECT RAISE(ABORT, 'product entitlement update requires next epoch');
END;

PRAGMA user_version = 38;

COMMIT;
