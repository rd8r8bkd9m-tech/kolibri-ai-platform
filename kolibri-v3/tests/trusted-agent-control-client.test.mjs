import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");
const read = (relative) =>
  fs.readFileSync(path.join(root, relative), "utf8");

test("trusted-agent client exposes only the bounded public authority contract", () => {
  const client = read("lib/platform-admin/trusted-agents-client.ts");
  const platformAdminClient = read("lib/platform-admin/client.ts");

  assert.match(client, /platformAdminRequest/);
  assert.match(platformAdminClient, /credentials:\s*["']same-origin["']/);
  assert.match(platformAdminClient, /withCsrfHeader/);
  assert.match(client, /\^sha256:\[0-9a-f\]\{64\}\$/);
  assert.match(client, /value\.items\.length > MAX_PAGE_SIZE/);
  assert.match(client, /value\.capabilities\.length !== 1/);
  assert.match(client, /value\.approvalsReviewer !== null/);
  assert.match(client, /value\.maxConcurrency !== 1/);
  assert.match(client, /getTrustedAgentAuditPage/);
  assert.match(client, /TRUSTED_AGENT_AUDIT_CURSOR/);
  assert.ok(client.includes('normalized.includes("/")'));
  assert.ok(client.includes('normalized.includes("\\\\")'));
  assert.ok(client.includes('normalized.includes("://")'));
  assert.match(client, /body:\s*JSON\.stringify\(\{\s*environment:/);
  assert.match(
    client,
    /body:\s*JSON\.stringify\(\{\s*workspaceBindingId,[\s\S]*?maxConcurrency:\s*1/,
  );
  assert.match(client, /accessMode:\s*["']full["']/);
  assert.match(client, /sandboxProfile:\s*["']danger-full-access["']/);
  assert.match(client, /approvalPolicy:\s*["']never["']/);
  assert.doesNotMatch(
    client,
    /\b(?:workspacePath|filesystemPath|apiKey|password|secret|credential)\b/i,
  );
});

test("trusted-agent BFF proxies only fixed backend resources with bounded writes", () => {
  const bindingCollection = read(
    "app/api/superadmin/trusted-agents/workspace-bindings/route.ts",
  );
  const bindingRevoke = read(
    "app/api/superadmin/trusted-agents/workspace-bindings/[bindingId]/revoke/route.ts",
  );
  const profileCollection = read(
    "app/api/superadmin/trusted-agents/profiles/route.ts",
  );
  const profileRevoke = read(
    "app/api/superadmin/trusted-agents/profiles/[profileId]/revoke/route.ts",
  );
  const identifiers = read(
    "app/api/superadmin/trusted-agents/identifiers.ts",
  );
  const audit = read(
    "app/api/superadmin/trusted-agents/audit/route.ts",
  );
  const routes = [
    bindingCollection,
    bindingRevoke,
    profileCollection,
    profileRevoke,
    audit,
  ].join("\n");

  assert.match(
    bindingCollection,
    /\/v1\/platform-admin\/trusted-agents\/workspace-bindings/,
  );
  assert.match(
    profileCollection,
    /\/v1\/platform-admin\/trusted-agents\/profiles/,
  );
  assert.match(bindingRevoke, /isWorkspaceBindingId\(bindingId\)/);
  assert.match(profileRevoke, /isTrustedAgentProfileId\(profileId\)/);
  assert.match(
    audit,
    /\/v1\/platform-admin\/trusted-agents\/audit\$\{query\}/,
  );
  assert.match(identifiers, /\^wsb_\[0-9a-f\]\{32\}\$/);
  assert.match(identifiers, /\^tap_\[0-9a-f\]\{32\}\$/);
  assert.equal(
    (routes.match(/return proxyV3JsonRequest\(/g) ?? []).length,
    7,
    "every collection action and revoke action uses the shared proxy",
  );
  assert.equal(
    (routes.match(/maxRequestBytes:/g) ?? []).length,
    4,
    "every mutation route must bound its request body",
  );
  assert.doesNotMatch(
    routes,
    /\b(?:Authorization|serviceToken|workspacePath|apiKey|password|secret|credential)\b/i,
  );
});

test("owner console manages durable profiles without per-command approval UI", () => {
  const panel = read(
    "components/kolibri-shell/trusted-agent-admin.tsx",
  );
  const section = read(
    "components/kolibri-shell/platform-admin-section.tsx",
  );

  assert.match(section, /<TrustedAgentAdmin\s*\/>/);
  assert.match(section, /Полномочия доверенных агентов/);
  assert.match(panel, /createTrustedAgentWorkspaceBinding/);
  assert.match(panel, /createTrustedAgentProfile/);
  assert.match(panel, /revokeTrustedAgentWorkspaceBinding/);
  assert.match(panel, /revokeTrustedAgentProfile/);
  assert.match(panel, /getTrustedAgentAuditPage/);
  assert.match(panel, /Журнал полномочий агентов/);
  assert.match(panel, /danger-full-access/);
  assert.match(panel, /approval=never/);
  assert.match(panel, /не требуется подтверждение каждой команды/);
  assert.match(panel, /Подтвердить отзыв/);
  assert.doesNotMatch(panel, /window\.confirm|workspacePath|apiKey|password/i);
});
