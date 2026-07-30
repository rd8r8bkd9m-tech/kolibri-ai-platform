import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");
const read = (relative) =>
  fs.readFileSync(path.join(root, relative), "utf8");

test("owner live refresh is bounded and runs only for a visible document", () => {
  const refresh = read("lib/platform-admin/visible-document-refresh.ts");

  assert.match(refresh, /MINIMUM_REFRESH_MS\s*=\s*5_000/);
  assert.match(refresh, /MAXIMUM_REFRESH_MS\s*=\s*60_000/);
  assert.match(refresh, /PLATFORM_ADMIN_LIVE_REFRESH_MS\s*=\s*10_000/);
  assert.match(refresh, /document\.visibilityState !== ["']visible["']/);
  assert.match(refresh, /addEventListener\(["']visibilitychange["']/);
  assert.match(refresh, /removeEventListener\(/);
  assert.match(refresh, /new AbortController\(\)/);
  assert.match(refresh, /activeController\?\.abort\(\)/);
  assert.match(refresh, /Math\.max\(current\.length, incoming\.length\)/);
  assert.match(refresh, /\.slice\(0, maximumItems\)/);
  assert.doesNotMatch(refresh, /\bNotification\b|requestPermission/);
});

test("live operation refresh merges first-page truth without resetting pagination", () => {
  const section = read(
    "components/kolibri-shell/platform-admin-section.tsx",
  );

  assert.match(section, /useVisibleDocumentRefresh\(refreshLiveAgentOperations\)/);
  assert.match(
    section,
    /getAgentOperationsPage\(undefined,\s*signal\)/,
  );
  assert.match(
    section,
    /mergeBoundedFirstPage\(\s*current\.operations,\s*page\.items,\s*agentOperationKey/,
  );
  const liveRefresh = section.slice(
    section.indexOf("const refreshLiveAgentOperations"),
    section.indexOf("useVisibleDocumentRefresh(refreshLiveAgentOperations)"),
  );
  assert.doesNotMatch(liveRefresh, /operationCursor:/);
  assert.match(liveRefresh, /providers:\s*page\.availability\.providers/);
  assert.match(liveRefresh, /runtimes:\s*page\.availability\.runtimes/);
  assert.match(liveRefresh, /===\s*["']running["'][\s\S]*?!==\s*["']running["']/);
  assert.match(section, /aria-live=["']polite["']/);
  assert.match(section, /aria-atomic=["']true["']/);
  assert.match(section, /role=["']status["']/);
  assert.match(section, /Автообновление работает при активной вкладке/);
  assert.doesNotMatch(
    section,
    /\b(?:cancelAgentOperation|deployAgentOperation|requestPermission)\b/,
  );
});

test("trusted-agent audit refreshes its first page without replacing its cursor", () => {
  const panel = read(
    "components/kolibri-shell/trusted-agent-admin.tsx",
  );

  assert.match(panel, /useVisibleDocumentRefresh\(refreshLiveAudit\)/);
  assert.match(panel, /getTrustedAgentAuditPage\(undefined,\s*signal\)/);
  assert.match(
    panel,
    /audit:\s*mergeBoundedFirstPage\(\s*current\.audit,\s*page\.items/,
  );
  const liveRefresh = panel.slice(
    panel.indexOf("const refreshLiveAudit"),
    panel.indexOf("useVisibleDocumentRefresh(refreshLiveAudit)"),
  );
  assert.doesNotMatch(liveRefresh, /auditCursor:/);
  assert.doesNotMatch(panel, /\bNotification\b|requestPermission/);
});
