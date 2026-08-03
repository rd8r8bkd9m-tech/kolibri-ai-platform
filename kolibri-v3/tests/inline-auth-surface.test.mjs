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

test("account authentication renders in the shared settings canvas without a dialog primitive", async () => {
  const [desktop, view, layout, auxiliary, accountSurface, runtime] = await Promise.all([
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace-view.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace-layout.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-auxiliary-canvas.tsx"),
    readSource("components/kolibri-shell/profile-settings-surface.tsx"),
    readSource("app/MyRuntimeProvider.tsx"),
  ]);

  assert.match(desktop, /const openSettings = useCallback/);
  assert.match(desktop, /auxiliary\.openSettings\(section\)/);
  assert.match(auxiliary, /<ProfileSettingsSurface\b/);
  assert.match(auxiliary, /activeSection=\{settingsSection\}/);
  assert.match(layout, /data-slot=["']primary-product-surface["']/);
  assert.match(layout, /primaryOpen \? \(/);
  assert.doesNotMatch(
    `${desktop}\n${view}\n${layout}`,
    /openSettings[\s\S]{0,420}setCanvasVisible\(/,
  );
  assert.doesNotMatch(`${desktop}\n${view}\n${layout}`, /\bProfileSettingsDialog\b/);

  assert.match(accountSurface, /data-slot=["']settings-canvas-surface["']/);
  assert.match(accountSurface, /<AuthPanel\s+onAuthenticated=\{\(\) => undefined\}\s*\/>/);
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
