import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const readSource = (relativePath) => readFile(path.join(APP_ROOT, relativePath), "utf8");

test("estimate catalog BFF and autocomplete keep authority/privacy boundaries", async () => {
	const [catalogRoute, reviewRoute, marketRoute, client, autocomplete, editor] = await Promise.all([
		readSource("app/api/v3/projects/[projectId]/estimate/catalog/route.ts"),
		readSource("app/api/v3/projects/[projectId]/estimate/catalog/candidates/[candidateId]/review/route.ts"),
		readSource("app/api/v3/projects/[projectId]/estimate/market-prices/route.ts"),
		readSource("lib/estimate/catalog.ts"),
		readSource("components/assistant-ui/product-widgets/catalog-autocomplete.tsx"),
		readSource("components/assistant-ui/product-widgets/estimate-editor.tsx"),
	]);

	for (const source of [catalogRoute, reviewRoute, marketRoute]) {
		assert.match(source, /proxyV3JsonRequest/);
		assert.match(source, /SAFE_PROJECT_ID/);
	}
	assert.match(catalogRoute, /query.*kind.*categoryId.*region.*source.*limit/);
	assert.match(reviewRoute, /SAFE_CANDIDATE_ID/);
	assert.match(marketRoute, /catalogEntryId/);
	assert.match(client, /withCsrfHeader/);
	assert.match(client, /Idempotency-Key/);
	assert.match(client, /credentials:\s*"same-origin"/);
	assert.match(autocomplete, /role="combobox"/);
	assert.match(autocomplete, /role="listbox"/);
	assert.match(autocomplete, /ArrowDown/);
	assert.match(autocomplete, /Escape/);
	assert.match(autocomplete, /На review/);
	assert.match(editor, /CatalogAutocomplete/);
	assert.match(editor, /lineConfidence/);
});
