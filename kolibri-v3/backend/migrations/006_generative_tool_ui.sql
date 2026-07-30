PRAGMA foreign_keys = OFF;

ALTER TABLE chat_messages
    ADD COLUMN content_json TEXT
        CHECK (content_json IS NULL OR json_valid(content_json));

ALTER TABLE chat_run_events RENAME TO chat_run_events_v5;

CREATE TABLE chat_run_events (
    tenant_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL
        CHECK (sequence >= 1),
    event_type TEXT NOT NULL
        CHECK (
            event_type IN (
                'RUN_STARTED',
                'TEXT_MESSAGE_START',
                'TEXT_MESSAGE_CONTENT',
                'TEXT_MESSAGE_END',
                'TOOL_CALL_START',
                'TOOL_CALL_ARGS',
                'TOOL_CALL_END',
                'TOOL_CALL_RESULT',
                'RUN_FINISHED',
                'RUN_ERROR'
            )
        ),
    event_json TEXT NOT NULL
        CHECK (json_valid(event_json)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, event_id),
    UNIQUE (tenant_id, run_id, sequence),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES chat_runs (tenant_id, id)
        ON DELETE CASCADE
);

INSERT INTO chat_run_events (
    tenant_id,
    event_id,
    run_id,
    sequence,
    event_type,
    event_json,
    created_at
)
SELECT
    tenant_id,
    event_id,
    run_id,
    sequence,
    event_type,
    event_json,
    created_at
FROM chat_run_events_v5;

DROP TABLE chat_run_events_v5;

CREATE INDEX ix_chat_run_events_tenant_run_sequence
    ON chat_run_events (tenant_id, run_id, sequence);

PRAGMA foreign_keys = ON;
PRAGMA user_version = 6;
