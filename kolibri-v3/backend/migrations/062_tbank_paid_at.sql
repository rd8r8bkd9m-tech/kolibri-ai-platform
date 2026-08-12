-- Record the exact server-verified moment a payment became CONFIRMED.
-- The value is set inside the same immediate transaction that activates the
-- subscription, so history can distinguish paid intents without parsing
-- audit events.

ALTER TABLE billing_payment_intents
ADD COLUMN paid_at INTEGER
    CHECK (paid_at IS NULL OR paid_at >= 1);

PRAGMA user_version = 62;
