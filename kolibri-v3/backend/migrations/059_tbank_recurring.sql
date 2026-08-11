-- Recurring T-Bank subscriptions (auto-renew / rebill).
--
-- The initial payment captures a provider RebillId; later charges re-use it
-- without a customer redirect and, when CONFIRMED, extend the subscription
-- period instead of creating a brand-new subscription row.

ALTER TABLE billing_payment_intents
ADD COLUMN kind TEXT NOT NULL DEFAULT 'initial'
    CHECK (kind IN ('initial', 'recurrent'));

ALTER TABLE billing_payment_intents
ADD COLUMN recurrent_parent_id TEXT;

ALTER TABLE billing_payment_intents
ADD COLUMN rebill_id TEXT
    CHECK (
        rebill_id IS NULL
        OR (
            length(rebill_id) BETWEEN 1 AND 64
            AND rebill_id NOT GLOB '*[^A-Za-z0-9._-]*'
        )
    );

ALTER TABLE billing_payment_intents
ADD COLUMN customer_key TEXT
    CHECK (
        customer_key IS NULL
        OR (
            length(customer_key) BETWEEN 1 AND 64
            AND customer_key NOT GLOB '*[^A-Za-z0-9._-]*'
        )
    );

ALTER TABLE billing_subscriptions
ADD COLUMN auto_renew INTEGER NOT NULL DEFAULT 1
    CHECK (auto_renew IN (0, 1));

ALTER TABLE billing_subscriptions
ADD COLUMN rebill_id TEXT
    CHECK (
        rebill_id IS NULL
        OR (
            length(rebill_id) BETWEEN 1 AND 64
            AND rebill_id NOT GLOB '*[^A-Za-z0-9._-]*'
        )
    );

ALTER TABLE billing_subscriptions
ADD COLUMN customer_key TEXT
    CHECK (
        customer_key IS NULL
        OR (
            length(customer_key) BETWEEN 1 AND 64
            AND customer_key NOT GLOB '*[^A-Za-z0-9._-]*'
        )
    );

ALTER TABLE billing_subscriptions
ADD COLUMN provider_payment_id TEXT
    CHECK (
        provider_payment_id IS NULL
        OR (
            length(provider_payment_id) BETWEEN 1 AND 20
            AND provider_payment_id NOT GLOB '*[^A-Za-z0-9._-]*'
        )
    );

ALTER TABLE billing_subscriptions
ADD COLUMN renewal_attempts INTEGER NOT NULL DEFAULT 0
    CHECK (renewal_attempts BETWEEN 0 AND 999);

ALTER TABLE billing_subscriptions
ADD COLUMN last_renewal_intent_id TEXT;

CREATE INDEX ix_billing_subscription_renewal_due
    ON billing_subscriptions (
        auto_renew,
        status,
        current_period_end,
        rebill_id
    );

CREATE INDEX ix_billing_intent_recurrent_parent
    ON billing_payment_intents (recurrent_parent_id, created_at);

PRAGMA user_version = 59;
