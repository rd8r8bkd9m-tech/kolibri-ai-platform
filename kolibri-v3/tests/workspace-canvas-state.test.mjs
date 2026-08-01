import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import ts from "typescript";

const root = process.cwd();
const moduleCache = new Map();

function loadTypeScriptModule(relativePath) {
	const absolutePath = path.resolve(root, relativePath);
	if (moduleCache.has(absolutePath)) return moduleCache.get(absolutePath).exports;
	const source = fs.readFileSync(absolutePath, "utf8");
	const output = ts.transpileModule(source, {
		compilerOptions: {
			module: ts.ModuleKind.CommonJS,
			target: ts.ScriptTarget.ES2022,
		},
		fileName: absolutePath,
	}).outputText;
	const module = { exports: {} };
	moduleCache.set(absolutePath, module);
	const localRequire = (specifier) => {
		if (!specifier.startsWith(".")) throw new Error(`Unexpected import: ${specifier}`);
		const target = path.resolve(path.dirname(absolutePath), specifier);
		return loadTypeScriptModule(
			path.relative(root, path.extname(target) ? target : `${target}.ts`),
		);
	};
	new Function("require", "module", "exports", output)(
		localRequire,
		module,
		module.exports,
	);
	return module.exports;
}

const canvas = loadTypeScriptModule("lib/workspace-canvas/state.ts");
const registry = loadTypeScriptModule("lib/workspace-canvas/registry.ts");

test("primary chat canvas stays mounted and cannot be closed or minimized", () => {
	const primary = canvas.createPrimaryChatCanvas({
		projectId: "project-1",
		threadId: "thread-1",
	});
	let state = canvas.createWorkspaceCanvasState([primary]);

	state = canvas.workspaceCanvasReducer(state, {
		type: "canvas/close",
		canvasId: primary.id,
	});
	state = canvas.workspaceCanvasReducer(state, {
		type: "canvas/presentation",
		canvasId: primary.id,
		presentation: "minimized",
	});

	assert.equal(state.canvases[primary.id].presentation, "docked");
	assert.equal(state.canvases[primary.id].role, "primary");
	assert.equal(
		canvas.getWorkspaceCanvasActiveSurface(state, primary.id).threadId,
		"thread-1",
	);
});

test("auxiliary canvases are independent, unbounded state entries", () => {
	let state = canvas.createWorkspaceCanvasState([
		canvas.createPrimaryChatCanvas(),
	]);
	for (let index = 0; index < 1_000; index += 1) {
		state = canvas.workspaceCanvasReducer(state, {
			type: "canvas/open",
			canvas: {
				id: `canvas:aux:${index}`,
				scope: {
					linkMode: "project",
					projectId: `project:${index % 10}`,
				},
				slot: "right",
				title: `Документ ${index}`,
				view: {
					id: `document:${index}`,
					surface: {
						kind: "document",
						projectId: `project:${index % 10}`,
						resourceId: `document:${index}`,
					},
					title: `Документ ${index}`,
				},
			},
		});
	}

	assert.equal(state.canvasOrder.length, 1_001);
	assert.equal(state.focusedCanvasId, "canvas:aux:999");
	assert.equal(state.canvases["canvas:aux:42"].scope.projectId, "project:2");
	assert.equal(
		canvas.getWorkspaceCanvasActiveSurface(state, "canvas:aux:42").resourceId,
		"document:42",
	);
});

test("views are registry-driven tabs and fullscreen ownership is exclusive", () => {
	let state = canvas.createWorkspaceCanvasState([
		canvas.createPrimaryChatCanvas(),
	]);
	for (const id of ["left", "right"]) {
		state = canvas.openWorkspaceCanvas(state, {
			id,
			title: id,
			view: {
				id: `${id}:files`,
				surface: { kind: "files" },
				title: "Файлы",
			},
		});
	}
	state = canvas.openCanvasView(state, "right", {
		id: "right:chat",
		surface: { kind: "chat", threadId: "thread-secondary" },
		title: "Второй чат",
	});
	state = canvas.setWorkspaceCanvasPresentation(state, "left", "fullscreen");
	state = canvas.setWorkspaceCanvasPresentation(state, "right", "fullscreen");

	assert.equal(state.canvases.left.presentation, "expanded");
	assert.equal(state.canvases.right.presentation, "fullscreen");
	assert.equal(state.canvases.right.views.length, 2);
	assert.equal(
		canvas.getWorkspaceCanvasActiveSurface(state, "right").threadId,
		"thread-secondary",
	);
});

test("surface registry is the single lookup and rejects duplicate ids", () => {
	const definitions = [
		{
			id: "files",
			label: "Файлы",
			capabilities: registry.DEFAULT_CANVAS_CAPABILITIES,
			payload: { renderer: "files" },
		},
		{
			id: "chat",
			label: "Чат",
			capabilities: registry.DEFAULT_CANVAS_CAPABILITIES,
			payload: { renderer: "chat" },
		},
	];
	const surfaceRegistry = registry.createCanvasSurfaceRegistry(definitions);

	assert.equal(surfaceRegistry.get("files").payload.renderer, "files");
	assert.equal(surfaceRegistry.has("marketplace"), false);
	assert.throws(
		() => registry.createCanvasSurfaceRegistry([...definitions, definitions[0]]),
		/Duplicate canvas surface/,
	);
});
