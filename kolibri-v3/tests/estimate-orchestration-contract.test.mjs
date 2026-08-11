import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";
import { fileURLToPath } from "node:url";

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MIGRATIONS = path.join(APP_ROOT, "backend", "migrations");
const read = (relativePath) => readFile(path.join(APP_ROOT, relativePath), "utf8");

const normalized = (value) => value.replace(/\s+/gu, " ").trim();

test("estimate generation migrations are executable and tenant-scoped", async () => {
	const migrationFiles = (await readdir(MIGRATIONS))
		.filter((name) => /^\d{3}_.+\.sql$/.test(name))
		.sort();
	assert.equal(migrationFiles.at(-1), "059_tbank_recurring.sql");

	const database = new DatabaseSync(":memory:");
	try {
		for (const name of migrationFiles) {
			database.exec(await readFile(path.join(MIGRATIONS, name), "utf8"));
		}
		const [{ user_version: userVersion }] = database
			.prepare("PRAGMA user_version")
			.all();
	assert.equal(userVersion, 59);
		assert.deepEqual(database.prepare("PRAGMA foreign_key_check").all(), []);

		const actualTables = new Set(
			database
				.prepare(
					"SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'estimate_generation_%'",
				)
				.all()
				.map(({ name }) => name),
		);
		assert.deepEqual(
			actualTables,
			new Set([
				"estimate_generation_runs",
				"estimate_generation_sections",
				"estimate_generation_tasks",
				"estimate_generation_checkpoints",
				"estimate_generation_technology_revisions",
				"estimate_generation_evidence",
				"estimate_generation_lineage",
				"estimate_generation_commands",
				"estimate_generation_events",
			]),
		);
	} finally {
		database.close();
	}
});

test("migration 051 fences retries and prevents cross-run provenance", async () => {
	const sql = normalized(
		await read("backend/migrations/051_durable_estimate_generation.sql"),
	);

	for (const status of [
		"queued",
		"running",
		"needs_input",
		"review",
		"ready",
		"failed",
		"cancelled",
	]) {
		assert.match(sql, new RegExp(`'${status}'`));
	}
	for (const stage of [
		"project_case",
		"decomposition",
		"technology",
		"research",
		"pricing",
		"expansion",
		"reconciliation",
		"persisting",
		"complete",
	]) {
		assert.match(sql, new RegExp(`'${stage}'`));
	}
	for (const role of [
		"technologist",
		"quantity_engineer",
		"resource_normer",
		"technical_researcher",
		"procurement",
		"logistics",
		"reviewer",
		"orchestrator",
	]) {
		assert.match(sql, new RegExp(`'${role}'`));
	}

	assert.match(sql, /idempotency_key_hash TEXT NOT NULL/);
	assert.match(sql, /request_hash TEXT NOT NULL/);
	assert.match(sql, /fencing_token INTEGER NOT NULL/);
	assert.match(sql, /lease_owner TEXT, lease_token TEXT, lease_until TEXT/);
	assert.match(
		sql,
		/FOREIGN KEY \(tenant_id, run_id, section_id, section_key\) REFERENCES estimate_generation_sections \(tenant_id, run_id, id, section_key\)/,
	);
	assert.match(
		sql,
		/FOREIGN KEY \(tenant_id, run_id, task_id\) REFERENCES estimate_generation_tasks \(tenant_id, run_id, id\)/,
	);
	assert.match(
		sql,
		/FOREIGN KEY \(tenant_id, run_id, technology_revision_id\) REFERENCES estimate_generation_technology_revisions \(tenant_id, run_id, id\)/,
	);
	assert.match(
		sql,
		/FOREIGN KEY \(tenant_id, run_id, evidence_id\) REFERENCES estimate_generation_evidence \(tenant_id, run_id, id\)/,
	);
	assert.match(
		sql,
		/status <> 'ready' OR \( stage = 'complete' AND quality_status = 'passed' AND result_document_id IS NOT NULL AND result_estimate_version IS NOT NULL \)/,
	);
	assert.match(sql, /status <> 'succeeded' OR result_json IS NOT NULL/);
	assert.match(
		sql,
		/status <> 'passed' OR completed_task_count = expected_task_count/,
	);
});

test("migration 051 keeps generated cards, evidence and row lineage auditable", async () => {
	const sql = normalized(
		await read("backend/migrations/051_durable_estimate_generation.sql"),
	);

	assert.match(sql, /published_technology_card_id TEXT/);
	assert.match(
		sql,
		/FOREIGN KEY \(tenant_id, project_id, published_technology_card_id\) REFERENCES technology_cards \(tenant_id, project_id, id\)/,
	);
	assert.match(sql, /kind TEXT NOT NULL CHECK \(kind IN \('technical', 'price'\)\)/);
	for (const source of [
		"user_input",
		"approved_catalog",
		"official_reference",
		"supplier_offer",
		"market_aggregate",
		"ai_candidate",
	]) {
		assert.match(sql, new RegExp(`'${source}'`));
	}
	assert.match(
		sql,
		/source_type <> 'ai_candidate' OR confidence_status = 'preliminary'/,
	);
	assert.match(
		sql,
		/kind <> 'price' OR \( region IS NOT NULL AND unit IS NOT NULL AND unit_price IS NOT NULL AND currency = 'RUB' AND observed_at IS NOT NULL \)/,
	);
	assert.match(sql, /producing_task_id TEXT/);
	assert.match(sql, /producing_checkpoint_id TEXT/);
	assert.match(sql, /operation_id TEXT NOT NULL/);
	assert.match(sql, /resource_id TEXT NOT NULL/);
	assert.match(sql, /line_snapshot_hash TEXT NOT NULL/);
	assert.match(
		sql,
		/line_confidence NOT IN \('source_backed', 'verified'\) OR evidence_id IS NOT NULL/,
	);
});

test("ADR and source-of-truth declare one publication boundary", async () => {
	const [adr, sourceOfTruth, orchestration, artifact, core] = await Promise.all([
		read("docs/adr/0005-durable-universal-estimate-orchestration.md"),
		read("docs/SOURCE_OF_TRUTH.md"),
		read("docs/ESTIMATE_GENERATION_ORCHESTRATION.md"),
		read("backend/app/estimate_artifact.py"),
		read("backend/app/estimate_generation.py"),
	]);

	for (const table of [
		"estimate_generation_runs",
		"estimate_generation_sections",
		"estimate_generation_tasks",
		"estimate_generation_checkpoints",
		"estimate_generation_technology_revisions",
		"estimate_generation_evidence",
		"estimate_generation_lineage",
		"estimate_generation_commands",
	]) {
		assert.match(adr, new RegExp(`\\b${table}\\b`));
	}
	assert.match(adr, /published_technology_card_id/);
	assert.match(adr, /project `technology_cards` becomes the canonical published/);
	assert.match(sourceOfTruth, /append-only migration 051/);
	assert.match(orchestration, /Row count is an observability metric, not a quality metric/);
	assert.match(orchestration, /recursive allowlisted AST/);
	assert.match(artifact, /class GeneratedQuantityFormula/);
	assert.match(
		artifact,
		/op: Literal\["variable", "constant", "multiply", "add", "divide", "ceil"\]/,
	);
	assert.match(core, /def _normalize_formula\(/);
	assert.match(core, /not isinstance\(expression, Mapping\)/);
	for (const unit of ["чел.-ч", "маш.-ч", "п.м.", "упак.", "рулон", "м²/смену"]) {
		assert.ok(core.includes(`"${unit}"`), `missing canonical unit alias ${unit}`);
	}
});
