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

test("account authentication overlays the preserved primary workspace without a dialog primitive", async () => {
  const [desktop, view, layout, accountSurface, runtime] = await Promise.all([
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace-view.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace-layout.tsx"),
    readSource("components/kolibri-shell/profile-settings-surface.tsx"),
    readSource("app/MyRuntimeProvider.tsx"),
  ]);

  assert.match(desktop, /const\s+\[accountOpen,\s*setAccountOpen\]/);
  assert.match(desktop, /openAccount\s*=\s*useCallback/);
  assert.match(view, /<ProfileSettingsSurface\b/);
  assert.match(view, /accountOpen=\{accountOpen\}/);
  assert.match(layout, /aria-label=["']Личный кабинет Kolibri["']/);
  assert.match(layout, /accountOpen \? \(/);
  assert.match(
    desktop,
    /openAccount[\s\S]{0,420}setAccountOpen\(true\)/,
  );
  assert.doesNotMatch(
    `${desktop}\n${view}\n${layout}`,
    /openAccount[\s\S]{0,420}setCanvasVisible\(/,
  );
  assert.doesNotMatch(`${desktop}\n${view}\n${layout}`, /\bProfileSettingsDialog\b/);

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
