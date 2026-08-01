BEGIN IMMEDIATE;

-- 046 was applied by an earlier V3 candidate on some databases before the
-- provider-neutral entitlement catalog was introduced. Keep migrations
-- append-only and converge those databases without rewriting payment data.
CREATE TABLE IF NOT EXISTS billing_entitlement_catalog (
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

INSERT OR IGNORE INTO billing_entitlement_catalog (
    code, active, created_at, updated_at
) VALUES (
    'construction.estimates.use', 1, unixepoch(), unixepoch()
);

PRAGMA user_version = 47;

COMMIT;
