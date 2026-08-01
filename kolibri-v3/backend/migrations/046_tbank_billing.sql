BEGIN IMMEDIATE;

-- Billing is provider-neutral at the entitlement boundary. This catalog is
-- generic and can be extended only by reviewed server migrations/operations;
-- the current construction vertical is approved data, not a schema invariant.
CREATE TABLE billing_entitlement_catalog (
    code TEXT PRIMARY KEY
        CHECK (
            length(code) BETWEEN 3 AND 96
            AND substr(code, 1, 1) GLOB '[a-z0-9]'
            AND code NOT GLOB '*[^a-z0-9._-]*'
        ),
    active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
) STRICT;

INSERT INTO billing_entitlement_catalog (
    code, active, created_at, updated_at
) VALUES (
    'construction.estimates.use', 1, unixepoch(), unixepoch()
);

-- Billing plans are server-owned commercial policy. The plan table is
-- deliberately empty after migration: prices, fiscal attributes and duration
-- must be approved by the product/legal owner instead of being invented by a
-- client or deployment script.
CREATE TABLE billing_plans (
    code TEXT PRIMARY KEY
        CHECK (
            length(code) BETWEEN 1 AND 48
            AND code NOT GLOB '*[^a-z0-9._-]*'
        ),
    display_name TEXT NOT NULL
        CHECK (length(display_name) BETWEEN 1 AND 120),
    amount_minor INTEGER NOT NULL
        CHECK (amount_minor BETWEEN 1 AND 9999999999),
    currency TEXT NOT NULL DEFAULT 'RUB'
        CHECK (currency = 'RUB'),
    duration_seconds INTEGER NOT NULL
        CHECK (duration_seconds BETWEEN 3600 AND 31622400),
    entitlement_code TEXT NOT NULL
        CHECK (
            length(entitlement_code) BETWEEN 3 AND 96
            AND substr(entitlement_code, 1, 1) GLOB '[a-z0-9]'
            AND entitlement_code NOT GLOB '*[^a-z0-9._-]*'
        ),
    receipt_item_name TEXT NOT NULL
        CHECK (length(receipt_item_name) BETWEEN 1 AND 128),
    receipt_tax TEXT NOT NULL
        CHECK (
            receipt_tax IN (
                'none', 'vat0', 'vat5', 'vat7', 'vat10', 'vat22',
                'vat105', 'vat107', 'vat110', 'vat122'
            )
        ),
    receipt_payment_method TEXT NOT NULL
        CHECK (
            receipt_payment_method IN (
                'full_prepayment', 'prepayment', 'advance',
                'full_payment', 'partial_payment', 'credit',
                'credit_payment'
            )
        ),
    receipt_payment_object TEXT NOT NULL
        CHECK (
            receipt_payment_object IN (
                'service', 'intellectual_activity', 'payment', 'another'
            )
        ),
    active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    FOREIGN KEY (entitlement_code)
        REFERENCES billing_entitlement_catalog(code) ON DELETE RESTRICT
) STRICT;

CREATE TRIGGER billing_plan_revision_fenced
BEFORE UPDATE ON billing_plans
WHEN NEW.code != OLD.code
  OR NEW.revision != OLD.revision + 1
  OR NEW.updated_at < OLD.updated_at
BEGIN
    SELECT RAISE(ABORT, 'billing plan update requires next revision');
END;

