PRAGMA foreign_keys = ON;

ALTER TABLE pricing_source_snapshots
    ADD COLUMN source_policy_version TEXT NOT NULL
        DEFAULT 'legacy_unrecorded';

ALTER TABLE pricing_source_snapshots
    ADD COLUMN source_policy_json TEXT NOT NULL
        DEFAULT '{}'
        CHECK (json_valid(source_policy_json));

PRAGMA user_version = 15;
