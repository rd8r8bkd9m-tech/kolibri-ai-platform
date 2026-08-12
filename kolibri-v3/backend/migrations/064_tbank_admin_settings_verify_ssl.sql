ALTER TABLE billing_provider_settings
ADD COLUMN verify_ssl INTEGER NOT NULL DEFAULT 1
    CHECK (verify_ssl IN (0, 1));

PRAGMA user_version = 64;
