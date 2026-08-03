PRAGMA foreign_keys = ON;

ALTER TABLE document_slots
ADD COLUMN estimate_lifecycle_status TEXT
    CHECK (
        estimate_lifecycle_status IS NULL
        OR estimate_lifecycle_status IN (
            'draft', 'needs_input', 'calculating', 'ready', 'failed'
        )
    );

UPDATE document_slots
SET estimate_lifecycle_status = CASE
    WHEN content_json IS NULL
      OR json_array_length(content_json, '$.rows') = 0
      OR NULLIF(TRIM(json_extract(content_json, '$.region')), '') IS NULL
      OR json_extract(content_json, '$.region') = 'Регион не указан'
        THEN 'needs_input'
    WHEN status = 'ready' THEN 'ready'
    WHEN status = 'revoked' THEN 'failed'
    ELSE 'draft'
END
WHERE slot_type = 'estimate';

ALTER TABLE estimate_versions
ADD COLUMN lifecycle_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (
        lifecycle_status IN (
            'draft', 'needs_input', 'calculating', 'ready', 'failed'
        )
    );

UPDATE estimate_versions
SET lifecycle_status = CASE
    WHEN json_array_length(content_json, '$.rows') = 0
      OR NULLIF(TRIM(json_extract(content_json, '$.region')), '') IS NULL
      OR json_extract(content_json, '$.region') = 'Регион не указан'
        THEN 'needs_input'
    WHEN status = 'ready' THEN 'ready'
    WHEN status = 'revoked' THEN 'failed'
    ELSE 'draft'
END;

PRAGMA user_version = 48;
