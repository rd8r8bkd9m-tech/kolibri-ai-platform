import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (relativePath) =>
	readFileSync(new URL(`../${relativePath}`, import.meta.url), "utf8");

test("mobile chat gestures reach the message list without a pet overlay", () => {
	const thread = read("components/assistant-ui/thread.tsx");

	assert.doesNotMatch(thread, /<PetMiniAssistant \/>/);
	assert.match(thread, /<ThreadPrimitive\.MessagesFlatList/);
	assert.match(thread, /style=\{styles\.flex\}/);
	assert.match(thread, /root: \{ flex: 1, minHeight: 0, minWidth: 0 \}/);
	assert.match(
		thread,
		/flex: \{ flex: 1, minHeight: 0, minWidth: 0(?:, position: "relative")? \}/,
	);
	assert.match(thread, /flexGrow: 1/);
});
