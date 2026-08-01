import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
	PET_ATLAS_LAYOUT,
	PET_MOTION_CLIPS,
	createPetMotionModel,
	getPetClipDurationMs,
	getPetFrameAtElapsedMs,
	reducePetMotion,
} from "../../../lib/pets/motion.ts";

const read = (relativePath) =>
	readFileSync(new URL(`../${relativePath}`, import.meta.url), "utf8");

test("pet atlas contract matches the hatch-pet 8x9 layout", () => {
	assert.deepEqual(PET_ATLAS_LAYOUT, {
		columns: 8,
		rows: 9,
		cellWidth: 192,
		cellHeight: 208,
		width: 1_536,
		height: 1_872,
	});
	assert.equal(PET_MOTION_CLIPS.idle.row, 0);
	assert.equal(PET_MOTION_CLIPS.thinking.row, 7);
	assert.equal(PET_MOTION_CLIPS.success.row, 4);
	assert.equal(PET_MOTION_CLIPS.error.row, 5);
	assert.equal(PET_MOTION_CLIPS.waiting.row, 6);
	assert.equal(PET_MOTION_CLIPS.review.row, 8);
});

test("frame selection is deterministic for loops, one-shots and reduced motion", () => {
	const idle = PET_MOTION_CLIPS.idle;
	const idleDuration = getPetClipDurationMs(idle);
	assert.equal(getPetFrameAtElapsedMs(idle, 0), 0);
	assert.equal(getPetFrameAtElapsedMs(idle, 279), 0);
	assert.equal(getPetFrameAtElapsedMs(idle, 280), 1);
	assert.equal(getPetFrameAtElapsedMs(idle, idleDuration), 0);
	assert.equal(getPetFrameAtElapsedMs(idle, 999_999, true), 0);

	const success = PET_MOTION_CLIPS.success;
	assert.equal(getPetFrameAtElapsedMs(success, 999_999), 4);
	assert.equal(getPetFrameAtElapsedMs(success, 999_999, true), 2);
});

test("runtime events override reactions and transient states expire predictably", () => {
	let model = createPetMotionModel(10);
	model = reducePetMotion(model, { type: "runtime.thinking", atMs: 20 });
	assert.equal(model.state, "thinking");

	model = reducePetMotion(model, { type: "interaction.tap", atMs: 30 });
	assert.equal(model.state, "greeting");
	assert.equal(model.resumeState, "thinking");
	assert.equal(
		reducePetMotion(model, { type: "time.elapsed", atMs: 729 }).state,
		"greeting",
	);
	model = reducePetMotion(model, { type: "time.elapsed", atMs: 730 });
	assert.equal(model.state, "thinking");

	model = reducePetMotion(model, { type: "runtime.success", atMs: 800 });
	assert.equal(model.state, "success");
	model = reducePetMotion(model, { type: "time.elapsed", atMs: 1_900 });
	assert.equal(model.state, "idle");

	model = reducePetMotion(model, { type: "runtime.waiting", atMs: 2_000 });
	assert.equal(model.state, "waiting");
	model = reducePetMotion(model, { type: "runtime.review", atMs: 2_100 });
	assert.equal(model.state, "review");
	model = reducePetMotion(model, { type: "runtime.error", atMs: 2_200 });
	assert.equal(model.state, "error");
});

test("mobile pet renderer owns atlas cropping without starting a second chat runtime", () => {
	const sprite = read("components/pet/pet-sprite.tsx");
	const motion = read("components/pet/use-pet-motion.ts");
	const assets = read("src/pets/assets.ts");
	const webAssets = read("src/pets/assets.web.ts");
	const runtimeActivity = read("src/pets/runtime-activity.ts");
	const runtimeProvider = read("src/product-chat/runtime-provider.tsx");
	const selection = read("src/pets/selection.ts");
	assert.match(sprite, /PET_ATLAS_LAYOUT/);
	assert.match(sprite, /getPetFrameAtElapsedMs/);
	assert.match(sprite, /useReducedMotion/);
	assert.match(sprite, /overflow:\s*"hidden"/);
	assert.doesNotMatch(sprite, /ComposerPrimitive|useAuiState|fetch\s*\(/);
	assert.match(motion, /subscribeToPetActivityFeed/);
	assert.match(motion, /state\.threads\.mainThreadId/);
	assert.match(motion, /getPetMessageAcceptedSnapshot/);
	assert.match(runtimeActivity, /lib\/pets\/runtime-activity/);
	assert.match(
		runtimeProvider,
		/agent\.subscribe\(createPetActivityAgentSubscriber\(\)\)/,
	);
	assert.match(selection, /typeof globalThis\.window !== "undefined"/);
	assert.doesNotMatch(read("components/pet/pet-mini-assistant.tsx"), /onMessageSent/);
	assert.equal((assets.match(/active:\s*require\(/g) ?? []).length, 10);
	assert.equal((assets.match(/thumbnail:\s*require\(/g) ?? []).length, 10);
	assert.match(assets, /atlases\/kolibri-v2\.webp/);
	assert.match(webAssets, /PET_CATALOG\.map/);
	assert.match(webAssets, /\/pets\/active\//);
	assert.match(webAssets, /pet\.motionAssetVersion/);
	assert.doesNotMatch(webAssets, /require\s*\(|unstable_path/);
});
