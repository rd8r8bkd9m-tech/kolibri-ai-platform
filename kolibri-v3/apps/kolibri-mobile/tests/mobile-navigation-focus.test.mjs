import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (relativePath) =>
	readFileSync(new URL(`../${relativePath}`, import.meta.url), "utf8");

test("mobile navigation releases web focus before hiding a route or drawer", () => {
	const focus = read("src/accessibility/release-web-focus.ts");
	const header = read("components/shell/mobile-header.tsx");
	const drawer = read("components/thread-list/drawer-content.tsx");
	const layout = read("app/_layout.tsx");

	assert.match(focus, /Platform\.OS !== "web"/);
	assert.match(focus, /activeElement\.blur\(\)/);
	assert.match(
		header,
		/releaseWebFocus\(\);[\s\S]*navigation\.openDrawer\(\)/,
	);
	assert.match(drawer, /const closeDrawer = \(\) => \{[\s\S]*releaseWebFocus\(\)/);
	assert.match(
		drawer,
		/releaseWebFocus\(\);[\s\S]*navigation\.navigate\("estimates"/,
	);
	assert.match(
		drawer,
		/releaseWebFocus\(\);[\s\S]*navigation\.navigate\("account"/,
	);
	assert.match(layout, /blur: releaseWebFocus/);
});
