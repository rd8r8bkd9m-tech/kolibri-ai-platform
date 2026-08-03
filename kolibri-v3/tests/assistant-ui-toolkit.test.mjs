import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (file) => readFile(path.join(ROOT, file), "utf8");

test("assistant-ui uses one toolkit and standard message primitives", async () => {
	const [app, toolkit, message, composer, screen, runtime] = await Promise.all([
		read("app/kolibri-app.tsx"),
		read("components/assistant-ui/toolkit.ts"),
		read("components/assistant-ui/thread/parts/thread-message.tsx"),
		read("components/assistant-ui/thread/parts/thread-layout.tsx"),
		read("components/assistant-ui/thread/layouts/thread-screen.tsx"),
		read("app/MyRuntimeProvider.tsx"),
	]);

	assert.match(app, /Tools\(\{ toolkit: kolibriToolkit \}\)/);
	assert.match(app, /unstable_Interactables\(\)/);
	assert.match(toolkit, /defineToolkit/);
	assert.match(toolkit, /generate_image[\s\S]*get_weather[\s\S]*present/);
	assert.match(message, /<MessagePrimitive\.Parts components=\{partsComponents\}/);
	assert.doesNotMatch(message, /renderGroupedPart|switch \(part\.type\)/);
	assert.match(composer, /ComposerPrimitive\.Queue/);
	assert.match(composer, /ComposerPrimitive\.Quote/);
	assert.match(screen, /SelectionToolbarPrimitive\.Quote/);
	assert.match(runtime, /AssistantRuntimeProvider runtime=\{runtime\}/);
	assert.doesNotMatch(runtime, /<GeneratedImageToolUI\s*\/>/);
});
