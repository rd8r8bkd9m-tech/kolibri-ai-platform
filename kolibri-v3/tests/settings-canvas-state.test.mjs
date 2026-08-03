import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (path) =>
	readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("settings is an isolated state of the single SPA canvas", async () => {
	const [surface, controller, workspace, layout] = await Promise.all([
		readSource(
			"components/kolibri-shell/desktop-workspace/desktop-auxiliary-canvas.tsx",
		),
		readSource(
			"components/kolibri-shell/desktop-workspace/use-auxiliary-canvas.ts",
		),
		readSource(
			"components/kolibri-shell/desktop-workspace/desktop-workspace.tsx",
		),
		readSource(
			"components/kolibri-shell/desktop-workspace/desktop-workspace-layout.tsx",
		),
	]);

	const settingsStart = surface.indexOf(
		'if (activeTab.content.kind === "settings")',
	);
	const settingsEnd = surface.indexOf("\n\tconst project", settingsStart);
	assert.ok(settingsStart >= 0 && settingsEnd > settingsStart);

	const settingsRenderer = surface.slice(settingsStart, settingsEnd);
	assert.match(settingsRenderer, /data-canvas-kind=["']settings["']/);
	assert.match(settingsRenderer, /<ProfileSettingsSurface\b/);
	assert.doesNotMatch(settingsRenderer, /<CanvasFrame\b/);
	assert.doesNotMatch(settingsRenderer, /<CanvasWorkspace\b/);
	assert.doesNotMatch(settingsRenderer, /headerTabs|onProjectSelect/);

	assert.match(
		controller,
		/const PRIMARY_CANVAS_SURFACE_ID = ["']workspace:primary-surface["']/,
	);
	assert.match(
		controller,
		/current\.tabs\.filter\(\(tab\) => tab\.placement !== ["']primary["']\)/,
	);
	assert.match(controller, /placement: ["']primary["']/);
	assert.match(
		workspace,
		/primaryContent=\{auxiliary\.primaryOpen \? auxiliaryCanvas : null\}/,
	);
	assert.match(workspace, /primaryOpen=\{auxiliary\.primaryOpen\}/);
	assert.match(layout, /const chatHidden = primaryOpen/);
	assert.doesNotMatch(
		`${workspace}\n${controller}`,
		/router\.(?:push|replace)\(/,
	);
});

test("settings temporarily owns the canvas width and restores navigation", async () => {
	const [workspace, layout, view] = await Promise.all([
		readSource(
			"components/kolibri-shell/desktop-workspace/desktop-workspace.tsx",
		),
		readSource(
			"components/kolibri-shell/desktop-workspace/desktop-workspace-layout.tsx",
		),
		readSource(
			"components/kolibri-shell/desktop-workspace/desktop-workspace-view.tsx",
		),
	]);

	assert.match(
		workspace,
		/auxiliary\.open && auxiliary\.activeTab\?\.content\.kind === ["']settings["']/,
	);
	assert.match(workspace, /navigationBeforeSettingsRef/);
	assert.match(workspace, /if \(navigationOpen\) setNavigationOpen\(false\)/);
	assert.match(workspace, /setNavigationOpen\(previousNavigationState\)/);
	assert.match(layout, /navigationOpen && !auxiliaryFullscreen/);

	const composerInstances = view.match(/<ThreadComposer\b/g) ?? [];
	assert.equal(composerInstances.length, 1);
	assert.match(
		view,
		/data-composer-surface=\{primaryOpen \? ["']canvas["'] : ["']chat["']\}/,
	);
});
