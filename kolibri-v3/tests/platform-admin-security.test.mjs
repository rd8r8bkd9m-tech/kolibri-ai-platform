import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");
const read = (relative) =>
  fs.readFileSync(path.join(root, relative), "utf8");

test("platform admin remains a separate server-derived owner-only section", () => {
  const profile = read(
    "components/kolibri-shell/profile-settings-surface.tsx",
  );
  const client = read("lib/platform-admin/client.ts");
  const operationsClient = read(
    "lib/platform-admin/agent-operations-client.ts",
  );
  const section = read(
    "components/kolibri-shell/platform-admin-section.tsx",
  );
  const operationsRoute = read(
    "app/api/superadmin/agent-operations/route.ts",
  );
  const operationsBackend = read("backend/app/agent_operations.py");
  const backend = read("backend/app/identity.py");
  const migration = read(
    "backend/migrations/033_platform_admin_control_plane.sql",
  );

  assert.match(profile, /identity\.user\?\.isPlatformOwner/);
  assert.match(
    profile,
    /\[identity\.user\?\.isPlatformOwner,\s*normalizedSearch\]/,
  );
  assert.match(profile, /section === "platform-admin"/);
  assert.match(
    profile,
    /if \(section === "profile"\) return <ProfileSection \/>/,
  );
  assert.match(profile, /data-slot="account-settings-surface"/);
  assert.doesNotMatch(
    client,
    /isPlatformOwner\s*!==\s*\(value\.role\s*===\s*["']owner["']\)/,
  );
  assert.match(backend, /if not identity\.is_platform_owner:/);
  assert.match(migration, /CREATE TABLE platform_authority_grants/);
  assert.match(migration, /authority_id = 'platform_owner'/);
  assert.match(client, /getPlatformTenantsPage/);
  assert.match(client, /getPlatformUsersPage/);
  assert.match(client, /getPlatformAuditPage/);
  assert.match(client, /SAFE_AUDIT_CURSOR/);
  assert.match(section, /mergeById/);
  assert.match(section, /getAgentOperationsPage/);
  assert.match(section, /Агенты и выполнение/);
  assert.match(section, /danger-full-access|sandboxProfile/);
  assert.match(section, /approvalPolicy/);
  assert.match(section, /Загрузить ещё/);
  assert.doesNotMatch(section, /cursor ещё не подключена/);
  assert.match(
    operationsRoute,
    /["`]\/v1\/platform-admin\/agent-operations\$\{query\}["`]/,
  );
  assert.match(operationsClient, /MAX_SAFE_INTEGER/);
  assert.match(operationsClient, /SAFE_CURSOR/);
  assert.doesNotMatch(
    operationsClient,
    /\b(?:prompt|commandJson|credential|leaseToken|workspacePath)\b/i,
  );
  assert.match(operationsBackend, /require_platform_audit_authority/);
  assert.match(
    operationsBackend,
    /excludes chat messages, prompts, command payloads,/,
  );
});
