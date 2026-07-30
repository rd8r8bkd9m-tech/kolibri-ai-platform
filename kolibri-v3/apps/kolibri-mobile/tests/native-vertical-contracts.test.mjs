import assert from "node:assert/strict";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const root = new URL("..", import.meta.url).pathname;
const read = (path) => readFileSync(join(root, path), "utf8");

test("pet registry contains only bundled reviewed raster assets", () => {
  const registry = read("src/pets/registry.ts");
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
      assert.match(registry, new RegExp(`${variant}/${slug}-v1\\.webp`));
    }
  }
  assert.doesNotMatch(registry, /https?:\/\//);
  assert.equal((registry.match(/active:\s*require\(/g) ?? []).length, 10);
  assert.equal((registry.match(/thumbnail:\s*require\(/g) ?? []).length, 10);
});

test("pet mini assistant binds to the active assistant-ui composer", () => {
  const component = read("components/pet/pet-mini-assistant.tsx");
  const selection = read("src/pets/selection.ts");
  const haptics = read("lib/haptics.ts");
  assert.match(component, /ComposerPrimitive\.Root/);
  assert.match(component, /ComposerPrimitive\.Input/);
  assert.match(component, /ComposerPrimitive\.Send/);
  assert.match(component, /ComposerPrimitive\.Cancel/);
  assert.match(component, /useAuiState/);
  assert.match(component, /state\.thread\.isRunning/);
  assert.match(component, /last\.status\.type === "complete"/);
  assert.match(component, /last\.status\.type === "incomplete"/);
  assert.match(component, /"idle" \| "thinking" \| "success" \| "error"/);
  assert.match(component, /useReducedMotion/);
  assert.match(component, /BackHandler/);
  assert.match(component, /readNativePetId/);
  assert.match(component, /persistNativePetId\(nextPet\.id\)/);
  assert.doesNotMatch(component, /\bfetch\s*\(/);
  assert.doesNotMatch(component, /setTimeout|fake|mock response/i);

  assert.match(selection, /kolibri\.mobile\.pet-id\.v1/);
  assert.match(selection, /SecureStore\.getItemAsync/);
  assert.match(selection, /SecureStore\.setItemAsync/);
  assert.match(selection, /NATIVE_PETS\.some/);
  assert.match(selection, /Platform\.OS === "web"/);
  assert.match(haptics, /Platform\.OS === "ios" \|\| Platform\.OS === "android"/);

  const thread = read("components/assistant-ui/thread.tsx");
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

test("native auth accepts only the server-projected entitlement contract", () => {
  const session = read("src/auth/mobile-session.tsx");
  assert.match(session, /entitlements: readonly string\[\]/);
  assert.match(session, /"entitlements" in value\.user/);
  assert.match(session, /Array\.isArray\(value\.user\.entitlements\)/);
  assert.match(
    session,
    /new Set\(value\.user\.entitlements\)\.size !==\s*value\.user\.entitlements\.length/,
  );
  assert.match(
    session,
    /establish\("\/v1\/mobile\/auth\/login", \{ \.\.\.input, device \}\)/,
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