CREATE TABLE billing_payment_intents (
    id TEXT PRIMARY KEY
        CHECK (
            length(id) BETWEEN 16 AND 96
            AND id NOT GLOB '*[^A-Za-z0-9._~-]*'
        ),
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    plan_code TEXT NOT NULL,
    plan_revision INTEGER NOT NULL CHECK (plan_revision >= 1),
    plan_display_name TEXT NOT NULL
        CHECK (length(plan_display_name) BETWEEN 1 AND 120),
    entitlement_code TEXT NOT NULL
        CHECK (
            length(entitlement_code) BETWEEN 3 AND 96
            AND substr(entitlement_code, 1, 1) GLOB '[a-z0-9]'
            AND entitlement_code NOT GLOB '*[^a-z0-9._-]*'
        ),
    duration_seconds INTEGER NOT NULL
        CHECK (duration_seconds BETWEEN 3600 AND 31622400),
    receipt_item_name TEXT NOT NULL
        CHECK (length(receipt_item_name) BETWEEN 1 AND 128),
    receipt_tax TEXT NOT NULL
        CHECK (
            receipt_tax IN (
                'none', 'vat0', 'vat5', 'vat7', 'vat10', 'vat22',
                'vat105', 'vat107', 'vat110', 'vat122'
            )
        ),
    receipt_payment_method TEXT NOT NULL
        CHECK (
            receipt_payment_method IN (
                'full_prepayment', 'prepayment', 'advance',
                'full_payment', 'partial_payment', 'credit',
                'credit_payment'
            )
        ),
    receipt_payment_object TEXT NOT NULL
        CHECK (
            receipt_payment_object IN (
                'service', 'intellectual_activity', 'payment', 'another'
            )
        ),
    amount_minor INTEGER NOT NULL
        CHECK (amount_minor BETWEEN 1 AND 9999999999),
    currency TEXT NOT NULL CHECK (currency = 'RUB'),
    provider TEXT NOT NULL CHECK (provider = 'tbank'),
    provider_environment TEXT NOT NULL
        CHECK (provider_environment IN ('test', 'demo', 'production')),
    return_surface TEXT NOT NULL DEFAULT 'web'
        CHECK (return_surface IN ('web', 'pwa')),
    terminal_fingerprint TEXT NOT NULL
        CHECK (
            length(terminal_fingerprint) = 16
            AND terminal_fingerprint NOT GLOB '*[^0-9a-f]*'
        ),
    order_id TEXT NOT NULL UNIQUE
        CHECK (length(order_id) BETWEEN 1 AND 50),
    provider_payment_id TEXT UNIQUE
        CHECK (
            provider_payment_id IS NULL
            OR length(provider_payment_id) BETWEEN 1 AND 20
        ),
    payment_url TEXT
        CHECK (payment_url IS NULL OR length(payment_url) BETWEEN 12 AND 2048),
    idempotency_key TEXT NOT NULL
        CHECK (length(idempotency_key) BETWEEN 16 AND 128),
    request_hash TEXT NOT NULL
        CHECK (
            length(request_hash) = 64
            AND request_hash NOT GLOB '*[^0-9a-f]*'
        ),
    return_nonce_hash TEXT NOT NULL
        CHECK (
            length(return_nonce_hash) = 64
            AND return_nonce_hash NOT GLOB '*[^0-9a-f]*'
        ),
    status TEXT NOT NULL
        CHECK (
            status IN (
                'initializing', 'pending', 'unknown', 'authorized',
                'succeeded', 'failed', 'canceled',
                'partially_refunded', 'refunded'
            )
        ),
    provider_status TEXT
        CHECK (provider_status IS NULL OR length(provider_status) <= 48),
    provider_error_code TEXT
        CHECK (provider_error_code IS NULL OR length(provider_error_code) <= 32),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    initialized_at INTEGER,
    UNIQUE (tenant_id, user_id, idempotency_key),
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT,
    FOREIGN KEY (plan_code)
        REFERENCES billing_plans(code) ON DELETE RESTRICT,
    FOREIGN KEY (entitlement_code)
        REFERENCES billing_entitlement_catalog(code) ON DELETE RESTRICT
) STRICT;

CREATE INDEX ix_billing_payment_subject_created
    ON billing_payment_intents (tenant_id, user_id, created_at DESC, id DESC);

CREATE INDEX ix_billing_payment_provider_order
    ON billing_payment_intents (provider, order_id, provider_payment_id);

CREATE TRIGGER billing_payment_scope_immutable
BEFORE UPDATE ON billing_payment_intents
WHEN NEW.id != OLD.id
  OR NEW.tenant_id != OLD.tenant_id
  OR NEW.user_id != OLD.user_id
  OR NEW.plan_code != OLD.plan_code
  OR NEW.plan_revision != OLD.plan_revision
  OR NEW.plan_display_name != OLD.plan_display_name
  OR NEW.entitlement_code != OLD.entitlement_code
  OR NEW.duration_seconds != OLD.duration_seconds
  OR NEW.receipt_item_name != OLD.receipt_item_name
  OR NEW.receipt_tax != OLD.receipt_tax
  OR NEW.receipt_payment_method != OLD.receipt_payment_method
  OR NEW.receipt_payment_object != OLD.receipt_payment_object
  OR NEW.amount_minor != OLD.amount_minor
  OR NEW.currency != OLD.currency
  OR NEW.provider != OLD.provider
  OR NEW.provider_environment != OLD.provider_environment
  OR NEW.return_surface != OLD.return_surface
  OR NEW.terminal_fingerprint != OLD.terminal_fingerprint
  OR NEW.order_id != OLD.order_id
  OR NEW.idempotency_key != OLD.idempotency_key
  OR NEW.request_hash != OLD.request_hash
  OR NEW.return_nonce_hash != OLD.return_nonce_hash
  OR (
      OLD.provider_payment_id IS NOT NULL
      AND NEW.provider_payment_id IS NOT OLD.provider_payment_id
  )
  OR (
      OLD.payment_url IS NOT NULL
      AND NEW.payment_url IS NOT OLD.payment_url
  )
