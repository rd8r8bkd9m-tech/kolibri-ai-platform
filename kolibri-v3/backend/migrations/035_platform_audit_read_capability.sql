BEGIN IMMEDIATE;

-- Agent Operations is a cross-tenant read model. Make that authority
-- explicit instead of treating the legacy tenant "owner" role or even the
-- broader platform.admin capability as an implicit audit grant.
UPDATE platform_authority_grants
SET capabilities_json = json_insert(
        capabilities_json,
        '$[#]',
        'platform.audit.read'
    ),
    updated_at = unixepoch()
WHERE authority_id = 'platform_owner'
  AND active = 1
  AND json_array_length(capabilities_json) < 32
  AND EXISTS (
      SELECT 1
      FROM json_each(platform_authority_grants.capabilities_json)
      WHERE value = 'platform.admin'
  )
  AND NOT EXISTS (
      SELECT 1
      FROM json_each(platform_authority_grants.capabilities_json)
      WHERE value = 'platform.audit.read'
  );

PRAGMA user_version = 35;

COMMIT;
