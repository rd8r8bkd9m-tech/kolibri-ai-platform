PRAGMA foreign_keys = ON;

CREATE TABLE normative_source_policies (
    origin TEXT PRIMARY KEY,
    authority TEXT NOT NULL,
    authority_url TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    storage_allowed INTEGER NOT NULL
        CHECK (storage_allowed IN (0, 1)),
    indexing_allowed INTEGER NOT NULL
        CHECK (indexing_allowed IN (0, 1)),
    excerpt_display_allowed INTEGER NOT NULL
        CHECK (excerpt_display_allowed IN (0, 1)),
    review_status TEXT NOT NULL
        CHECK (
            review_status IN (
                'provisional_internal_use',
                'approved',
                'restricted',
                'blocked'
            )
        ),
    terms_url TEXT,
    reviewed_at TEXT,
    reviewed_by_user_id TEXT,
    notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

INSERT INTO normative_source_policies (
    origin, authority, authority_url, policy_version,
    storage_allowed, indexing_allowed, excerpt_display_allowed,
    review_status, terms_url, reviewed_at, reviewed_by_user_id,
    notes, updated_at
) VALUES
(
    'https://minstroyrf.gov.ru',
    'Минстрой России',
    'https://minstroyrf.gov.ru',
    'minstroy_official_documents_internal_v1',
    1, 1, 1,
    'provisional_internal_use',
    NULL, NULL, NULL,
    'Внутреннее индексирование официально опубликованных документов; полный текст не выдаётся через продуктовый API.',
    '2026-07-29T00:00:00Z'
),
(
    'https://www.minstroyrf.gov.ru',
    'Минстрой России',
    'https://minstroyrf.gov.ru',
    'minstroy_official_documents_internal_v1',
    1, 1, 1,
    'provisional_internal_use',
    NULL, NULL, NULL,
    'Внутреннее индексирование официально опубликованных документов; полный текст не выдаётся через продуктовый API.',
    '2026-07-29T00:00:00Z'
),
(
    'https://publication.pravo.gov.ru',
    'Официальное опубликование правовых актов',
    'https://publication.pravo.gov.ru',
    'official_legal_acts_v1',
    1, 1, 1,
    'approved',
    NULL, '2026-07-29T00:00:00Z', NULL,
    'Только официальные правовые акты и их официальные приложения.',
    '2026-07-29T00:00:00Z'
),
(
    'https://fgiscs.minstroyrf.ru',
    'ФГИС ЦС',
    'https://fgiscs.minstroyrf.ru',
    'fgis_normative_documents_internal_v1',
    1, 1, 1,
    'provisional_internal_use',
    NULL, NULL, NULL,
    'Кандидатный внутренний корпус; отдельные условия машинного доступа проверяются до массовой загрузки.',
    '2026-07-29T00:00:00Z'
);

CREATE TABLE normative_documents (
    id TEXT PRIMARY KEY,
    canonical_code TEXT NOT NULL UNIQUE,
    display_code TEXT NOT NULL,
    title TEXT NOT NULL,
    document_kind TEXT NOT NULL
        CHECK (
            document_kind IN (
                'sp',
                'snip',
                'gost',
                'methodology',
                'estimate_norm',
                'legal_act'
            )
        ),
    jurisdiction TEXT NOT NULL DEFAULT 'RU',
    authority TEXT NOT NULL,
    authority_url TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE normative_editions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    edition_label TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (
            status IN (
                'candidate',
                'effective',
                'superseded',
                'withdrawn',
                'quarantined'
            )
        ),
    source_url TEXT NOT NULL,
    official_publication_url TEXT,
    source_origin TEXT NOT NULL,
    effective_from TEXT,
    effective_to TEXT,
    published_on TEXT,
    fetched_at TEXT NOT NULL,
    media_type TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL
        CHECK (
            length(raw_sha256) = 71
            AND raw_sha256 LIKE 'sha256:%'
            AND substr(raw_sha256, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    raw_size INTEGER NOT NULL CHECK (raw_size >= 1),
    raw_content BLOB NOT NULL,
    extracted_text_sha256 TEXT,
    source_policy_version TEXT NOT NULL,
    source_policy_json TEXT NOT NULL CHECK (json_valid(source_policy_json)),
    metadata_json TEXT NOT NULL CHECK (json_valid(metadata_json)),
    verified_at TEXT,
    verified_by_user_id TEXT,
    verification_note TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (document_id, edition_label, raw_sha256),
    FOREIGN KEY (document_id)
        REFERENCES normative_documents (id)
        ON DELETE CASCADE,
    FOREIGN KEY (source_origin)
        REFERENCES normative_source_policies (origin)
        ON DELETE RESTRICT
);

CREATE INDEX ix_normative_editions_document_status_dates
    ON normative_editions (
        document_id,
        status,
        effective_from,
        effective_to,
        fetched_at DESC
    );

CREATE TABLE normative_sections (
    id TEXT PRIMARY KEY,
    edition_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 1),
    locator TEXT NOT NULL,
    heading TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    body_sha256 TEXT NOT NULL
        CHECK (
            length(body_sha256) = 71
            AND body_sha256 LIKE 'sha256:%'
            AND substr(body_sha256, 8) NOT GLOB '*[^0-9a-f]*'
        ),
    applicability_json TEXT NOT NULL CHECK (json_valid(applicability_json)),
    UNIQUE (edition_id, locator),
    FOREIGN KEY (edition_id)
        REFERENCES normative_editions (id)
        ON DELETE CASCADE
);

CREATE INDEX ix_normative_sections_edition_ordinal
    ON normative_sections (edition_id, ordinal);

CREATE VIRTUAL TABLE normative_sections_fts USING fts5(
    section_id UNINDEXED,
    document_code,
    document_title,
    section_heading,
    body,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER normative_sections_fts_delete
AFTER DELETE ON normative_sections
BEGIN
    DELETE FROM normative_sections_fts WHERE section_id = OLD.id;
END;

CREATE TABLE normative_relations (
    id TEXT PRIMARY KEY,
    source_edition_id TEXT NOT NULL,
    target_document_id TEXT NOT NULL,
    target_edition_id TEXT,
    relation_type TEXT NOT NULL
        CHECK (
            relation_type IN (
                'supersedes',
                'amends',
                'references',
                'mandatory_listed_by',
                'voluntary_listed_by',
                'conflicts_with'
            )
        ),
    evidence_locator TEXT NOT NULL,
    rationale TEXT NOT NULL DEFAULT '',
    valid_from TEXT,
    valid_to TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (
        source_edition_id,
        target_document_id,
        target_edition_id,
        relation_type,
        evidence_locator
    ),
    FOREIGN KEY (source_edition_id)
        REFERENCES normative_editions (id)
        ON DELETE CASCADE,
    FOREIGN KEY (target_document_id)
        REFERENCES normative_documents (id)
        ON DELETE CASCADE,
    FOREIGN KEY (target_edition_id)
        REFERENCES normative_editions (id)
        ON DELETE CASCADE
);

CREATE INDEX ix_normative_relations_target
    ON normative_relations (
        target_document_id,
        relation_type,
        valid_from,
        valid_to
    );

CREATE TABLE normative_audit_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    document_id TEXT,
    edition_id TEXT,
    actor_tenant_id TEXT,
    actor_user_id TEXT,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at TEXT NOT NULL,
    FOREIGN KEY (document_id)
        REFERENCES normative_documents (id)
        ON DELETE SET NULL,
    FOREIGN KEY (edition_id)
        REFERENCES normative_editions (id)
        ON DELETE SET NULL
);

CREATE INDEX ix_normative_audit_events_created
    ON normative_audit_events (created_at DESC, id);

PRAGMA user_version = 20;
