import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { PET_CATALOG } from "../lib/pets/catalog.ts";
import {
	PET_ACTIVITY_EVENT_TYPE,
	PET_ATLAS_LAYOUT,
	PET_MOTION_CLIPS,
	createPetMotionModel,
	derivePetActivityFromRuntime,
	getPetFrameAtElapsedMs,
	parsePetActivityEventV1,
	reducePetMotion,
} from "../lib/pets/motion.ts";

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const readSource = (relativePath) =>
	readFile(path.join(APP_ROOT, relativePath), "utf8");
const fileFromPublicUrl = (url) =>
	path.join(APP_ROOT, "public", url.replace(/^\//, ""));

test("the reviewed pet roster and its versioned static fallbacks are complete", async () => {
	const manifest = JSON.parse(await readSource("public/pets/manifest-v1.json"));

	assert.equal(manifest.version, 1);
	assert.equal(manifest.pets.length, 10);
	assert.deepEqual(
		manifest.pets.map((pet) => pet.id),
		PET_CATALOG.map((pet) => pet.id),
	);
	assert.equal(new Set(PET_CATALOG.map((pet) => pet.assetSlug)).size, 10);
	assert.equal(PET_CATALOG[0].motionAssetVersion, "v2");
	assert.equal(
		PET_CATALOG.filter((pet) => pet.motionAssetVersion !== null).length,
		1,
	);

	for (const pet of manifest.pets) {
		for (const field of [
			"name",
			"personality",
			"role",
			"master",
			"active",
			"thumbnail",
		]) {
			assert.ok(pet[field], `${pet.id} is missing ${field}`);
		}
		const [master, active, thumbnail] = await Promise.all([
			stat(fileFromPublicUrl(pet.master)),
			stat(fileFromPublicUrl(pet.active)),
			stat(fileFromPublicUrl(pet.thumbnail)),
		]);
		assert.ok(master.size > 100_000, `${pet.id} master is unexpectedly small`);
		assert.ok(active.size < 80_000, `${pet.id} active fallback is too heavy`);
		assert.ok(thumbnail.size < 12_000, `${pet.id} thumbnail is too heavy`);
	}
});

test("the original Kolibri master remains immutable", async () => {
	const master = await readFile(
		path.join(APP_ROOT, "public/pets/masters/kolibri-v1.png"),
	);
	assert.equal(
		createHash("sha256").update(master).digest("hex"),
		"6f30357f75c963e5e4d85b464b10eadb2545d2a6b40aced54861571c4322c3d7",
	);
	assert.equal(master.readUInt32BE(16), 1254);
	assert.equal(master.readUInt32BE(20), 1254);
	assert.equal(master[25], 6, "source PNG must remain RGBA");
});

test("the Koli v2 atlas is validated once and shipped byte-identically", async () => {
	const [releaseAtlas, webAtlas, nativeAtlas, validation] = await Promise.all([
		readFile(path.join(APP_ROOT, "release/assets/pets/kolibri-v2/spritesheet.webp")),
		readFile(path.join(APP_ROOT, "public/pets/atlases/kolibri-v2.webp")),
		readFile(
			path.join(
				APP_ROOT,
				"apps/kolibri-mobile/assets/pets/atlases/kolibri-v2.webp",
			),
		),
		readSource(
			"release/assets/pets/kolibri-v2/hatch-run/final/validation.json",
		).then(JSON.parse),
	]);
	const checksum = (bytes) =>
		createHash("sha256").update(bytes).digest("hex");
	assert.equal(
		checksum(releaseAtlas),
		"34ecd7fddd2e1360c4a869140fb31b92a1c50e9f5f05d7213964bbe9ab866ae6",
	);
	assert.equal(checksum(webAtlas), checksum(releaseAtlas));
	assert.equal(checksum(nativeAtlas), checksum(releaseAtlas));
	assert.equal(validation.ok, true);
	assert.equal(validation.width, 1536);
	assert.equal(validation.height, 1872);
	assert.equal(validation.mode, "RGBA");
	assert.equal(validation.transparent_rgb_residue_pixels, 0);
	assert.deepEqual(validation.errors, []);
	assert.deepEqual(validation.warnings, []);
});

test("one portable contract owns semantic state, ordered events and atlas timing", () => {
	assert.deepEqual(PET_ATLAS_LAYOUT, {
		columns: 8,
		rows: 9,
		cellWidth: 192,
		cellHeight: 208,
		width: 1536,
		height: 1872,
	});
	assert.equal(PET_MOTION_CLIPS.idle.row, 0);
	assert.equal(PET_MOTION_CLIPS.running.row, 7);
	assert.equal(PET_MOTION_CLIPS.review.row, 8);
	assert.equal(getPetFrameAtElapsedMs(PET_MOTION_CLIPS.idle, 280), 1);
	assert.equal(
		getPetFrameAtElapsedMs(PET_MOTION_CLIPS.success, 999_999),
		4,
	);

	assert.equal(
		derivePetActivityFromRuntime({
			approvalRequired: true,
			isRunning: true,
			lastMessageRole: "assistant",
			lastMessageStatus: "running",
			toolIsRunning: false,
			toolRequiresAction: true,
		}),
		"approval",
	);
	assert.equal(
		derivePetActivityFromRuntime({
			approvalRequired: false,
			isRunning: true,
			lastMessageRole: "assistant",
			lastMessageStatus: "running",
			toolIsRunning: true,
			toolRequiresAction: false,
		}),
		"running",
	);

	const activity = parsePetActivityEventV1({
		type: PET_ACTIVITY_EVENT_TYPE,
		threadId: "thread_pet_01",
		runId: "run_pet_01",
		sequence: 3,
		occurredAt: "2026-08-01T12:00:00Z",
		state: "review",
	});
	assert.ok(activity);
	let model = reducePetMotion(createPetMotionModel(0), {
		type: "server.activity",
		activeThreadId: "thread_pet_01",
		activity,
		atMs: 100,
	});
	assert.equal(model.state, "review");
	const stale = { ...activity, sequence: 2, state: "error" };
	model = reducePetMotion(model, {
		type: "server.activity",
		activeThreadId: "thread_pet_01",
		activity: stale,
		atMs: 200,
	});
	assert.equal(model.state, "review", "stale server events must be ignored");
	assert.equal(parsePetActivityEventV1({ ...activity, sequence: -1 }), null);
});

test("desktop and mobile render the same living entity without another runtime", async () => {
	const [
		desktop,
		desktopHost,
		webSprite,
		webMotion,
		mobile,
		mobileSprite,
		mobileMotion,
		mobileThread,
		mobileWebAssets,
	] = await Promise.all([
		readSource("components/kolibri-shell/kolibri-pet.tsx"),
		readSource(
			"components/kolibri-shell/desktop-workspace/desktop-workspace-view.tsx",
		),
		readSource("components/kolibri-shell/pet/pet-sprite.tsx"),
		readSource("components/kolibri-shell/pet/use-web-pet-motion.ts"),
		readSource("apps/kolibri-mobile/components/pet/pet-mini-assistant.tsx"),
		readSource("apps/kolibri-mobile/components/pet/pet-sprite.tsx"),
		readSource("apps/kolibri-mobile/components/pet/use-pet-motion.ts"),
		readSource("apps/kolibri-mobile/components/assistant-ui/thread.tsx"),
		readSource("apps/kolibri-mobile/src/pets/assets.web.ts"),
	]);

	assert.match(desktopHost, /<KolibriPetHost \/>/);
	assert.match(desktop, /WebPetSprite/);
	assert.match(desktop, /pet\.motionAssetVersion/);
	assert.match(desktop, /ComposerPrimitive\.Root/);
	assert.match(desktop, /setPointerCapture/);
	assert.match(desktop, /event\.key === "ArrowLeft"/);
	assert.match(desktop, /prefers-reduced-motion: reduce/);
	assert.match(webSprite, /PET_ATLAS_LAYOUT/);
	assert.match(webSprite, /getPetFrameAtElapsedMs/);
	assert.match(webMotion, /derivePetActivityFromRuntime/);
	assert.doesNotMatch(desktop, /kolibri-pet-art__idle|kolibri-pet-art__reaction/);

	assert.match(mobile, /PetSprite/);
	assert.match(mobile, /ComposerPrimitive\.Root/);
	assert.match(mobileSprite, /PET_ATLAS_LAYOUT/);
	assert.match(mobileMotion, /derivePetActivityFromRuntime/);
	assert.match(mobileThread, /useDrawerStatus/);
	assert.match(mobileThread, /drawerOpen \? null/);
	assert.match(mobileWebAssets, /PET_CATALOG\.map/);
	assert.match(mobileWebAssets, /\/pets\/active\//);
	assert.match(mobileWebAssets, /pet\.motionAssetVersion/);
	assert.doesNotMatch(mobileWebAssets, /require\s*\(|unstable_path/);

	for (const source of [desktop, webSprite, webMotion, mobile, mobileSprite]) {
		assert.doesNotMatch(source, /\bfetch\s*\(/);
	}
});
