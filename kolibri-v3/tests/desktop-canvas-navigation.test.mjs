import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (path) =>
	readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("desktop destinations replace one central Canvas state and a thread click returns to chat", async () => {
	const [workspace, auxiliary, layout, controller, sidebar, header] =
		await Promise.all([
		readSource(
			"components/kolibri-shell/desktop-workspace/desktop-workspace.tsx",
		),
		readSource(
			"components/kolibri-shell/desktop-workspace/desktop-auxiliary-canvas.tsx",
		),
		readSource(
			"components/kolibri-shell/desktop-workspace/desktop-workspace-layout.tsx",
		),
		readSource(
			"components/kolibri-shell/desktop-workspace/use-auxiliary-canvas.ts",
		),
		readSource(
			"components/kolibri-shell/sidebar/workspace-sidebar-navigation.tsx",
		),
		readSource("components/kolibri-shell/workspace-header.tsx"),
	]);

	assert.doesNotMatch(workspace, /PrimaryWorkspaceSurface/);
	assert.match(workspace, /auxiliary\.openProjects\(\)/);
	assert.match(workspace, /auxiliary\.openReferences\(\)/);
	assert.match(workspace, /auxiliary\.openFiles\(/);
	assert.match(
		workspace,
		/primaryContent=\{auxiliary\.primaryOpen \? auxiliaryCanvas : null\}/,
	);
	assert.match(workspace, /primaryOpen=\{auxiliary\.primaryOpen\}/);
	assert.match(workspace, /const activeDestination = !auxiliary\.open/);
	assert.match(
		workspace,
		/Active workspace surface: \$\{workspaceContext\.surface\}/,
	);
	assert.doesNotMatch(workspace, /Primary surface: chat/);
	assert.match(auxiliary, /<ProjectsOverview/);
	assert.match(auxiliary, /<ReferenceCatalog/);
	assert.match(auxiliary, /<WorkspaceFileManager/);
	assert.match(auxiliary, /<WorkspaceArtifactEditor/);
	assert.match(auxiliary, /data-canvas-kind=["']projects["']/);
	assert.match(
		auxiliary,
		/data-canvas-kind=\{activeFile \? ["']artifact["'] : ["']documents["']\}/,
	);
	assert.match(auxiliary, /data-canvas-kind=["']references["']/);
	assert.match(auxiliary, /onOpenProject=\{onSelectProject\}/);
	assert.match(auxiliary, /onProjectSelect=\{onSelectProject\}/);
	assert.match(workspace, /auxiliary\.selectProject\(project\)/);
	assert.match(controller, /const selectProject = useCallback/);
	assert.match(controller, /updateCanvasTab\(current, activeTab\.id/);
	assert.match(
		controller,
		/id: placement === ["']primary["'] \? PRIMARY_CANVAS_SURFACE_ID : id/,
	);
	assert.match(
		controller,
		/current\.tabs\.filter\(\(tab\) => tab\.placement !== ["']primary["']\)/,
	);
	assert.match(layout, /const chatHidden = primaryOpen/);

	const captureStart = sidebar.indexOf("onClickCapture");
	const chatProjection = sidebar.indexOf("onOpenChat?.()", captureStart);
	const overlayClose = sidebar.indexOf(
		"shouldNavigate && isOverlay && closeOnThreadSelect",
		captureStart,
	);
	assert.ok(captureStart >= 0 && chatProjection > captureStart);
	assert.ok(
		overlayClose > chatProjection,
		"chat projection must happen before optional drawer close",
	);

	const selectThread = workspace.indexOf("onSelectThread={(threadId)");
	const dismissCanvas = workspace.indexOf("openChat();", selectThread);
	const switchThread = workspace.indexOf("switchToThread(threadId)", selectThread);
	assert.ok(selectThread >= 0 && dismissCanvas > selectThread);
	assert.ok(
		switchThread > dismissCanvas,
		"Canvas must return to chat before async thread hydration",
	);
	assert.match(header, /onClick=\{onOpenChat\}/);
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
