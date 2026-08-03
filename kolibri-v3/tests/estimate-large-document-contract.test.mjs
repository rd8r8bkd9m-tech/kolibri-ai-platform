import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (relativePath) => readFile(path.join(APP_ROOT, relativePath), "utf8");

test("EstimateEditor 1.4 separates total rows from its bounded row window", async () => {
	const [schema, artifact, widgets] = await Promise.all([
		read("lib/generative-ui/schema.ts"),
		read("backend/app/estimate_artifact.py"),
		read("backend/app/product_widgets.py"),
	]);

	assert.match(schema, /"1\.4"/);
	assert.match(schema, /"overhead"/);
	assert.match(schema, /"tax"/);
	assert.match(schema, /"contingency"/);
	assert.match(schema, /operationId:/);
	assert.match(schema, /resourceId:/);
	assert.match(schema, /evidenceId:/);
	assert.match(schema, /estimateGenerationRunId:/);
	assert.match(schema, /technologyCardRevisionId:/);
	assert.match(schema, /technologyCardHash:/);
	assert.match(schema, /qualityStatus:/);
	assert.match(schema, /rowPage:[\s\S]{0,500}limit: z\.number\(\)\.int\(\)\.min\(0\)\.max\(100\)/);
	assert.match(schema, /Estimate 1\.4 requires rowPage metadata/);
	assert.match(schema, /estimate\.rows\.length > limit/);
	assert.match(schema, /estimate\.pricing\.totalRows !== totalRows/);

	assert.match(artifact, /def estimate_view\(/);
	assert.match(artifact, /page_rows = all_rows\[safe_offset : safe_offset \+ safe_limit\]/);
	assert.match(artifact, /"rowPage": \{/);
	assert.match(artifact, /"totalRows": len\(all_rows\)/);
	assert.match(widgets, /estimate_view\([\s\S]{0,300}row_limit=0/);
	assert.match(widgets, /arguments=\{"\$type": "EstimateEditor", \*\*view\}/);
});

test("web reads 100-row pages and saves only optimistic row deltas", async () => {
	const [documentClient, editor, estimateRoute, rowsRoute, backendRoute] =
		await Promise.all([
			read("lib/estimate/document.ts"),
			read("components/assistant-ui/product-widgets/estimate-editor.tsx"),
			read("app/api/v3/projects/[projectId]/estimate/route.ts"),
			read("app/api/v3/projects/[projectId]/estimate/rows/route.ts"),
			read("backend/app/project_artifacts.py"),
		]);

	assert.match(documentClient, /ESTIMATE_ROW_PAGE_SIZE = 100/);
	assert.match(documentClient, /Math\.min\(ESTIMATE_ROW_PAGE_SIZE/);
	assert.match(documentClient, /ESTIMATE_ROW_MUTATION_BATCH_MAX = 200/);
	assert.match(documentClient, /export async function loadEstimateWindow/);
	assert.match(documentClient, /offset: String\(window\.offset\)/);
	assert.match(documentClient, /limit: String\(window\.limit\)/);
	assert.match(documentClient, /export async function saveEstimateRowDelta/);
	assert.match(documentClient, /version: input\.estimate\.version/);
	assert.match(documentClient, /upsertRows: delta\.upsertRows/);
	assert.match(documentClient, /deleteRowIds: delta\.deleteRowIds/);
	assert.match(documentClient, /returnPage: window/);
	assert.match(
		documentClient,
		/\/estimate\/rows`,[\s\S]{0,300}method: "PATCH"/,
	);
	assert.doesNotMatch(documentClient, /method: "PATCH"[\s\S]{0,200}\/estimate`/);

	assert.match(editor, /loadEstimateWindow/);
	assert.match(editor, /saveEstimateRowDelta/);
	assert.doesNotMatch(editor, /body: JSON\.stringify\(\{ title:.*rows/s);

	assert.match(estimateRoute, /for \(const key of \["offset", "limit"\]/);
	assert.match(estimateRoute, /Number\(value\) > 100/);
	assert.match(estimateRoute, /response\.headers\.set\("Deprecation", "true"\)/);
	assert.match(estimateRoute, /rel="successor-version"/);
	assert.match(rowsRoute, /\/estimate\/rows/);
	assert.match(rowsRoute, /method: "PATCH"/);
	assert.match(backendRoute, /limit: int = Query\(default=100, ge=0, le=100\)/);
	assert.match(backendRoute, /@router\.patch\("\/{project_id}\/estimate\/rows"\)/);
});

test("native mobile has the same paged read and delta mutation contract", async () => {
	const [contracts, client] = await Promise.all([
		read("apps/kolibri-mobile/src/verticals/construction-estimates/contracts.ts"),
		read("apps/kolibri-mobile/src/verticals/construction-estimates/client.ts"),
	]);

	assert.match(contracts, /NATIVE_ESTIMATE_PAGE_SIZE = 100/);
	assert.match(contracts, /schemaVersion: "1\.2" \| "1\.3" \| "1\.4"/);
	assert.match(contracts, /rowPage\?: NativeEstimateRowPage/);
	assert.match(contracts, /value\.rows\.length > rowPage\.limit/);
	assert.doesNotMatch(contracts, /value\.rows\.length > 200/);
	assert.match(contracts, /upsertRows/);
	assert.match(contracts, /deleteRowIds/);
	assert.match(contracts, /returnPage/);
	assert.match(client, /offset: String/);
	assert.match(client, /limit: String/);
	assert.match(client, /\/estimate\/rows/);
	assert.doesNotMatch(client, /\/estimate`,[\s\S]{0,120}method: "PATCH"/);
});

test("fixture row count cannot satisfy the live large-document contract", async () => {
	const [fixtureJourney, liveSpec] = await Promise.all([
		read("backend/tests/test_public_estimate_journey.py"),
		read("tests/e2e/full-estimate-live.spec.ts"),
	]);

	assert.match(fixtureJourney, /transport\/persistence only, never semantic QA/);
	assert.match(liveSpec, /presented\.rowPage\?\.limit\)\.toBe\(0\)/);
	assert.match(liveSpec, /loadAllEstimateRows/);
	assert.match(liveSpec, /MAXIMUM_ESTIMATE_PAGE_ROWS = 100/);
	assert.match(liveSpec, /analyzeEstimateQuality/);
});
