import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

import { initialShellNavigation, shellNavigationReducer } from "../src/shell/shellNavigationModel.js";
import { isMobileFullSurface } from "../src/workbench/mobileWindowModel.js";
import { initialWorkbench, workbenchReducer } from "../src/workbench/reducer.js";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const css = read("../src/App.css");
const publicShell = read("../src/shell/PublicShell.jsx");
const projectWorkspace = read("../src/windows/ProjectWorkspace.jsx");
const mobileWindow = read("../src/workbench/MobileWindow.jsx");
const composer = read("../src/shell/Composer.jsx");
const modeMenu = read("../src/shell/ComposerModeMenu.jsx");
const constants = read("../src/app/constants.js");

const vite = await createServer({
  root: fileURLToPath(new URL("..", import.meta.url)),
  server: { middlewareMode: true },
  appType: "custom",
  logLevel: "silent",
});
const { resolveShellViewportHeight, resolveShellViewportOffset } = await vite.ssrLoadModule("/src/shell/useShellViewport.js");
await vite.close();

// One persistent project chat owns the composer. History and artifacts are
// explicit OS surfaces; another user message must not create another chat.
assert.match(publicShell, /<ShellHeader[\s\S]*<ShellWorkbench[\s\S]*<ShellComposer/);
assert.doesNotMatch(projectWorkspace, /<Composer/);

// A 390×844 iPhone viewport must remain fully viewport-driven, including
// visualViewport panning when the software keyboard is shown.
assert.equal(resolveShellViewportHeight(844, 900), 844);
assert.equal(resolveShellViewportOffset(47.8), 47);
assert.match(css, /\.kolibri-workbench\s*\{[^}]*height:\s*var\(--shell-viewport-height\)/s);
assert.match(css, /\.composer-layer\s*\{[^}]*var\(--safe-bottom\)/s);

// History and Files are sheets; task workspaces and artifacts are full task
// surfaces. A modal sheet must cover the global composer instead of leaving a
// live control underneath aria-modal.
assert.equal(isMobileFullSurface("projects"), false);
assert.equal(isMobileFullSurface("files"), false);
for (const kind of ["workspace", "canvas", "estimate", "pdf", "response", "document", "site", "app"]) {
  assert.equal(isMobileFullSurface(kind), true, `${kind} must remain a mobile task surface`);
}
assert.match(mobileWindow, /aria-modal="true"/);
assert.match(css, /@media \(max-width:\s*760px\)[\s\S]*?\.mobile-window-layer\.is-sheet\s*\{[^}]*position:\s*fixed[^}]*z-index:\s*2800[^}]*top:\s*var\(--system-bar-height\)[^}]*bottom:\s*0/s);
assert.match(css, /\.shell-composer-footer\s*\{[^}]*z-index:\s*2300/s);

// The composer keeps one compact editable row. Execution modes confirmed by
// the backend move into one popover/sheet; unavailable modes never render as
// disabled promises.
assert.match(css, /\.composer-input\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*auto minmax\(0, 1fr\)/s);
assert.match(composer, /<ComposerModeMenu/);
assert.match(composer, /supportedModes\.length > 1/);
assert.doesNotMatch(composer, /disabled=\{!supported\}/);
assert.match(composer, /aria-label="Выбрать инструмент"[\s\S]*?title="Инструменты"/);
assert.match(composer, /aria-label="Выбрать режим работы"[\s\S]*?title=\{`Режим работы:/);
assert.match(composer, /aria-label="Отправить"[\s\S]*?title="Отправить"/);
assert.match(modeMenu, /EXECUTION_MODES\.filter\(\(mode\) => executionModes\.includes\(mode\.id\)\)/);
assert.match(modeMenu, /<small>Модель<\/small><strong>Kolibri<\/strong>/);
assert.match(modeMenu, /<small>Рассуждение<\/small>/);
assert.match(modeMenu, /<small>Скорость<\/small>/);
assert.doesNotMatch(`${modeMenu}\n${constants}`, /gpt-5\.6|label:\s*"Codex"/i);
assert.match(css, /\.execution-mode-trigger\s*\{[^}]*min-width:\s*44px/s);
assert.match(css, /@media \(max-width:\s*760px\)[\s\S]*?\.composer-layer\.is-embedded \.mode-menu,[\s\S]*?position:\s*fixed/s);
assert.match(css, /@media \(max-width:\s*760px\)[\s\S]*?\.execution-mode-trigger,[\s\S]*?width:\s*44px[^}]*justify-content:\s*center/s);

for (const contract of [
  [/button\.shell-brand\s*\{[^}]*min-height:\s*44px/s, "brand trigger"],
  [/\.system-bar nav button,[\s\S]*?\.system-bar nav a\s*\{[^}]*min-width:\s*44px[^}]*height:\s*44px/s, "system actions"],
  [/\.tool-dock button\s*\{[^}]*width:\s*44px[^}]*height:\s*44px/s, "dock actions"],
  [/\.floating-composer > button\s*\{[^}]*width:\s*44px[^}]*height:\s*44px/s, "composer actions"],
  [/\.execution-mode-trigger\s*\{[^}]*min-width:\s*44px/s, "execution mode trigger"],
  [/\.project-view-bar button\s*\{[^}]*min-height:\s*44px/s, "project view actions"],
  [/\.window-actions button,[\s\S]*?\.window-resize\s*\{[^}]*width:\s*44px[^}]*height:\s*44px/s, "window controls"],
]) {
  assert.match(css, contract[0], `${contract[1]} must preserve a 44px hit target`);
}

// Stable IDs and reducer lifecycle prevent duplicate history/windows and make
// minimize, restore, fullscreen and close deterministic.
const history = { id: "projects-window", kind: "projects", title: "История" };
let workbench = workbenchReducer(initialWorkbench, { type: "OPEN", window: history });
workbench = workbenchReducer(workbench, { type: "OPEN", window: history });
assert.equal(workbench.windows.length, 1);
workbench = workbenchReducer(workbench, { type: "MINIMIZE", id: history.id });
assert.equal(workbench.windows[0].minimized, true);
workbench = workbenchReducer(workbench, { type: "FOCUS", id: history.id });
assert.equal(workbench.windows[0].minimized, false);
workbench = workbenchReducer(workbench, { type: "MAXIMIZE", id: history.id });
assert.equal(workbench.windows[0].maximized, true);
workbench = workbenchReducer(workbench, { type: "MAXIMIZE", id: history.id });
assert.equal(workbench.windows[0].maximized, false);
workbench = workbenchReducer(workbench, { type: "DEACTIVATE", id: history.id });
assert.equal(workbench.windows.length, 0);

let navigation = shellNavigationReducer(initialShellNavigation, { type: "MOBILE_TOGGLE" });
assert.equal(navigation.mobileOpen, true);
navigation = shellNavigationReducer(navigation, { type: "DISMISS" });
assert.deepEqual(navigation, initialShellNavigation);

console.log("Kolibri premium one-window Shell release gate passed");
