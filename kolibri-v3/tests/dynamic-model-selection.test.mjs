import assert from "node:assert/strict";
import test from "node:test";

import {
	catalogModelSelectionId,
	effectiveModelSelectionId,
} from "../lib/models/selection.ts";

const models = [
	{ profile: "auto", id: "auto", isDefault: true },
	{ profile: "vendor-a", id: "shared-model", isDefault: true },
	{ profile: "vendor-b", id: "shared-model", isDefault: true },
	{ profile: "future-agent", id: "future-fast", isDefault: false },
];

test("model selection accepts runtime profiles that were not compiled into the UI", () => {
	assert.equal(
		effectiveModelSelectionId(models, {
			preferredAgentProfile: "future-agent",
			preferredModel: "future-fast",
		}),
		"future-agent:future-fast",
	);
});

test("model selection remains unambiguous when providers reuse model IDs", () => {
	assert.equal(catalogModelSelectionId(models[1]), "vendor-a:shared-model");
	assert.equal(catalogModelSelectionId(models[2]), "vendor-b:shared-model");
	assert.notEqual(
		catalogModelSelectionId(models[1]),
		catalogModelSelectionId(models[2]),
	);
});
