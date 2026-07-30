BEGIN IMMEDIATE;

-- A trusted-agent profile is selected server-side.  These nullable columns
-- preserve already accepted developer runs while letting every new run that
-- has an active profile freeze the exact profile and workspace epochs used at
-- acceptance.  Runtime dispatch revalidates these values against live rows.
ALTER TABLE chat_run_execution_contexts
    ADD COLUMN trusted_agent_profile_id TEXT
        REFERENCES trusted_agent_profiles(id) ON DELETE RESTRICT;

ALTER TABLE chat_run_execution_contexts
    ADD COLUMN trusted_agent_profile_epoch INTEGER
        CHECK (
            trusted_agent_profile_epoch IS NULL
            OR trusted_agent_profile_epoch >= 1
        );

ALTER TABLE chat_run_execution_contexts
    ADD COLUMN trusted_agent_workspace_binding_id TEXT
        REFERENCES trusted_agent_workspace_bindings(id) ON DELETE RESTRICT;

ALTER TABLE chat_run_execution_contexts
    ADD COLUMN trusted_agent_workspace_binding_epoch INTEGER
        CHECK (
            trusted_agent_workspace_binding_epoch IS NULL
            OR trusted_agent_workspace_binding_epoch >= 1
        );

CREATE TRIGGER chat_execution_trusted_binding_before_insert
BEFORE INSERT ON chat_run_execution_contexts
WHEN (
    (
        NEW.trusted_agent_profile_id IS NULL
        OR NEW.trusted_agent_profile_epoch IS NULL
        OR NEW.trusted_agent_workspace_binding_id IS NULL
        OR NEW.trusted_agent_workspace_binding_epoch IS NULL
    )
    AND (
        NEW.trusted_agent_profile_id IS NOT NULL
        OR NEW.trusted_agent_profile_epoch IS NOT NULL
        OR NEW.trusted_agent_workspace_binding_id IS NOT NULL
        OR NEW.trusted_agent_workspace_binding_epoch IS NOT NULL
    )
)
OR (
    NEW.trusted_agent_profile_id IS NOT NULL
    AND (
        NEW.execution_mode != 'developer'
        OR NEW.authority_role != 'owner'
        OR NEW.platform_authority_epoch IS NULL
        OR NOT EXISTS (
            SELECT 1
            FROM trusted_agent_profiles AS profile
            JOIN trusted_agent_workspace_bindings AS binding
              ON binding.id = profile.workspace_binding_id
            JOIN platform_authority_grants AS authority
              ON authority.authority_id = profile.authority_id
             AND authority.user_id = profile.owner_user_id
             AND authority.tenant_id = profile.owner_tenant_id
            JOIN chat_runs AS run
              ON run.tenant_id = NEW.tenant_id
             AND run.id = NEW.run_id
            WHERE profile.id = NEW.trusted_agent_profile_id
              AND profile.profile_epoch = NEW.trusted_agent_profile_epoch
              AND profile.workspace_binding_id
                    = NEW.trusted_agent_workspace_binding_id
              AND profile.workspace_binding_epoch
                    = NEW.trusted_agent_workspace_binding_epoch
              AND profile.owner_user_id = NEW.authority_user_id
              AND profile.owner_tenant_id = NEW.tenant_id
              AND profile.authority_epoch = NEW.platform_authority_epoch
              AND profile.lifecycle_status = 'active'
              AND profile.runtime_profile = run.selected_profile
              AND profile.access_mode = NEW.access_mode
              AND profile.sandbox_profile = NEW.sandbox_profile
              AND profile.approval_policy = NEW.approval_policy
              AND profile.approvals_reviewer IS NEW.approvals_reviewer
              AND binding.id = NEW.trusted_agent_workspace_binding_id
              AND binding.workspace_epoch
                    = NEW.trusted_agent_workspace_binding_epoch
              AND binding.owner_user_id = NEW.authority_user_id
              AND binding.owner_tenant_id = NEW.tenant_id
              AND binding.authority_epoch = NEW.platform_authority_epoch
              AND binding.lifecycle_status = 'active'
              AND authority.authority_epoch
                    = NEW.platform_authority_epoch
              AND authority.active = 1
              AND EXISTS (
                  SELECT 1
                  FROM json_each(authority.capabilities_json)
                  WHERE value = 'chat.developer.request'
              )
        )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'trusted agent execution binding is invalid');
END;

CREATE TRIGGER chat_execution_trusted_binding_immutable
BEFORE UPDATE OF
    trusted_agent_profile_id,
    trusted_agent_profile_epoch,
    trusted_agent_workspace_binding_id,
    trusted_agent_workspace_binding_epoch
ON chat_run_execution_contexts
WHEN NEW.trusted_agent_profile_id IS NOT OLD.trusted_agent_profile_id
  OR NEW.trusted_agent_profile_epoch IS NOT OLD.trusted_agent_profile_epoch
  OR NEW.trusted_agent_workspace_binding_id
        IS NOT OLD.trusted_agent_workspace_binding_id
  OR NEW.trusted_agent_workspace_binding_epoch
        IS NOT OLD.trusted_agent_workspace_binding_epoch
BEGIN
    SELECT RAISE(ABORT, 'trusted agent execution binding is immutable');
END;

CREATE INDEX ix_chat_execution_trusted_profile
    ON chat_run_execution_contexts (
        trusted_agent_profile_id,
        trusted_agent_profile_epoch,
        tenant_id,
        run_id
    )
    WHERE trusted_agent_profile_id IS NOT NULL;

PRAGMA user_version = 36;

COMMIT;
