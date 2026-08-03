import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("full-estimate QA labels fixture coverage and reserves semantics for the live gate", async () => {
	const [runtime, unitFixture, journey, liveSpec, qualityOracle, runner, orchestrationSpec] = await Promise.all([
		read("backend/app/direct_model_runtime.py"),
		read("backend/tests/test_full_estimate_generation.py"),
		read("backend/tests/test_public_estimate_journey.py"),
		read("tests/e2e/full-estimate-live.spec.ts"),
		read("tests/estimate-semantic-quality.mjs"),
		read("scripts/run-live-estimate-qa.mjs"),
		read("docs/ESTIMATE_GENERATION_ORCHESTRATION.md"),
	]);

	assert.match(runtime, /Every natural-language estimate request uses the general/);
	assert.doesNotMatch(
		runtime,
		/if estimate_requested:[\s\S]{0,5000}execution_profile="estimate-intake"/,
	);
	assert.match(unitFixture, /Exercises section aggregation only/);
	assert.match(unitFixture, /test_fixture_section_transport_has_no_total_row_cap/);
	assert.doesNotMatch(unitFixture, /def test_full_estimate_is_generated/);
	assert.match(journey, /transport\/persistence only, never semantic QA/);
	assert.match(journey, /test_fixture_transport_preserves_every_large_estimate_row/);
	assert.doesNotMatch(journey, /test_product_qa_full_estimate/);
	assert.match(journey, /expected_rows = transport\.section_count \* transport\.rows_per_section/);
	assert.match(journey, /csv_text\.count\("ресурсная позиция"\) == expected_rows/);
	assert.match(liveSpec, /MINIMUM_FULL_ESTIMATE_ROWS = 1_000/);
	assert.match(liveSpec, /\["codex-cli", "mimo-code"\]/);
	assert.doesNotMatch(liveSpec, /fixture|server-house-estimate|server-construction-estimate/);
	assert.match(liveSpec, /analyzeEstimateQuality/);
	assert.match(liveSpec, /MAXIMUM_PRESENT_ARGUMENT_BYTES/);
	assert.match(liveSpec, /rowPage/);
	assert.match(liveSpec, /estimate\/rows/);
	assert.match(liveSpec, /editedPage\.version/);
	assert.match(liveSpec, /estimate_version_conflict/);
	assert.match(liveSpec, /generationSummary/);
	assert.match(liveSpec, /technology-card\/latest/);
	assert.match(liveSpec, /cardResourceCount/);
	assert.match(qualityOracle, /Numbered or synthetic placeholder descriptions/);
	assert.match(qualityOracle, /Rows without operation\/card linkage/);
	assert.match(qualityOracle, /Source-backed rows without evidence reference/);
	assert.match(qualityOracle, /Rows whose line total is not deterministic/);
	assert.match(runner, /KOLIBRI_E2E_QA_STORAGE_STATE must point/);
	assert.match(orchestrationSpec, /Fixture providers may verify SSE/);
	assert.match(orchestrationSpec, /Only the\s+separate live gate/);
});
