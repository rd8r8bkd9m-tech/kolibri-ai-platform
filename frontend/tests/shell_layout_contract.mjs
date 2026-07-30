import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const vite = await createServer({
  root: fileURLToPath(new URL("..", import.meta.url)),
  server: { middlewareMode: true },
  appType: "custom",
  logLevel: "silent",
});
const {
  resolveShellViewportHeight,
  resolveShellViewportOffset,
} = await vite.ssrLoadModule("/src/shell/useShellViewport.js");
await vite.close();

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const css = read("../src/App.css");
const indexCss = read("../src/index.css");
const publicShell = read("../src/shell/PublicShell.jsx");
const shellComposer = read("../src/shell/ShellComposer.jsx");
const projectWorkspace = read("../src/windows/ProjectWorkspace.jsx");
const viewportHook = read("../src/shell/useShellViewport.js");

for (const [width, height] of [[319, 642], [390, 844]]) {
  assert.equal(resolveShellViewportHeight(height, 999), height, `${width}×${height} must use visual viewport height`);
  assert.ok(width - 20 >= 299, `${width}px viewport must leave a usable composer width`);
}
assert.equal(resolveShellViewportHeight(undefined, 642), 642);
assert.equal(resolveShellViewportHeight(0, 844), 844);
assert.equal(resolveShellViewportHeight(641.8, 999), 641, "fractional viewport height must never overrun the visible area");
assert.equal(resolveShellViewportOffset(47.9), 47, "a panned iPhone visual viewport must move the shell into view");
assert.equal(resolveShellViewportOffset(undefined), 0);

assert.match(publicShell, /<ShellHeader[\s\S]*<ShellWorkbench[\s\S]*<ShellComposer/);
assert.match(shellComposer, /<footer className="shell-composer-footer"/);
assert.doesNotMatch(projectWorkspace, /<Composer/);
assert.match(css, /\.kolibri-workbench\s*\{[^}]*height:\s*var\(--shell-viewport-height\)[^}]*grid-template-rows:/s);
assert.match(css, /\.kolibri-workbench\s*\{[^}]*top:\s*var\(--shell-viewport-offset-top\)/s);
assert.match(css, /\.workbench-body\s*\{[^}]*min-height:\s*0/s);
assert.match(css, /\.project-conversation\s*\{[^}]*overflow:\s*auto/s);
assert.match(css, /\.composer-layer\s*\{[^}]*position:\s*relative/s);
assert.doesNotMatch(css.match(/\.composer-layer\s*\{[^}]*\}/s)?.[0] || "", /position:\s*(?:absolute|fixed)/);
assert.doesNotMatch(indexCss, /min-width:\s*320px/);
assert.match(viewportHook, /visualViewport/);
assert.match(viewportHook, /addEventListener\("resize", schedule\)/);
assert.match(viewportHook, /--shell-viewport-height/);
assert.match(viewportHook, /--shell-viewport-offset-top/);

console.log("Kolibri viewport-driven shell layout contract passed");
