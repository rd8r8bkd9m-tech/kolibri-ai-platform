import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (path) =>
	readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("desktop exposes a searchable command palette for the active workspace", async () => {
	const [palette, workspace, view, header] = await Promise.all([
		readSource(
			"components/kolibri-shell/workspace-command-palette.tsx",
		),
		readSource(
			"components/kolibri-shell/desktop-workspace/desktop-workspace.tsx",
		),
		readSource(
			"components/kolibri-shell/desktop-workspace/desktop-workspace-view.tsx",
		),
		readSource("components/kolibri-shell/workspace-header.tsx"),
	]);

	assert.match(palette, /from ["']cmdk["']/);
	assert.match(palette, /<Command\.Input/);
	assert.match(palette, /<Command\.Empty/);
	assert.match(palette, /heading=["']Действия["']/);
	assert.match(palette, /heading=["']Диалоги["']/);
	assert.match(palette, /heading=["']Проекты["']/);
	assert.match(palette, /heading=["']Документы["']/);
	assert.match(palette, /Найти команду, диалог, проект или документ/);
	assert.match(palette, /run\(\(\) => onSelectThread\(thread\.id\)\)/);
	assert.match(palette, /run\(\(\) => onSelectProject\(project\)\)/);
	assert.match(palette, /run\(\(\) => onSelectFile\(file\)\)/);

	assert.match(workspace, /const \[commandPaletteOpen, setCommandPaletteOpen\]/);
	assert.match(workspace, /<DesktopWorkspaceView/);
	assert.match(workspace, /aui\.threads\(\)\.switchToNewThread\(\)/);
	assert.match(workspace, /aui\.threads\(\)\.switchToThread\(threadId\)/);
	assert.match(view, /<WorkspaceCommandPalette/);
	assert.match(view, /onOpenBrowser=\{\(\) => auxiliary\.openTool\(["']browser["']\)\}/);
	assert.match(view, /onOpenReview=\{\(\) => auxiliary\.openTool\(["']review["']\)\}/);

	assert.match(header, /data-command-palette-launcher=["']header["']/);
	assert.match(header, /label=["']Команды и поиск["']/);
	assert.match(header, /shortcut=["']⌘K["']/);
});
