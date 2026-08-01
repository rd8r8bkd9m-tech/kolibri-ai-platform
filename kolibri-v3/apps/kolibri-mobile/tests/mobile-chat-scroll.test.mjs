import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (relativePath) =>
	readFileSync(new URL(`../${relativePath}`, import.meta.url), "utf8");

test("the pet overlay lets mobile chat gestures reach the message list", () => {
	const pet = read("components/pet/pet-mini-assistant.tsx");
	const thread = read("components/assistant-ui/thread.tsx");

	assert.match(pet, /style=\{\[StyleSheet\.absoluteFill, styles\.passThroughOverlay\]\}/);
	assert.match(pet, /passThroughOverlay: \{ pointerEvents: "none" \}/);
	assert.match(pet, /borderColor: pet\.accent,[\s\S]{0,80}pointerEvents: "auto"/);
	assert.match(pet, /pointerEvents:\s*panelPointerEvents/);
	assert.doesNotMatch(pet, /pointerEvents="box-none"/);

	assert.match(thread, /<ThreadPrimitive\.MessagesFlatList/);
	assert.match(thread, /style=\{styles\.flex\}/);
	assert.match(thread, /root: \{ flex: 1, minHeight: 0, minWidth: 0 \}/);
	assert.match(thread, /flex: \{ flex: 1, minHeight: 0, minWidth: 0 \}/);
	assert.match(thread, /flexGrow: 1/);
});
