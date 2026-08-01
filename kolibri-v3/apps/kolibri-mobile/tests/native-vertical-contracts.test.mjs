import assert from "node:assert/strict";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import { parseEstimateCatalog } from "../src/verticals/construction-estimates/contracts.ts";

const root = new URL("..", import.meta.url).pathname;
const read = (path) => readFileSync(join(root, path), "utf8");

test("pet registry contains only bundled reviewed raster assets", () => {
  const registry = read("src/pets/registry.ts");
  const assets = read("src/pets/assets.ts");
  const expected = [
    "kolibri",
    "lumi",
    "fini",
    "iskra",
    "runi",
    "buki",
    "mohi",
    "nimbi",
    "klik",
    "zumi",
  ];
  for (const slug of expected) {
    for (const variant of ["active", "thumbs"]) {
      const asset = join(
        root,
        "assets",
        "pets",
        variant,
        `${slug}-v1.webp`,
      );
      assert.equal(existsSync(asset), true, asset);
      assert.ok(statSync(asset).size > 1_000, `${asset} is unexpectedly small`);
      assert.match(assets, new RegExp(`${variant}/${slug}-v1\\.webp`));
    }
  }
  assert.doesNotMatch(assets, /https?:\/\//);
  assert.equal((assets.match(/active:\s*require\(/g) ?? []).length, 10);
  assert.equal((assets.match(/thumbnail:\s*require\(/g) ?? []).length, 10);
  assert.match(registry, /NATIVE_PET_ASSETS/);
  assert.doesNotMatch(registry, /require\s*\(/);
});

test("pet mini assistant binds to the active assistant-ui composer", () => {
  const component = read("components/pet/pet-mini-assistant.tsx");
  const motion = read("components/pet/use-pet-motion.ts");
  const selection = read("src/pets/selection.ts");
  const haptics = read("lib/haptics.ts");
  assert.match(component, /ComposerPrimitive\.Root/);
  assert.match(component, /ComposerPrimitive\.Input/);
  assert.match(component, /ComposerPrimitive\.Send/);
  assert.match(component, /ComposerPrimitive\.Cancel/);
	assert.match(component, /useAuiState/);
	assert.match(motion, /state\.thread/);
	assert.match(motion, /assistantMessage\.status\.type === "incomplete"/);
	assert.match(motion, /derivePetActivityFromRuntime/);
	assert.match(motion, /toolRequiresAction/);
  assert.match(motion, /"approval"/);
  assert.match(motion, /"waiting"/);
  assert.match(motion, /"running"/);
  assert.match(component, /PetSprite/);
	assert.match(component, /useReducedMotion/);
	assert.match(component, /BackHandler/);
	assert.match(component, /onLongPress/);
	assert.match(component, /delayLongPress=\{380\}/);
	assert.match(component, /haptics\.medium\(\)/);
  assert.match(component, /readNativePetId/);
	assert.match(component, /persistNativePetId\(nextPet\.id\)/);
	assert.doesNotMatch(component, /\bfetch\s*\(/);
	assert.doesNotMatch(component, /fake|mock response/i);

  assert.match(selection, /kolibri\.mobile\.pet-id\.v1/);
  assert.match(selection, /SecureStore\.getItemAsync/);
  assert.match(selection, /SecureStore\.setItemAsync/);
  assert.match(selection, /NATIVE_PETS\.some/);
  assert.match(selection, /Platform\.OS === "web"/);
  assert.match(haptics, /Platform\.OS === "ios" \|\| Platform\.OS === "android"/);

	const thread = read("components/assistant-ui/thread.tsx");
	assert.match(thread, /useDrawerStatus/);
	assert.match(thread, /drawerOpen \? null/);
	assert.match(thread, /<PetMiniAssistant \/>/);
  assert.match(thread, /<Composer \/>/);
});

test("construction vertical fails closed and uses only real V3 endpoints", () => {
  const access = read("src/verticals/construction-estimates/access.ts");
  const client = read("src/verticals/construction-estimates/client.ts");
  const registration = read(
    "src/verticals/construction-estimates/registration.ts",
  );
  assert.match(access, /Array\.isArray\(user\.entitlements\)/);
  assert.match(access, /construction\.estimates\.workspace/);
  assert.match(access, /construction\.estimates\.use/);
  assert.match(access, /enabled: false/);
  assert.match(registration, /construction\.estimate\.renderer\.v1/);
  assert.match(client, /\/v1\/documents/);
  assert.match(
    client,
    /\/v1\/projects\/\$\{encodeURIComponent\(estimate\.projectId\)\}\/estimate/,
  );
  assert.match(client, /method: "PATCH"/);
  assert.match(client, /estimatePatchBody/);
  assert.doesNotMatch(client, /fixture|mock|sample|localStorage/i);
});

test("native estimate catalog ignores other valid document slot types", () => {
	const common = {
		projectId: "project_native_catalog_01",
		projectName: "Ремонт квартиры",
		status: "draft",
		version: 1,
		updatedAt: "2026-08-01T13:00:00Z",
		editable: false,
	};
	const estimates = parseEstimateCatalog({
		documents: [
			{
				...common,
				id: "document_native_source_01",
				category: "documents",
				kind: "document",
				name: "Исходные данные",
			},
			{
				...common,
				id: "document_native_estimate_01",
				category: "estimates",
				kind: "estimate",
				name: "Предварительная смета",
				rowCount: 3,
				total: "15000.00",
				currency: "RUB",
				editable: true,
			},
			{
				...common,
				id: "document_native_contract_01",
				category: "contracts",
				kind: "contract",
				name: "Договор",
			},
		],
	});

	assert.equal(estimates.length, 1);
	assert.equal(estimates[0]?.id, "document_native_estimate_01");
	assert.throws(
		() =>
			parseEstimateCatalog({
				documents: [
					{
						...common,
						id: "document_native_invalid_estimate_01",
						category: "estimates",
						kind: "estimate",
						name: "Повреждённая смета",
					},
				],
			}),
		/Document catalog contains an invalid estimate/,
	);
});

test("native auth accepts only the server-projected entitlement contract", () => {
  const session = read("src/auth/mobile-session.tsx");
  assert.match(session, /entitlements: readonly string\[\]/);
  assert.match(session, /const entitlements = user\.entitlements/);
  assert.match(session, /Array\.isArray\(entitlements\)/);
  assert.match(
    session,
    /new Set\(entitlements\)\.size !== entitlements\.length/,
  );
  assert.match(
    session,
    /establish\("\/v1\/mobile\/auth\/login", \{ \.\.\.input, device \}\)/,
	);
});

test("mobile auth submit validation matches the V3 password contract", () => {
	const screen = read("components/auth/auth-screen.tsx");
	assert.match(screen, /passwordMinLength = mode === "register" \? 12 : 1/);
	assert.match(screen, /password\.length >= passwordMinLength/);
	assert.match(screen, /Для регистрации нужен пароль не короче 12 символов/);
});

test("mobile chat sends the canonical V1 AG-UI standard payload", () => {
  const provider = read("src/product-chat/runtime-provider.tsx");
  assert.match(provider, /buildMobileAgUiPayload/);
  assert.match(provider, /state: null/);
  assert.match(provider, /tools: \[\]/);
  assert.match(provider, /context: \[\]/);
  assert.match(provider, /executionMode: "standard"/);
  assert.match(provider, /agentProfile: normalizeAgentProfile\(agentProfile\)/);
  assert.doesNotMatch(
    provider,
    /forwardedProps:\s*\{[\s\S]*accessMode:\s*"standard"/,
  );
	assert.match(provider, /const headers = new Headers\(init\.headers\)/);
	assert.match(provider, /headers\.set\("Content-Type", "application\/json"\)/);
	assert.doesNotMatch(
		provider,
		/headers:\s*\{[\s\S]*Object\.fromEntries\(new Headers\(init\.headers\)/,
	);
});

test("estimate editor preserves optimistic versioning and honest conflicts", () => {
  const screen = read("app/estimates.tsx");
  const contracts = read(
    "src/verticals/construction-estimates/contracts.ts",
  );
  assert.match(screen, /estimate_version_conflict/);
  assert.match(screen, /client\.open\(estimate\.projectId\)/);
  assert.match(screen, /client\.save\(estimate, title, rows\)/);
  assert.match(screen, /Данные и сохранение не подменяются локальным демо/);
  assert.match(contracts, /version: estimate\.version/);
  assert.match(contracts, /lineTotal: _lineTotal/);
  assert.match(contracts, /isNativeEstimateDraftValid/);
});
