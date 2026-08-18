import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (relativePath) =>
	readFileSync(new URL(`../${relativePath}`, import.meta.url), "utf8");

test("mobile navigation releases web focus before hiding a route or drawer", () => {
	const focus = read("src/accessibility/release-web-focus.ts");
	const header = read("components/shell/mobile-header.tsx");
	const adapter = read("src/components/overlays/DrawerContentAdapter.tsx");
	const drawer = read("src/components/overlays/Sidebar.tsx");
	const layout = read("app/_layout.tsx");

	assert.match(focus, /Platform\.OS !== "web"/);
	assert.match(focus, /activeElement\.blur\(\)/);
	assert.match(
		header,
		/releaseWebFocus\(\);[\s\S]*navigation\.openDrawer\(\)/,
	);
	assert.match(adapter, /const closeDrawer = \(\) => \{[\s\S]*releaseWebFocus\(\)/);
	assert.match(drawer, /router\.push\(path\)/);
	assert.match(drawer, /navigate\("\/account\?client=mobile"\)/);
	assert.match(layout, /blur: releaseWebFocus/);
});

test("mobile production bundling can resolve the shared V3 runtime", () => {
	const metro = read("metro.config.js");

	assert.match(metro, /workspaceRoot = path\.resolve\(projectRoot, "\.\.\/\.\."\)/);
	assert.match(metro, /config\.watchFolders = \[workspaceRoot\]/);
	assert.match(metro, /path\.join\(workspaceRoot, "node_modules"\)/);
});
