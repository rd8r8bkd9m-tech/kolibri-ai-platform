-- Reference price snapshots for construction estimates.
-- Stores versioned price data that was previously hardcoded in Python modules.

CREATE TABLE IF NOT EXISTS reference_price_snapshots (
    id TEXT PRIMARY KEY,
    version TEXT NOT NULL UNIQUE,
    work_type TEXT NOT NULL,
    region TEXT NOT NULL DEFAULT 'reference',
    observed_at TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'Kolibri reference',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reference_prices (
    snapshot_id TEXT NOT NULL REFERENCES reference_price_snapshots(id) ON DELETE CASCADE,
    item_code TEXT NOT NULL,
    unit TEXT NOT NULL,
    price TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, item_code)
);

CREATE INDEX IF NOT EXISTS idx_reference_prices_snapshot
    ON reference_prices(snapshot_id);

-- Insert the plastering reference snapshot (version 2026-07-29.1)
INSERT OR IGNORE INTO reference_price_snapshots (
    id, version, work_type, region, observed_at, valid_until, source
) VALUES (
    'plastering-reference-2026-07-29-1',
    'plastering-reference/2026-07-29.1',
    'plastering',
    'reference',
    '2026-07-29T00:00:00+00:00',
    '2026-08-29',
    'Kolibri reference snapshot'
);

-- Insert plastering reference prices
INSERT OR IGNORE INTO reference_prices (snapshot_id, item_code, unit, price) VALUES
    ('plastering-reference-2026-07-29-1', 'survey', 'm2', '35.00'),
    ('plastering-reference-2026-07-29-1', 'surface_cleaning', 'm2', '90.00'),
    ('plastering-reference-2026-07-29-1', 'protection', 'm2', '48.00'),
    ('plastering-reference-2026-07-29-1', 'primer_application', 'm2', '75.00'),
    ('plastering-reference-2026-07-29-1', 'primer_material', 'l', '120.00'),
    ('plastering-reference-2026-07-29-1', 'beacon_installation', 'm2', '160.00'),
    ('plastering-reference-2026-07-29-1', 'beacon_profile', 'ea', '85.00'),
    ('plastering-reference-2026-07-29-1', 'corner_installation', 'm', '95.00'),
    ('plastering-reference-2026-07-29-1', 'corner_profile', 'ea', '95.00'),
    ('plastering-reference-2026-07-29-1', 'mesh_installation', 'm2', '220.00'),
    ('plastering-reference-2026-07-29-1', 'reinforcing_mesh', 'm2', '75.00'),
    ('plastering-reference-2026-07-29-1', 'plaster_application', 'm2', '520.00'),
    ('plastering-reference-2026-07-29-1', 'plaster_mix', 'bag', '470.00'),
    ('plastering-reference-2026-07-29-1', 'water', 'm3', '180.00'),
    ('plastering-reference-2026-07-29-1', 'electricity', 'kWh', '8.50'),
    ('plastering-reference-2026-07-29-1', 'plaster_machine', 'shift', '8500.00'),
    ('plastering-reference-2026-07-29-1', 'delivery', 'trip', '3500.00'),
    ('plastering-reference-2026-07-29-1', 'lifting', 't', '1800.00'),
    ('plastering-reference-2026-07-29-1', 'slopes', 'm2', '1450.00'),
    ('plastering-reference-2026-07-29-1', 'smoothing', 'm2', '140.00'),
    ('plastering-reference-2026-07-29-1', 'quality_control', 'm2', '65.00'),
    ('plastering-reference-2026-07-29-1', 'cleanup', 'm2', '65.00'),
    ('plastering-reference-2026-07-29-1', 'waste_removal', 'trip', '6500.00'),
    ('plastering-reference-2026-07-29-1', 'consumables', 'set', '8500.00');

PRAGMA user_version = 55;
