PRAGMA foreign_keys = OFF;

-- V3 estimate knowledge is authority-first.  System rows deliberately keep
-- tenant_id NULL; tenant/project rows always carry their composite scope.
CREATE TABLE IF NOT EXISTS catalog_entries (
    id TEXT PRIMARY KEY,
    tenant_id TEXT,
    project_id TEXT,
    visibility TEXT NOT NULL
        CHECK (visibility IN (
            'project_private', 'tenant_private', 'system_curated',
            'market_aggregate'
        )),
    kind TEXT NOT NULL
        CHECK (kind IN ('work', 'material', 'equipment', 'service')),
    canonical_name TEXT NOT NULL CHECK (length(canonical_name) BETWEEN 1 AND 300),
    short_name TEXT NOT NULL CHECK (length(short_name) BETWEEN 1 AND 160),
    description TEXT NOT NULL DEFAULT '',
    category_id TEXT NOT NULL DEFAULT '',
    canonical_unit TEXT NOT NULL CHECK (length(canonical_unit) BETWEEN 1 AND 32),
    specification_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(specification_json)),
    aliases_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(aliases_json)),
    region_scope_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(region_scope_json)),
    provenance_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(provenance_json)),
    review_status TEXT NOT NULL
        CHECK (review_status IN ('proposed', 'approved', 'archived')),
    confidence TEXT NOT NULL DEFAULT '0'
        CHECK (confidence GLOB '[0-1]' OR confidence GLOB '[0-1].[0-9]*'),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    valid_from TEXT,
    valid_until TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by_user_id TEXT,
    approved_by_user_id TEXT,
    UNIQUE (tenant_id, id),
    CHECK (
        (visibility = 'project_private' AND tenant_id IS NOT NULL AND project_id IS NOT NULL)
        OR (visibility IN ('tenant_private', 'market_aggregate') AND tenant_id IS NOT NULL)
        OR (visibility = 'system_curated' AND tenant_id IS NULL AND project_id IS NULL)
    ),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (approved_by_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_catalog_entries_visibility_scope
    ON catalog_entries (visibility, tenant_id, project_id, review_status, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_catalog_entries_name
    ON catalog_entries (tenant_id, kind, canonical_name, canonical_unit);

CREATE TABLE IF NOT EXISTS catalog_candidates (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT,
    source_type TEXT NOT NULL
        CHECK (source_type IN ('ai_generated', 'user_manual', 'estimate_import', 'supplier_import')),
    original_text TEXT NOT NULL CHECK (length(original_text) BETWEEN 1 AND 2000),
    proposed_canonical_name TEXT NOT NULL CHECK (length(proposed_canonical_name) BETWEEN 1 AND 300),
    proposed_short_name TEXT NOT NULL CHECK (length(proposed_short_name) BETWEEN 1 AND 160),
    kind TEXT NOT NULL
        CHECK (kind IN ('work', 'material', 'equipment', 'service')),
    proposed_unit TEXT NOT NULL CHECK (length(proposed_unit) BETWEEN 1 AND 32),
    specification_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(specification_json)),
    aliases_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(aliases_json)),
    category_id TEXT NOT NULL DEFAULT '',
    confidence TEXT NOT NULL DEFAULT '0'
        CHECK (confidence GLOB '[0-1]' OR confidence GLOB '[0-1].[0-9]*'),
    source_estimate_id TEXT,
    source_estimate_version INTEGER,
    source_row_id TEXT,
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('proposed', 'needs_review', 'approved', 'rejected', 'merged', 'archived')),
    duplicate_of_id TEXT,
    merge_target_id TEXT,
    reviewer_user_id TEXT,
    review_note TEXT,
    audit_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(audit_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, source_estimate_id)
        REFERENCES document_slots (tenant_id, id)
        ON DELETE SET NULL,
    FOREIGN KEY (duplicate_of_id)
        REFERENCES catalog_entries (id)
        ON DELETE SET NULL,
    FOREIGN KEY (merge_target_id)
        REFERENCES catalog_entries (id)
        ON DELETE SET NULL,
    FOREIGN KEY (reviewer_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_catalog_candidates_review
    ON catalog_candidates (tenant_id, project_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS catalog_candidate_events (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('created', 'reviewed', 'merged', 'rejected', 'archived')),
    actor_user_id TEXT,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id, candidate_id)
        REFERENCES catalog_candidates (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (actor_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_catalog_candidate_events_candidate
    ON catalog_candidate_events (tenant_id, candidate_id, created_at, id);

CREATE TABLE IF NOT EXISTS technology_card_definitions (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL CHECK (scope IN ('system_curated', 'tenant_private', 'project_private')),
    tenant_id TEXT,
    project_id TEXT,
    canonical_name TEXT NOT NULL CHECK (length(canonical_name) BETWEEN 1 AND 240),
    purpose TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_id, id),
    CHECK (
        (scope = 'system_curated' AND tenant_id IS NULL AND project_id IS NULL)
        OR (scope = 'tenant_private' AND tenant_id IS NOT NULL)
        OR (scope = 'project_private' AND tenant_id IS NOT NULL AND project_id IS NOT NULL)
    ),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS technology_card_versions (
    id TEXT PRIMARY KEY,
    card_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    status TEXT NOT NULL CHECK (status IN ('draft', 'approved', 'superseded', 'archived')),
    applicability_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(applicability_json)),
    inputs_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(inputs_json)),
    lines_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(lines_json)),
    resources_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(resources_json)),
    assumptions_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(assumptions_json)),
    exceptions_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(exceptions_json)),
    rules_version TEXT NOT NULL CHECK (length(rules_version) BETWEEN 1 AND 120),
    created_by_user_id TEXT,
    approved_by_user_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (card_id, version),
    FOREIGN KEY (card_id) REFERENCES technology_card_definitions (id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY (approved_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_technology_card_versions_status
    ON technology_card_versions (card_id, status, version DESC);

CREATE TABLE IF NOT EXISTS pricing_consent_grants (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    project_id TEXT,
    scope TEXT NOT NULL CHECK (scope IN ('market_aggregate', 'tenant_statistics')),
    policy_version TEXT NOT NULL CHECK (length(policy_version) BETWEEN 1 AND 120),
    status TEXT NOT NULL CHECK (status IN ('granted', 'revoked')),
    granted_at TEXT NOT NULL,
    revoked_at TEXT,
    source TEXT NOT NULL CHECK (length(source) BETWEEN 1 AND 120),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT,
    CHECK ((status = 'granted' AND revoked_at IS NULL) OR (status = 'revoked' AND revoked_at IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pricing_consent_active_scope
    ON pricing_consent_grants (tenant_id, user_id, COALESCE(project_id, ''), scope)
    WHERE status = 'granted';

CREATE TABLE IF NOT EXISTS pricing_consent_events (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    consent_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('granted', 'revoked')),
    actor_user_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id, consent_id)
        REFERENCES pricing_consent_grants (tenant_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (actor_user_id, tenant_id)
        REFERENCES users (id, tenant_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_pricing_consent_events_scope
    ON pricing_consent_events (tenant_id, consent_id, created_at, id);

CREATE TABLE IF NOT EXISTS market_pricing_policies (
    policy_version TEXT PRIMARY KEY,
    minimum_independent_contributors INTEGER NOT NULL CHECK (minimum_independent_contributors >= 2),
    freshness_days INTEGER NOT NULL CHECK (freshness_days BETWEEN 1 AND 3650),
    outlier_method TEXT NOT NULL CHECK (outlier_method = 'tukey_iqr_1_5'),
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL
);

INSERT OR IGNORE INTO market_pricing_policies (
    policy_version, minimum_independent_contributors, freshness_days,
    outlier_method, active, created_at
) VALUES ('market-aggregate/1.0.0', 5, 180, 'tukey_iqr_1_5', 1, '2026-08-02T00:00:00Z');

CREATE TABLE IF NOT EXISTS market_price_aggregates (
    id TEXT PRIMARY KEY,
    catalog_entry_id TEXT,
    item_key TEXT NOT NULL,
    specification_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(specification_json)),
    unit TEXT NOT NULL,
    country TEXT NOT NULL DEFAULT 'RU',
    region TEXT NOT NULL,
    municipality TEXT,
    quantity_band TEXT NOT NULL DEFAULT 'unspecified',
    date_window_start TEXT NOT NULL,
    date_window_end TEXT NOT NULL,
    source_composition_json TEXT NOT NULL CHECK (json_valid(source_composition_json)),
    independent_contributor_count INTEGER NOT NULL CHECK (independent_contributor_count >= 0),
    observation_count INTEGER NOT NULL CHECK (observation_count >= 0),
    p25 TEXT NOT NULL,
    median TEXT NOT NULL,
    p75 TEXT NOT NULL,
    freshness TEXT NOT NULL CHECK (freshness IN ('fresh', 'stale')),
    confidence TEXT NOT NULL,
    calculation_policy_version TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    published INTEGER NOT NULL CHECK (published IN (0, 1)),
    FOREIGN KEY (catalog_entry_id) REFERENCES catalog_entries (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_market_price_aggregates_lookup
    ON market_price_aggregates (item_key, country, region, unit, published, generated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_market_price_aggregates_key
    ON market_price_aggregates (
        item_key, unit, country, region, COALESCE(municipality, ''),
        quantity_band, date_window_start, date_window_end,
        calculation_policy_version
    );

-- Rebuild the legacy observations table once so the source hierarchy can
-- include paid invoices/completed work and every new observation carries
-- explicit context, evidence and consent fields. Existing rows are copied
-- byte-for-byte for the legacy columns.
ALTER TABLE price_observations RENAME TO price_observations_v48;

CREATE TABLE price_observations (
    tenant_id TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    estimate_version INTEGER NOT NULL CHECK (estimate_version >= 1),
    row_id TEXT NOT NULL,
    item_key TEXT NOT NULL CHECK (length(item_key) = 71 AND item_key LIKE 'sha256:%' AND substr(item_key, 8) NOT GLOB '*[^0-9a-f]*'),
    catalog_entry_id TEXT,
    item_kind TEXT NOT NULL CHECK (item_kind IN ('work', 'material', 'equipment', 'service')),
    description TEXT NOT NULL,
    normalized_description TEXT NOT NULL,
    specification_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(specification_json)),
    region TEXT NOT NULL,
    country TEXT NOT NULL DEFAULT 'RU',
    municipality TEXT,
    timezone TEXT,
    unit TEXT NOT NULL,
    quantity_band TEXT NOT NULL DEFAULT 'unspecified',
    quantity_min TEXT,
    quantity_max TEXT,
    previous_unit_price_rub TEXT,
    observed_unit_price_rub TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'RUB' CHECK (currency = 'RUB'),
    tax_treatment TEXT NOT NULL DEFAULT 'unknown' CHECK (tax_treatment IN ('included', 'excluded', 'unknown', 'not_applicable')),
    delivery_treatment TEXT NOT NULL DEFAULT 'unknown' CHECK (delivery_treatment IN ('included', 'excluded', 'unknown')),
    source_type TEXT NOT NULL CHECK (source_type IN ('ai_preliminary', 'user_edit', 'official_reference', 'supplier_offer', 'customer_approved', 'contract_price', 'paid_invoice', 'completed_work')),
    lifecycle TEXT NOT NULL CHECK (lifecycle IN ('draft', 'shared', 'approved', 'contracted')),
    context_json TEXT NOT NULL CHECK (json_valid(context_json)),
    evidence_quote_id TEXT,
    evidence_reference_hash TEXT,
    observed_at TEXT NOT NULL,
    valid_until TEXT,
    confidence TEXT NOT NULL DEFAULT '0',
    consent_id TEXT,
    contributor_pseudonym TEXT NOT NULL DEFAULT 'legacy:unknown',
    aggregate_eligible INTEGER NOT NULL DEFAULT 0 CHECK (aggregate_eligible IN (0, 1)),
    test_data INTEGER NOT NULL DEFAULT 0 CHECK (test_data IN (0, 1)),
    archived_at TEXT,
    archive_reason TEXT,
    created_by_user_id TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, document_id, estimate_version, row_id, source_type),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects (tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, document_id, estimate_version) REFERENCES estimate_versions (tenant_id, document_id, version) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, evidence_quote_id) REFERENCES pricing_quotes (tenant_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, consent_id) REFERENCES pricing_consent_grants (tenant_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (created_by_user_id, tenant_id) REFERENCES users (id, tenant_id) ON DELETE RESTRICT,
    FOREIGN KEY (catalog_entry_id) REFERENCES catalog_entries (id) ON DELETE SET NULL
);

INSERT INTO price_observations (
    tenant_id, id, project_id, document_id, estimate_version, row_id,
    item_key, item_kind, description, normalized_description,
    region, unit, previous_unit_price_rub, observed_unit_price_rub,
    currency, source_type, lifecycle, context_json, evidence_quote_id,
    aggregate_eligible, created_by_user_id, observed_at,
    specification_json, country, quantity_band, tax_treatment,
    delivery_treatment, confidence, contributor_pseudonym
)
SELECT
    tenant_id, id, project_id, document_id, estimate_version, row_id,
    item_key, item_kind, description, normalized_description,
    region, unit, previous_unit_price_rub, observed_unit_price_rub,
    currency, source_type, lifecycle, context_json, evidence_quote_id,
    aggregate_eligible, created_by_user_id, observed_at,
    '{}', 'RU', 'unspecified', 'unknown', 'unknown',
    CASE source_type
        WHEN 'contract_price' THEN '0.9'
        WHEN 'customer_approved' THEN '0.75'
        WHEN 'supplier_offer' THEN '0.7'
        WHEN 'official_reference' THEN '0.5'
        WHEN 'user_edit' THEN '0.2'
        ELSE '0.05'
    END,
    'legacy:' || substr(tenant_id || ':' || created_by_user_id, 1, 120)
FROM price_observations_v48;

DROP TABLE price_observations_v48;

CREATE INDEX IF NOT EXISTS ix_price_observations_personal_catalog
    ON price_observations (tenant_id, created_by_user_id, project_id, region, item_key, observed_at DESC);
CREATE INDEX IF NOT EXISTS ix_price_observations_future_aggregation
    ON price_observations (aggregate_eligible, country, region, item_key, observed_at DESC);
CREATE INDEX IF NOT EXISTS ix_price_observations_contributor
    ON price_observations (contributor_pseudonym, item_key, region, observed_at DESC);

CREATE TRIGGER IF NOT EXISTS trg_price_observations_no_ai_aggregate
BEFORE INSERT ON price_observations
WHEN NEW.source_type = 'ai_preliminary' AND NEW.aggregate_eligible = 1
BEGIN
    SELECT RAISE(ABORT, 'AI preliminary observations cannot enter aggregates');
END;

CREATE TRIGGER IF NOT EXISTS trg_price_observations_no_ai_aggregate_update
BEFORE UPDATE OF aggregate_eligible, source_type ON price_observations
WHEN NEW.source_type = 'ai_preliminary' AND NEW.aggregate_eligible = 1
BEGIN
    SELECT RAISE(ABORT, 'AI preliminary observations cannot enter aggregates');
END;

-- Small reviewed technology-card/catalog seed. These entries contain names,
-- units and applicability only; no fabricated normative coefficients or
-- market prices are asserted by the migration.
INSERT OR IGNORE INTO catalog_entries (
    id, tenant_id, project_id, visibility, kind, canonical_name, short_name,
    description, category_id, canonical_unit, specification_json,
    aliases_json, region_scope_json, provenance_json, review_status,
    confidence, version, valid_from, created_at, updated_at
) VALUES
('catalog_system_site_preparation', NULL, NULL, 'system_curated', 'work',
 'Подготовка строительной площадки', 'Подготовка площадки',
 'Подготовительные работы до начала строительства.', 'site-preparation', 'м²',
 '{}', '["подготовка участка","стройплощадка"]', '{}',
 '{"sourceType":"curated","sourceReference":"kolibri-seed/1"}', 'approved', '0.8', 1,
 '2026-08-02', '2026-08-02T00:00:00Z', '2026-08-02T00:00:00Z'),
('catalog_system_foundation_concrete', NULL, NULL, 'system_curated', 'material',
 'Бетон для фундамента', 'Бетон фундаментный',
 'Материал фундамента; марка и подвижность уточняются по проекту.', 'foundation', 'м³',
 '{"requiresSpecification":["class","mobility"]}', '["бетон","бетон м300","бетон м 300"]', '{}',
 '{"sourceType":"curated","sourceReference":"kolibri-seed/1"}', 'approved', '0.8', 1,
 '2026-08-02', '2026-08-02T00:00:00Z', '2026-08-02T00:00:00Z'),
('catalog_system_rebar', NULL, NULL, 'system_curated', 'material',
 'Арматура для фундамента', 'Арматура',
 'Стальная арматура; диаметр и класс уточняются по проекту.', 'foundation', 'кг',
 '{"requiresSpecification":["class","diameter"]}', '["арматурная сталь","каркас фундамента"]', '{}',
 '{"sourceType":"curated","sourceReference":"kolibri-seed/1"}', 'approved', '0.8', 1,
 '2026-08-02', '2026-08-02T00:00:00Z', '2026-08-02T00:00:00Z'),
('catalog_system_wall_masonry', NULL, NULL, 'system_curated', 'work',
 'Кладка наружных стен', 'Кладка стен',
 'Работа по устройству наружных стен; материал и толщина уточняются.', 'structure', 'м²',
 '{"requiresSpecification":["material","thickness"]}', '["стены","коробка","кладка"]', '{}',
 '{"sourceType":"curated","sourceReference":"kolibri-seed/1"}', 'approved', '0.8', 1,
 '2026-08-02', '2026-08-02T00:00:00Z', '2026-08-02T00:00:00Z'),
('catalog_system_roof', NULL, NULL, 'system_curated', 'work',
 'Устройство кровли', 'Кровля',
 'Монтаж кровельной системы и покрытия; тип кровли уточняется.', 'roof', 'м²',
 '{"requiresSpecification":["roofType"]}', '["крыша","кровельные работы"]', '{}',
 '{"sourceType":"curated","sourceReference":"kolibri-seed/1"}', 'approved', '0.8', 1,
 '2026-08-02', '2026-08-02T00:00:00Z', '2026-08-02T00:00:00Z'),
('catalog_system_electrical', NULL, NULL, 'system_curated', 'service',
 'Электромонтажные работы', 'Электрика',
 'Внутренние электрические сети; проект и состав точек уточняются.', 'engineering', 'м²',
 '{"requiresSpecification":["pointCount","supplyScheme"]}', '["электрика","электромонтаж"]', '{}',
 '{"sourceType":"curated","sourceReference":"kolibri-seed/1"}', 'approved', '0.8', 1,
 '2026-08-02', '2026-08-02T00:00:00Z', '2026-08-02T00:00:00Z'),
('catalog_system_plumbing', NULL, NULL, 'system_curated', 'service',
 'Сантехнические работы', 'Сантехника',
 'Внутренние системы водоснабжения и канализации; точки подключения уточняются.', 'engineering', 'компл.',
 '{}', '["водоснабжение","канализация"]', '{}',
 '{"sourceType":"curated","sourceReference":"kolibri-seed/1"}', 'approved', '0.8', 1,
 '2026-08-02', '2026-08-02T00:00:00Z', '2026-08-02T00:00:00Z'),
('catalog_system_plaster_mechanized', NULL, NULL, 'system_curated', 'work',
 'Механизированная штукатурка стен', 'Механизированная штукатурка',
 'Карта применяется только при явном запросе на штукатурные работы.', 'finishing', 'м²',
 '{"technologyCard":"technology_card_plaster_mechanized"}', '["машинная штукатурка","штукатурка стен"]', '{}',
 '{"sourceType":"curated","sourceReference":"kolibri-seed/1"}', 'approved', '0.8', 1,
 '2026-08-02', '2026-08-02T00:00:00Z', '2026-08-02T00:00:00Z');

INSERT OR IGNORE INTO technology_card_definitions (
    id, scope, canonical_name, purpose, created_at, updated_at
) VALUES
('technology_card_house_basic', 'system_curated', 'Базовая структура строительства дома',
 'Разворачивает объектный brief в разделы без утверждения нормативных коэффициентов.',
 '2026-08-02T00:00:00Z', '2026-08-02T00:00:00Z'),
('technology_card_plaster_mechanized', 'system_curated', 'Механизированная штукатурка стен',
 'Применяется только к явно распознанной штукатурке стен.',
 '2026-08-02T00:00:00Z', '2026-08-02T00:00:00Z');

INSERT OR IGNORE INTO technology_card_versions (
    id, card_id, version, status, applicability_json, inputs_json,
    lines_json, resources_json, assumptions_json, exceptions_json,
    rules_version, created_at, updated_at
) VALUES
('technology_card_house_basic_v1', 'technology_card_house_basic', 1, 'approved',
 '{"intent":["new_build","house","cottage"]}',
 '["area_m2","region","storeys","foundation","engineering"]',
 '[{"section":"Подготовка","catalogEntryId":"catalog_system_site_preparation","quantityFormula":"area_m2","normStatus":"requires_source"},{"section":"Фундамент","catalogEntryId":"catalog_system_foundation_concrete","quantityFormula":"project_input","normStatus":"requires_source"},{"section":"Коробка","catalogEntryId":"catalog_system_wall_masonry","quantityFormula":"project_input","normStatus":"requires_source"},{"section":"Кровля","catalogEntryId":"catalog_system_roof","quantityFormula":"project_input","normStatus":"requires_source"},{"section":"Инженерные сети","catalogEntryId":"catalog_system_electrical","quantityFormula":"project_input","normStatus":"requires_source"},{"section":"Инженерные сети","catalogEntryId":"catalog_system_plumbing","quantityFormula":"project_input","normStatus":"requires_source"}]',
 '[]',
 '["Этажность, грунт, фундамент, планировка, инженерные вводы и спецификации требуют подтверждения."]',
 '["Не применять к запросу только о штукатурке."]',
 'house-preliminary/1.0.0', '2026-08-02T00:00:00Z', '2026-08-02T00:00:00Z'),
('technology_card_plaster_mechanized_v1', 'technology_card_plaster_mechanized', 1, 'approved',
 '{"intent":["plastering"],"requiresExplicitKeyword":true}',
 '["wall_area_m2","average_thickness_mm","material","application_method"]',
 '[{"section":"Штукатурка","catalogEntryId":"catalog_system_plaster_mechanized","quantityFormula":"wall_area_m2","normStatus":"server_engine"}]',
 '[]', '[]', '["Не выбирать для общего запроса о строительстве дома."]',
 'plastering/1.0.0', '2026-08-02T00:00:00Z', '2026-08-02T00:00:00Z');

PRAGMA foreign_keys = ON;
PRAGMA user_version = 49;
