import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (relativePath) => readFile(path.join(APP_ROOT, relativePath), "utf8");

const ROUTE_ROOT = "app/api/v3/projects/[projectId]/estimate/generation";

test("same-origin BFF exposes bounded durable generation reads", async () => {
	const [latest, run, card, backendRouter, main] = await Promise.all([
		read(`${ROUTE_ROOT}/route.ts`),
		read(`${ROUTE_ROOT}/[runId]/route.ts`),
		read(`${ROUTE_ROOT}/technology-card/latest/route.ts`),
		read("backend/app/estimate_generation_router.py"),
		read("backend/app/main.py"),
	]);

	for (const source of [latest, run, card]) {
		assert.match(source, /SAFE_PROJECT_ID/);
		assert.match(source, /encodeURIComponent\(projectId\)/);
		assert.match(source, /export async function GET/);
		assert.match(source, /proxyV3JsonRequest/);
		assert.match(source, /method: "GET"/);
	}
	assert.match(run, /SAFE_RUN_ID = \/\^run_estimate_generation_/);
	assert.match(run, /encodeURIComponent\(runId\)/);
	assert.match(latest, /\/estimate\/generation`/);
	assert.match(run, /\/estimate\/generation\/\$\{encodeURIComponent\(runId\)\}`/);
	assert.match(card, /\/estimate\/generation\/technology-card\/latest`/);

	assert.match(backendRouter, /@router\.get\("\/{project_id}\/estimate\/generation"\)/);
	assert.match(
		backendRouter,
		/@router\.get\("\/{project_id}\/estimate\/generation\/technology-card\/latest"\)/,
	);
	assert.match(main, /include_router\(estimate_generation_router\)/);
});

test("cancel BFF forwards authenticated idempotent mutation without widening input", async () => {
	const [cancel, proxy, backendRouter] = await Promise.all([
		read(`${ROUTE_ROOT}/[runId]/cancel/route.ts`),
		read("lib/server/v3-backend.ts"),
		read("backend/app/estimate_generation_router.py"),
	]);

	assert.match(cancel, /SAFE_PROJECT_ID/);
	assert.match(cancel, /SAFE_RUN_ID = \/\^run_estimate_generation_/);
	assert.match(cancel, /export async function POST/);
	assert.match(cancel, /encodeURIComponent\(projectId\)/);
	assert.match(cancel, /encodeURIComponent\(runId\)/);
	assert.match(cancel, /\/cancel`/);
	assert.match(cancel, /method: "POST"/);
	assert.match(cancel, /maxRequestBytes: 4 \* 1_024/);

	for (const header of [
		"authorization",
		"cookie",
		"idempotency-key",
		"origin",
		"x-csrf-token",
	]) {
		assert.ok(proxy.includes(`"${header}"`), `proxy must forward ${header}`);
	}
	assert.match(
		backendRouter,
		/@router\.post\("\/{project_id}\/estimate\/generation\/\{run_id\}\/cancel"\)/,
	);
});