BEGIN
    SELECT RAISE(ABORT, 'billing payment scope is immutable');
END;

CREATE TRIGGER billing_payment_version_fenced
BEFORE UPDATE ON billing_payment_intents
WHEN NEW.version != OLD.version + 1 OR NEW.updated_at < OLD.updated_at
BEGIN
    SELECT RAISE(ABORT, 'billing payment update requires next version');
END;

CREATE TABLE billing_subscriptions (
    id TEXT PRIMARY KEY
        CHECK (
            length(id) BETWEEN 16 AND 96
            AND id NOT GLOB '*[^A-Za-z0-9._~-]*'
        ),
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    plan_code TEXT NOT NULL,
    entitlement_code TEXT NOT NULL
        CHECK (
            length(entitlement_code) BETWEEN 3 AND 96
            AND substr(entitlement_code, 1, 1) GLOB '[a-z0-9]'
            AND entitlement_code NOT GLOB '*[^a-z0-9._-]*'
        ),
    payment_intent_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL
        CHECK (status IN ('active', 'refunded', 'canceled', 'expired')),
    previous_tenant_plan_code TEXT NOT NULL
        CHECK (
            length(previous_tenant_plan_code) BETWEEN 1 AND 48
            AND previous_tenant_plan_code NOT GLOB '*[^a-z0-9._-]*'
        ),
    current_period_start INTEGER NOT NULL,
    current_period_end INTEGER NOT NULL
        CHECK (current_period_end > current_period_start),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT,
    FOREIGN KEY (plan_code)
        REFERENCES billing_plans(code) ON DELETE RESTRICT,
    FOREIGN KEY (payment_intent_id)
        REFERENCES billing_payment_intents(id) ON DELETE RESTRICT,
    FOREIGN KEY (entitlement_code)
        REFERENCES billing_entitlement_catalog(code) ON DELETE RESTRICT
) STRICT;

CREATE INDEX ix_billing_subscription_subject_active
    ON billing_subscriptions (
        tenant_id,
        user_id,
        status,
        current_period_end DESC
    );

CREATE TABLE billing_notification_events (
    id TEXT PRIMARY KEY
        CHECK (
            length(id) BETWEEN 16 AND 96
            AND id NOT GLOB '*[^A-Za-z0-9._~-]*'
        ),
    event_digest TEXT NOT NULL UNIQUE
        CHECK (
            length(event_digest) = 64
            AND event_digest NOT GLOB '*[^0-9a-f]*'
        ),
    payment_intent_id TEXT NOT NULL,
    provider_payment_id TEXT NOT NULL
        CHECK (length(provider_payment_id) BETWEEN 1 AND 20),
    provider_status TEXT NOT NULL
        CHECK (length(provider_status) BETWEEN 1 AND 48),
    outcome TEXT NOT NULL
        CHECK (
            outcome IN (
                'applied', 'ignored_duplicate', 'ignored_out_of_order',
                'ignored_unknown_status'
            )
        ),
    created_at INTEGER NOT NULL,
    FOREIGN KEY (payment_intent_id)
        REFERENCES billing_payment_intents(id) ON DELETE RESTRICT
) STRICT;

CREATE INDEX ix_billing_notification_payment_created
    ON billing_notification_events (payment_intent_id, created_at DESC, id DESC);

CREATE TABLE billing_audit_events (
    id TEXT PRIMARY KEY
        CHECK (
            length(id) BETWEEN 16 AND 96
            AND id NOT GLOB '*[^A-Za-z0-9._~-]*'
        ),
    tenant_id TEXT NOT NULL,
    user_id TEXT,
    actor_type TEXT NOT NULL
        CHECK (actor_type IN ('user', 'tbank', 'system', 'platform_owner')),
    action TEXT NOT NULL CHECK (length(action) BETWEEN 3 AND 120),
    payment_intent_id TEXT,
    details_json TEXT NOT NULL
        CHECK (
            json_valid(details_json)
            AND json_type(details_json) = 'object'
            AND length(details_json) <= 8192
        ),
    created_at INTEGER NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users(id, tenant_id) ON DELETE RESTRICT,
    FOREIGN KEY (payment_intent_id)
        REFERENCES billing_payment_intents(id) ON DELETE RESTRICT
) STRICT;

CREATE INDEX ix_billing_audit_created
    ON billing_audit_events (created_at DESC, id DESC);

CREATE INDEX ix_billing_audit_payment
    ON billing_audit_events (payment_intent_id, created_at DESC, id DESC);

PRAGMA user_version = 46;

COMMIT;
