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

test("account authentication replaces the primary workspace without a modal", async () => {
  const [shell, accountSurface, runtime] = await Promise.all([
    readSource("components/kolibri-shell/workspace-shell.tsx"),
    readSource("components/kolibri-shell/profile-settings-surface.tsx"),
    readSource("app/MyRuntimeProvider.tsx"),
  ]);

  assert.match(shell, /const\s+\[accountSurfaceOpen,\s*setAccountSurfaceOpen\]/);
  assert.match(
    shell,
    /const\s+primaryContent\s*=\s*accountSurfaceOpen\s*\?/,
  );
  assert.match(shell, /<ProfileSettingsSurface\b/);
  assert.match(
    shell,
    /openAccountSettings[\s\S]{0,260}setCanvasVisible\(false\)[\s\S]{0,180}setAccountSurfaceOpen\(true\)/,
  );
  assert.doesNotMatch(shell, /\bProfileSettingsDialog\b/);

  assert.match(accountSurface, /data-slot=["']account-settings-surface["']/);
  assert.match(accountSurface, /<AuthPanel\s+onAuthenticated=\{onClose\}\s*\/>/);
  assert.match(
    accountSurface,
    /await\s+identity\.(?:login|register)[\s\S]{0,220}onAuthenticated\(\)/,
  );
  assert.match(accountSurface, /minLength=\{12\}/);
  assert.doesNotMatch(accountSurface, /@\/components\/ui\/dialog/);
  assert.doesNotMatch(accountSurface, /<Dialog(?:Content|Close|Title)?\b/);

  assert.match(
    runtime,
    /if\s*\(\s*!authenticated\s*\)\s*\{[\s\S]{0,260}return\s+applyCanonicalThreads\(\[\]\)/,
  );
  assert.doesNotMatch(
    runtime,
    /Product Chat requires an authenticated session/,
  );
});
