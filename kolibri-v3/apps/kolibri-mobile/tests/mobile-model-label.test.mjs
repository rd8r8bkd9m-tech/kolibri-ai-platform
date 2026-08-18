import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (relativePath) =>
	readFileSync(new URL(`../${relativePath}`, import.meta.url), "utf8");

test("composer model label never leaks raw platform/user model ids", () => {
	const client = read("src/models/client.ts");
	const selector = read("components/assistant-ui/model-selector.tsx");

	assert.ok(client.includes("(?:platform|user):"));
	assert.ok(client.includes("return exact.displayName"));
	assert.ok(client.includes("model.id.endsWith(`:${slug}`)"));
	assert.ok(client.includes("replace(/[._-]+/g, \" \")"));
	assert.ok(!client.includes("if (!catalog) return preferredModel"));

	// The label must resolve the friendly name before the picker sheet opens.
	assert.ok(selector.includes("if (status === \"idle\" && !catalog) {"));
	assert.ok(!selector.includes("open && status === \"idle\""));
});
