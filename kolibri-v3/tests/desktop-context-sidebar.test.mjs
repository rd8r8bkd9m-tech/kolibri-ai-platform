import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (path) =>
	readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("desktop shell has one shared central Canvas and an optional tool panel", async () => {
	const [
		wrapper,
		desktop,
		view,
		auxiliarySurface,
		auxiliaryController,
		layout,
		frame,
		canvas,
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
			readSource("components/kolibri-workspace/canvas-workspace.tsx"),
			readSource("components/kolibri-shell/workspace-header.tsx"),
			readSource("components/assistant-ui/thread/parts/thread-layout.tsx"),
			readSource("components/kolibri-shell/sidebar/constants.ts"),
		]);

	assert.match(wrapper, /import \{ DesktopWorkspace \}/);
	assert.match(wrapper, /return <DesktopWorkspace[^>]*\/>/);
	assert.doesNotMatch(wrapper, /WorkspaceContextSidebar|desktopContextTool/);

	assert.match(layout, /id=["']workspace-project-navigation["']/);
	// Redesign spec §5: navigation default 320, range 280–360.
	assert.match(layout, /defaultSize=\{320\}/);
	assert.match(layout, /minSize=\{280\}[\s\S]{0,80}maxSize=\{360\}/);
	assert.match(layout, /id=["']primary-workspace["'][\s\S]{0,100}minSize=\{640\}/);
	assert.match(layout, /id=["']auxiliary-canvas["']/);
	// Redesign spec §5: auxiliary default 400, range 320–640.
	assert.match(layout, /defaultSize=\{400\}/);
	assert.match(layout, /minSize=\{320\}[\s\S]{0,80}maxSize=\{640\}/);
	assert.match(layout, /aria-label=["']Диалог с Kolibri["']/);
	assert.match(layout, /\{auxiliaryOpen && !auxiliaryFullscreen \? \(/);

	assert.match(
		desktop,
		/primaryContent=\{auxiliary\.primaryOpen \? auxiliaryCanvas : null\}/,
	);
	assert.match(desktop, /primaryOpen=\{auxiliary\.primaryOpen\}/);
	assert.match(desktop, /useAuxiliaryCanvas\(\{/);
	assert.match(auxiliaryController, /placement = ["']right["']/);
	assert.match(auxiliaryController, /PRIMARY_CANVAS_SURFACE_ID/);
	assert.match(
		auxiliaryController,
		/open && activeTab\?\.placement === ["']right["'] && Boolean\(activeTab\.maximized\)/,
	);
	assert.match(
		auxiliaryController,
		/!tab\.minimized && tab\.placement === activeTab\.placement/,
	);
	assert.match(
		auxiliaryController,
		/activeTab\.placement !== ["']right["']/,
	);
	assert.match(
		auxiliaryController,
		/find\(\(tab\) => tab\.placement === ["']right["'] && !tab\.minimized\)/,
	);
	assert.match(auxiliaryController, /KOLIBRI_OPEN_ESTIMATE_EVENT/);
	assert.match(auxiliarySurface, /placement=\{activeTab\.placement\}/);
	assert.match(view, /<Thread\b/);
	assert.match(view, /<ThreadComposer\b/);
	assert.match(view, /workspaceOpen=\{rightWorkspaceOpen\}/);
	assert.match(
		view,
		/primaryOpen \? undefined : auxiliary\.toggle/,
	);
	assert.match(view, /`Диалог · \$\{activeCanvasLabel/);
	assert.doesNotMatch(desktop, /Рабочий стол/);
	assert.doesNotMatch(sidebarConstants, /Рабочий стол|id:\s*["']desktop["']/);

	assert.match(frame, /data-slot=["']canvas-frame["']/);
	assert.match(frame, /headerActions/);
	assert.match(frame, /headerTabs/);
	assert.match(frame, /overflow-x-auto/);
	assert.match(canvas, /activeHeaderTabId/);
	assert.match(canvas, /onHeaderTabSelect/);
	// Redesign spec §9: canvas header keeps at most three actions; the
	// project picker lives only in the workspace header.
	assert.doesNotMatch(canvas, /WorkspaceProjectPicker/);
	assert.match(header, /<WorkspaceProjectPicker\b/);
	assert.match(frame, /data-slot=["']canvas-fullscreen-toggle["']/);
	assert.match(frame, /tabs\.length > 0 \? \(/);
	assert.match(frame, /role=["']tabpanel["']/);
	assert.match(auxiliaryController, /const dismiss = useCallback/);
	assert.match(auxiliarySurface, /onClose=\{controller\.close\}/);
	assert.match(auxiliarySurface, /data-canvas-kind=["']projects["']/);
	assert.match(
		auxiliarySurface,
		/data-canvas-kind=\{activeFile \? ["']artifact["'] : ["']documents["']\}/,
	);
	assert.match(auxiliarySurface, /data-canvas-kind=["']references["']/);
	assert.match(header, /aria-controls=["']workspace-canvas["']/);
	assert.match(header, /data-context-launcher=["']header["']/);
	assert.match(composer, /aria-controls=["']workspace-canvas["']/);
});

test("right canvas exposes exactly the four owner-approved tools", async () => {
	const [contextPanel, canvas, frame, fileManager] = await Promise.all([
		readSource("components/kolibri-workspace/context-panel.tsx"),
		readSource("components/kolibri-workspace/canvas-workspace.tsx"),
		readSource("components/kolibri-workspace/canvas-frame.tsx"),
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
	assert.match(frame, /aria-label=["']Инструменты рабочей области["']/);
	// Redesign spec §8: the static «Инструменты» launcher page is removed;
	// the canvas falls back to the Files surface instead.
	assert.doesNotMatch(canvas, /WorkspaceLauncher/);
	assert.match(canvas, /<WorkspaceFileManager\b/);
	assert.doesNotMatch(canvas, /WorkspaceProjectPicker/);
	assert.match(fileManager, /<select\b/);
	assert.match(fileManager, /placeholder=["']Поиск файлов["']/);
	assert.doesNotMatch(fileManager, /workspace-file-category-tabs/);
	assert.doesNotMatch(fileManager, /Сетка|grid view|list view/i);
});

test("an estimate opens in the shared Canvas with version-safe artifact rendering", async () => {
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
			"lib/estimate/document.ts",
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
	assert.match(loader, /parsed\.data\.documentId !== identity\.documentId/);
	assert.match(loader, /parsed\.data\.projectId !== identity\.projectId/);
	assert.match(loader, /parsed\.data\.version < identity\.minimumVersion/);
	assert.match(surface, /KOLIBRI_DOCUMENTS_CHANGED_EVENT/);
	assert.doesNotMatch(surface, /setEstimate\(null\)/);
	assert.match(surface, /data-document-id=\{estimate\.documentId\}/);
	assert.match(surface, /data-document-version=\{estimate\.version\}/);
	assert.match(editor, /initial\.version <= version/);
	assert.match(editor, /dirty \|\| hasLocalEdits\.current \|\| savingRef\.current/);
	assert.match(editor, /setVersionConflict\(\{/);
});
