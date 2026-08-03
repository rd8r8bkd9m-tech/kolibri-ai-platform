import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (relativePath) =>
	readFileSync(new URL(`../${relativePath}`, import.meta.url), "utf8");

test("the pet overlay lets mobile chat gestures reach the message list", () => {
	const pet = read("components/pet/pet-mini-assistant.tsx");
	const thread = read("components/assistant-ui/thread.tsx");

	assert.match(
		pet,
		/style=\{\[StyleSheet\.absoluteFill, \{ pointerEvents: "box-none" \}\]\}/,
	);
	assert.match(pet, /pointerEvents: open \? "auto" : "none"/);
	assert.doesNotMatch(pet, /\spointerEvents=/);
	assert.match(pet, /accessibilityElementsHidden=\{!open\}/);
	assert.match(
		pet,
		/importantForAccessibility=\{open \? "yes" : "no-hide-descendants"\}/,
	);
	assert.match(pet, /\{open \? \([\s\S]*?<PetComposer accent=\{pet\.accent\} \/>/);
	assert.doesNotMatch(pet, /passThroughOverlay/);

	assert.match(thread, /<ThreadPrimitive\.MessagesFlatList/);
	assert.match(thread, /style=\{styles\.flex\}/);
	assert.match(thread, /root: \{ flex: 1, minHeight: 0, minWidth: 0 \}/);
	assert.match(thread, /flex: \{ flex: 1, minHeight: 0, minWidth: 0 \}/);
	assert.match(thread, /flexGrow: 1/);
});
