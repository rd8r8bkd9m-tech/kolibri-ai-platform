PRAGMA foreign_keys = ON;

-- Generative UI rejects the generic key `url` at every nesting level. V18
-- estimate messages stored trusted price provenance under that key, so their
-- otherwise valid EstimateEditor cards soft-failed on history hydration.
-- Rebuild only the affected rows array and expose the allowlisted `sourceUrl`
-- field. Internal immutable estimate snapshots keep their original schema and
-- are adapted by the read model.
WITH rebuilt_messages AS (
    SELECT
        message.tenant_id,
        message.id,
        json_set(
            message.content_json,
            '$.args.rows',
            json(
                (
                    SELECT json_group_array(
                        json(
                            CASE
                                WHEN json_type(
                                    item.value,
                                    '$.enginePriceProvenance.url'
                                ) = 'text'
                                THEN json_remove(
                                    json_set(
                                        item.value,
                                        '$.enginePriceProvenance.sourceUrl',
                                        json_extract(
                                            item.value,
                                            '$.enginePriceProvenance.url'
                                        )
                                    ),
                                    '$.enginePriceProvenance.url'
                                )
                                ELSE item.value
                            END
                        )
                    )
                    FROM json_each(
                        message.content_json,
                        '$.args.rows'
                    ) AS item
                )
            )
        ) AS migrated_content_json
    FROM chat_messages AS message
    WHERE message.role = 'assistant'
      AND json_valid(message.content_json)
      AND json_extract(message.content_json, '$.args.$type')
          = 'EstimateEditor'
      AND EXISTS (
          SELECT 1
          FROM json_each(
              message.content_json,
              '$.args.rows'
          ) AS item
          WHERE json_type(
              item.value,
              '$.enginePriceProvenance.url'
          ) = 'text'
      )
)
UPDATE chat_messages
SET content_json = (
    SELECT migrated_content_json
    FROM rebuilt_messages
    WHERE rebuilt_messages.tenant_id = chat_messages.tenant_id
      AND rebuilt_messages.id = chat_messages.id
)
WHERE EXISTS (
    SELECT 1
    FROM rebuilt_messages
    WHERE rebuilt_messages.tenant_id = chat_messages.tenant_id
      AND rebuilt_messages.id = chat_messages.id
);

PRAGMA user_version = 19;
