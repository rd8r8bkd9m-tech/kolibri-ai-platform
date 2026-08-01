import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (path) =>
	readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("desktop shell is one quiet three-column workspace", async () => {
	const [
		wrapper,
		desktop,
		view,
		auxiliarySurface,
		auxiliaryController,
		layout,
		frame,
		header,
		composer,
		sidebarConstants,
	] = await Promise.all([
			readSource("components/kolibri-shell/workspace-shell.tsx"),
			readSource(
				"components/kolibri-shell/desktop-workspace/desktop-workspace.tsx",
			),
			readSource(
				"components/kolibri-shell/desktop-workspace/desktop-workspace-view.tsx",
			),
			readSource(
				"components/kolibri-shell/desktop-workspace/desktop-auxiliary-canvas.tsx",
			),
			readSource(
				"components/kolibri-shell/desktop-workspace/use-auxiliary-canvas.ts",
			),
			readSource(
				"components/kolibri-shell/desktop-workspace/desktop-workspace-layout.tsx",
			),
			readSource("components/kolibri-workspace/canvas-frame.tsx"),
			readSource("components/kolibri-shell/workspace-header.tsx"),
			readSource("components/assistant-ui/thread/parts/thread-layout.tsx"),
			readSource("components/kolibri-shell/sidebar/constants.ts"),
		]);

	assert.match(wrapper, /import \{ DesktopWorkspace \}/);
	assert.match(wrapper, /return <DesktopWorkspace \/>/);
	assert.doesNotMatch(wrapper, /WorkspaceContextSidebar|desktopContextTool/);

	assert.match(layout, /id=["']workspace-project-navigation["']/);
	assert.match(layout, /defaultSize=\{374\}/);
	assert.match(layout, /minSize=\{288\}[\s\S]{0,80}maxSize=\{410\}/);
	assert.match(layout, /id=["']primary-workspace["'][\s\S]{0,100}minSize=\{640\}/);
	assert.match(layout, /id=["']auxiliary-canvas["']/);
	assert.match(layout, /defaultSize=\{480\}/);
	assert.match(layout, /minSize=\{320\}[\s\S]{0,80}maxSize=\{600\}/);
	assert.match(layout, /aria-label=["']Диалог с Kolibri["']/);
	assert.match(layout, /\{auxiliaryOpen && !auxiliaryFullscreen \? \(/);

	assert.match(desktop, /primaryContent=\{null\}/);
	assert.match(desktop, /primaryOpen=\{false\}/);
	assert.match(desktop, /useAuxiliaryCanvas\(\{/);
	assert.match(auxiliaryController, /placement: ["']right["']/);
	assert.match(auxiliaryController, /KOLIBRI_OPEN_ESTIMATE_EVENT/);
	assert.match(auxiliarySurface, /placement=["']right["']/);
	assert.match(view, /<Thread\b/);
	assert.match(view, /workspaceOpen=\{auxiliary\.open\}/);
	assert.doesNotMatch(desktop, /Рабочий стол/);
	assert.doesNotMatch(sidebarConstants, /Рабочий стол|id:\s*["']desktop["']/);

	assert.match(frame, /data-slot=["']canvas-frame["']/);
	assert.match(frame, /data-slot=["']canvas-fullscreen-toggle["']/);
	assert.match(frame, /tabs\.length > 1 \? \(/);
	assert.match(frame, /role=["']tabpanel["']/);
	assert.match(header, /aria-controls=["']workspace-canvas["']/);
	assert.match(composer, /aria-controls=["']workspace-canvas["']/);
});

test("right canvas exposes exactly the four owner-approved tools", async () => {
	const [contextPanel, canvas, fileManager] = await Promise.all([
		readSource("components/kolibri-workspace/context-panel.tsx"),
		readSource("components/kolibri-workspace/canvas-workspace.tsx"),
		readSource("components/kolibri-workspace/workspace-file-manager.tsx"),
	]);

	const toolIds = [
		...contextPanel.matchAll(
			/\{ id: ["'](review|terminal|browser|files)["'], label:/g,
		),
	].map((match) => match[1]);
	assert.deepEqual(toolIds, ["review", "terminal", "browser", "files"]);
	assert.doesNotMatch(
		contextPanel,
		/calculations|subtask|Расчёты|Дополнительная задача/i,
	);
	assert.doesNotMatch(contextPanel, /role=["']tablist["']/);

	assert.match(canvas, /CONTEXT_PANEL_TABS\.map/);
	assert.match(canvas, /aria-label=["']Инструменты рабочей области["']/);
	assert.match(canvas, /<WorkspaceFileManager\b/);
	assert.match(fileManager, /<select\b/);
	assert.match(fileManager, /placeholder=["']Поиск файлов["']/);
	assert.doesNotMatch(fileManager, /workspace-file-category-tabs/);
	assert.doesNotMatch(fileManager, /Сетка|grid view|list view/i);
});

test("an estimate opens beside chat with version-safe artifact rendering", async () => {
	const [auxiliaryController, artifact, surface, loader, editor] =
		await Promise.all([
		readSource(
			"components/kolibri-shell/desktop-workspace/use-auxiliary-canvas.ts",
		),
		readSource("components/kolibri-workspace/workspace-artifact-editor.tsx"),
		readSource(
			"components/assistant-ui/product-widgets/estimate-document-surface.tsx",
		),
		readSource(
			"components/assistant-ui/product-widgets/estimate-document-common.tsx",
		),
		readSource("components/assistant-ui/product-widgets/estimate-editor.tsx"),
	]);

	assert.match(
		auxiliaryController,
		/const openEstimate[\s\S]{0,2600}openTab\(\{[\s\S]{0,300}content: \{ kind: ["']files["'], category: ["']estimates["'] \}/,
	);
	assert.match(
		auxiliaryController,
		/id: `artifact:\$\{detail\.documentId\}`/,
	);
	assert.match(artifact, /expectedDocumentId=\{file\.documentId\}/);
	assert.match(artifact, /expectedVersion=\{file\.version\}/);
	assert.match(artifact, /key=\{file\.documentId\}/);
	assert.doesNotMatch(artifact, /key=\{file\.version\}/);
	assert.match(loader, /parsed\.data\.documentId !== documentId/);
	assert.match(loader, /parsed\.data\.projectId !== projectId/);
	assert.match(loader, /parsed\.data\.version < minimumVersion/);
	assert.match(surface, /KOLIBRI_DOCUMENTS_CHANGED_EVENT/);
	assert.doesNotMatch(surface, /setEstimate\(null\)/);
	assert.match(surface, /data-document-id=\{estimate\.documentId\}/);
	assert.match(surface, /data-document-version=\{estimate\.version\}/);
	assert.match(editor, /initial\.version <= version/);
	assert.match(editor, /dirty \|\| hasLocalEdits\.current \|\| savingRef\.current/);
	assert.match(editor, /setVersionConflict\(\{/);
});
