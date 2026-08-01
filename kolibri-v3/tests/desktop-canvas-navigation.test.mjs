import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (path) =>
	readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("desktop navigation keeps chat primary and opens product surfaces in the auxiliary canvas", async () => {
	const [workspace, auxiliary, layout] = await Promise.all([
		readSource(
			"components/kolibri-shell/desktop-workspace/desktop-workspace.tsx",
		),
		readSource(
			"components/kolibri-shell/desktop-workspace/desktop-auxiliary-canvas.tsx",
		),
		readSource(
			"components/kolibri-shell/desktop-workspace/desktop-workspace-layout.tsx",
		),
	]);

	assert.doesNotMatch(workspace, /PrimaryWorkspaceSurface/);
	assert.match(workspace, /auxiliary\.openProjects\(\)/);
	assert.match(workspace, /auxiliary\.openReferences\(\)/);
	assert.match(workspace, /auxiliary\.openFiles\(/);
	assert.match(workspace, /primaryOpen=\{false\}/);
	assert.match(auxiliary, /<ProjectsOverview/);
	assert.match(auxiliary, /<ReferenceCatalog/);
	assert.match(auxiliary, /onOpenProject=\{onOpenProject\}/);
	assert.match(layout, /chatHidden\s*=\s*primaryOpen\s*\|\|\s*accountOpen/);
});

test("desktop conversation switching hydrates before publishing the new projection", async () => {
	const provider = await readSource("app/MyRuntimeProvider.tsx");
	const hydrationStart = provider.indexOf(
		"const hydration = hydrateProductChatMessages(",
	);
	const projectionCommit = provider.indexOf(
		"commitProjection({",
		hydrationStart,
	);

	assert.ok(hydrationStart >= 0, "thread switch must hydrate target messages");
	assert.ok(projectionCommit > hydrationStart, "selection must publish after hydration");
});
