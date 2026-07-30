import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const APP_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

const readSource = (relativePath) =>
  readFile(path.join(APP_ROOT, relativePath), "utf8");

test("all developer providers share one versioned activity UI contract", async () => {
  const [runtime, codex, mimo, provider, activityUi] = await Promise.all([
    readSource("backend/app/agent_runtime.py"),
    readSource("backend/app/codex_app_server.py"),
    readSource("backend/app/mimo_developer_runtime.py"),
    readSource("app/MyRuntimeProvider.tsx"),
    readSource("components/assistant-ui/developer-activity-tool.tsx"),
  ]);

  assert.match(runtime, /AGENT_ACTIVITY_SCHEMA_ID\s*=\s*"kolibri\.agent-activity"/);
  assert.match(runtime, /def canonical_runtime_activity\(/);
  assert.match(codex, /canonical_runtime_activity\(phase,\s*item\)/);
  assert.match(mimo, /canonical_runtime_activity\(phase,\s*item\)/);
  assert.match(provider, /<DeveloperActivityToolUIs\s*\/>/);
  assert.equal(
    (provider.match(/<DeveloperActivityToolUIs\s*\/>/g) ?? []).length,
    1,
  );
  assert.doesNotMatch(activityUi, /\bCodex\b|\bMiMo\b/);
  assert.match(activityUi, /toolName:\s*"developer_command"/);
  assert.match(activityUi, /toolName:\s*"developer_file_change"/);
  assert.match(activityUi, /Вывод команды/);
});
