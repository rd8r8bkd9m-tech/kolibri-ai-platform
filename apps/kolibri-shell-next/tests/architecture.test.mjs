import assert from "node:assert/strict";
import { lstat, readFile, readdir } from "node:fs/promises";
import { createHash } from "node:crypto";
import { dirname, extname, isAbsolute, relative, resolve, sep } from "node:path";
import test from "node:test";

const root = resolve(import.meta.dirname, "..");
const srcRoot = resolve(root, "src");
const inspectedExtensions = new Set([".js", ".jsx", ".mjs", ".ts", ".tsx"]);
const ignoredDirectories = new Set(["dist", "node_modules", ".git", "coverage"]);
const legacyPathFragments = [
  /(^|\/)apps\/kolibri-shell(?:\/|$)/,
  /(^|\/)frontend(?:\/|$)/,
  /(^|\/)legacy(?:\/|$)/,
  /^@legacy(?:\/|$)/,
];

const allowedLayers = {
  app: new Set(["app", "features", "components", "services", "domain"]),
  features: new Set(["features", "components", "services", "domain"]),
  components: new Set(["components", "domain"]),
  services: new Set(["services", "domain"]),
  domain: new Set(["domain"]),
  dev: new Set(["dev", "features", "components", "services", "domain"]),
};

const aliasToLayer = new Map(
  Object.keys(allowedLayers).map((layer) => [`@${layer}`, layer]),
);

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true }).catch((error) => {
    if (error.code === "ENOENT") return [];
    throw error;
  });
  const files = [];
  for (const entry of entries) {
    if (ignoredDirectories.has(entry.name)) continue;
    const path = resolve(directory, entry.name);
    const stats = await lstat(path);
    assert.equal(stats.isSymbolicLink(), false, `symlink is forbidden: ${relative(root, path)}`);
    if (entry.isDirectory()) files.push(...(await walk(path)));
    else files.push(path);
  }
  return files;
}

function importsIn(source) {
  const imports = [];
  const patterns = [
    /\b(?:import|export)\s+(?:type\s+)?(?:[^"']*?\s+from\s+)?["']([^"']+)["']/g,
    /\bimport\s*\(\s*["']([^"']+)["']\s*\)/g,
    /\brequire\s*\(\s*["']([^"']+)["']\s*\)/g,
  ];
  for (const pattern of patterns) {
    for (const match of source.matchAll(pattern)) imports.push(match[1]);
  }
  return imports;
}

function sourceLayer(file) {
  const path = relative(srcRoot, file).split(sep);
  return path.length > 1 ? path[0] : null;
}

function importedLayer(specifier, file) {
  const alias = [...aliasToLayer.keys()].find(
    (candidate) => specifier === candidate || specifier.startsWith(`${candidate}/`),
  );
  if (alias) return aliasToLayer.get(alias);

  if (specifier.startsWith(".")) {
    const target = resolve(dirname(file), specifier);
    const targetRelative = relative(srcRoot, target);
    assert.equal(
      targetRelative.startsWith(`..${sep}`) || isAbsolute(targetRelative),
      false,
      `relative import escapes src: ${relative(root, file)} -> ${specifier}`,
    );
    return targetRelative.split(sep)[0];
  }
  return null;
}

test("source and public trees contain no symlink dependencies", async () => {
  await walk(resolve(root, "src"));
  await walk(resolve(root, "public"));
});

test("all code imports stay clean-room and respect layers", async () => {
  const files = (await walk(root)).filter((file) => inspectedExtensions.has(extname(file)));
  for (const file of files) {
    const source = await readFile(file, "utf8");
    for (const specifier of importsIn(source)) {
      assert.equal(
        legacyPathFragments.some((fragment) => fragment.test(specifier.replaceAll("\\", "/"))),
        false,
        `legacy application import is forbidden: ${relative(root, file)} -> ${specifier}`,
      );

      if (!file.startsWith(`${srcRoot}${sep}`)) continue;
      const from = sourceLayer(file);
      const to = importedLayer(specifier, file);
      if (!from || !to) continue;
      assert.ok(allowedLayers[from], `unknown source layer: ${from}`);
      assert.ok(
        allowedLayers[from].has(to),
        `layer violation: ${relative(root, file)} (${from}) -> ${specifier} (${to})`,
      );
      if (from !== "dev") {
        assert.notEqual(to, "dev", `production source imports development fixture: ${relative(root, file)}`);
      }
    }
  }
});

test("the architecture contract remains present", async () => {
  const contract = await readFile(resolve(root, "docs/component-boundaries.md"), "utf8");
  assert.match(contract, /clean-room shell/i);
  assert.match(contract, /Production has no sample response fallback/);
});

test("the approved bird is copied bytes and runtime pins are exact", async () => {
  const bird = await readFile(resolve(root, "public/kolibri-bird.png"));
  assert.equal(
    createHash("sha256").update(bird).digest("hex"),
    "6f30357f75c963e5e4d85b464b10eadb2545d2a6b40aced54861571c4322c3d7",
  );
  const manifest = JSON.parse(await readFile(resolve(root, "package.json"), "utf8"));
  assert.deepEqual(manifest.engines, { node: "26.5.0", npm: "11.17.0" });
  assert.equal(manifest.packageManager, "npm@11.17.0");
});

test("development fixture is gated by Vite DEV and dynamically imported", async () => {
  const entry = await readFile(resolve(srcRoot, "main.tsx"), "utf8");
  assert.match(entry, /import\.meta\.env\.DEV/);
  assert.match(entry, /await import\(["']@dev\/estimateFixture["']\)/);
  assert.doesNotMatch(entry, /^import .*@dev\/estimateFixture/m);
});
