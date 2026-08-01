#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const projectRoot = path.resolve(import.meta.dirname, "..");
const sourceGlobs = ["app", "components", "lib", "backend", "packages", "scripts", "server", "tests"];
const extensionPatterns = new Set([".ts", ".tsx", ".js", ".mjs", ".jsx", ".py"]);

const importMatchers = [
  /(?:import|export)\s+(?:[\s\S]*?\s+from\s+)?["']([^"']+)["']/g,
  /\brequire\(\s*["']([^"']+)["']\s*\)/g,
  /\bimport\(\s*["']([^"']+)["']\s*\)/g,
];

const legacyNeedles = ["kolibri-v2", "kolibri-backend", "kolibri-v3-new", "frontend", "kolibri-v3/frontend"];

const ignoredDirNames = new Set([
  "node_modules",
  ".next",
  ".venv",
  "venv",
  ".git",
  "dist",
  "build",
  "coverage",
  "site-packages",
  "__pycache__",
  ".ruff_cache",
  ".pytest_cache",
  "output",
  ".playwright-cli",
  "var",
  "generated",
]);

const extensionPriority = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".json"];

function isIgnoredEntry(entryName) {
  return ignoredDirNames.has(entryName);
}

function normalizePath(value) {
  return value.replace(/\\/g, "/");
}

function isLegacyReference(rawImportSource) {
  const normalized = rawImportSource.toLowerCase();
  return legacyNeedles.some((needle) => {
    const boundaryPattern = new RegExp(`(?:^|/)${needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$")}(?:$|/)`);
    return boundaryPattern.test(normalized);
  });
}

function getLayer(filePath) {
  const relativePath = normalizePath(path.relative(projectRoot, filePath));

  const exactLayerMap = [
    { prefix: "components/ui", layer: "components/ui" },
    { prefix: "components/kolibri-shell", layer: "components/kolibri-shell" },
    { prefix: "components/assistant-ui", layer: "components/assistant-ui" },
    { prefix: "components/kolibri-workspace", layer: "components/kolibri-workspace" },
    { prefix: "backend/app", layer: "backend/app" },
    { prefix: "lib/server", layer: "lib/server" },
  ];

  if (exactLayerMap.some(({ prefix }) => relativePath === prefix)) {
    return exactLayerMap.find(({ prefix }) => relativePath === prefix).layer;
  }

  if (relativePath.startsWith("app/")) return "app";
  if (relativePath.startsWith("components/ui/")) return "components/ui";
  if (relativePath.startsWith("components/kolibri-shell/")) return "components/kolibri-shell";
  if (relativePath.startsWith("components/assistant-ui/")) return "components/assistant-ui";
  if (relativePath.startsWith("components/kolibri-workspace/")) return "components/kolibri-workspace";
  if (relativePath.startsWith("components/")) return "components";
  if (relativePath.startsWith("lib/server/")) return "lib/server";
  if (relativePath.startsWith("lib/")) return "lib";
  if (relativePath.startsWith("backend/app/")) return "backend/app";
  if (relativePath.startsWith("backend/")) return "backend";
  if (relativePath.startsWith("packages/")) return "packages";
  if (relativePath.startsWith("server/")) return "server";
  if (relativePath.startsWith("scripts/")) return "scripts";
  if (relativePath.startsWith("tests/")) return "tests";

  return null;
}

const dependencyRules = {
  app: {
    allow: "*",
  },
  components: {
    allowPrefix: [
      "components/",
      "lib/",
      "components",
    ],
  },
  "components/ui": {
    allowPrefix: [
      "components/ui/",
      "lib/utils",
      "lib/",
      "components/",
    ],
  },
  "components/assistant-ui": {
    allowPrefix: [
      "components/assistant-ui/",
      "components/ui/",
      "components/kolibri-shell/",
      "components/kolibri-workspace/",
      "lib/",
      "components/",
    ],
  },
  "components/kolibri-shell": {
    allowPrefix: [
      "components/kolibri-shell/",
      "components/assistant-ui/",
      "components/kolibri-workspace/",
      "components/ui/",
      "components/theme/",
      "lib/",
      "components/",
    ],
  },
  "components/kolibri-workspace": {
    allowPrefix: [
      "components/kolibri-workspace/",
      "components/assistant-ui/",
      "components/ui/",
      "components/kolibri-shell/",
      "lib/",
      "components/",
    ],
  },
  lib: {
    allowPrefix: ["lib/", "backend/", "backend/app/", "server/"] ,
  },
  "lib/server": {
    allowPrefix: ["lib/", "lib/server/", "backend/", "server/", "app/"],
  },
  backend: {
    allowPrefix: ["backend/", "backend/app/", "lib/", "server/", "packages/", "scripts/"],
  },
  "backend/app": {
    allowPrefix: ["backend/app/", "backend/", "server/", "lib/", "packages/", "scripts/"],
  },
  packages: {
    allowPrefix: ["packages/", "backend/", "lib/", "server/", "app/", "components/", "scripts/"]
  },
  scripts: {
    allowPrefix: ["scripts/", "lib/", "backend/", "app/", "components/", "tests/", "packages/"]
  },
  server: {
    allowPrefix: ["server/", "backend/", "lib/", "packages/"],
  },
  tests: {
    allow: "*",
  },
};

function classifyImport(source, fromFile) {
  if (!source) return null;

  const rawSource = source.trim();

  if (
    rawSource.startsWith("http") ||
    rawSource.startsWith("node:") ||
    rawSource.startsWith("#")
  ) {
    return null;
  }

  if (rawSource.startsWith("@/")) {
    return path.resolve(projectRoot, rawSource.slice(2));
  }

  if (rawSource.startsWith("./") || rawSource.startsWith("../") || rawSource.startsWith("/") ) {
    const base = rawSource.startsWith("/")
      ? path.join(projectRoot, rawSource.replace(/^\//, ""))
      : path.resolve(path.dirname(fromFile), rawSource);
    return resolveImportTarget(base);
  }

  return null;
}

async function resolveImportTarget(basePath) {
  const normalizedBase = path.normalize(basePath);

  for (const ext of extensionPriority) {
    const asFile = `${normalizedBase}${ext}`;
    try {
      const stats = await fs.stat(asFile);
      if (stats.isFile()) {
        return asFile;
      }
    } catch {
      // continue
    }
  }

  try {
    const stats = await fs.stat(normalizedBase);
    if (stats.isDirectory()) {
      const indexCandidates = ["index.ts", "index.tsx", "index.js", "index.mjs", "index.py", "index.jsx", "index.cjs"];
      for (const name of indexCandidates) {
        try {
          const indexPath = path.join(normalizedBase, name);
          const indexStats = await fs.stat(indexPath);
          if (indexStats.isFile()) {
            return indexPath;
          }
        } catch {
          // continue
        }
      }
      return normalizedBase;
    }
  } catch {
    return null;
  }

  return null;
}

async function collectFiles(baseDir) {
  const entries = await fs.readdir(baseDir, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    if (isIgnoredEntry(entry.name)) {
      continue;
    }

    const fullPath = path.join(baseDir, entry.name);

    if (entry.isDirectory()) {
      files.push(...(await collectFiles(fullPath)));
      continue;
    }

    if (extensionPatterns.has(path.extname(entry.name))) {
      files.push(fullPath);
    }
  }

  return files;
}

function toLayerAlias(filePath) {
  return normalizePath(path.relative(projectRoot, filePath));
}

function violatesDependency(sourceLayer, targetLayer, targetImportPath) {
  const rule = dependencyRules[sourceLayer];
  if (!rule) {
    return false;
  }

  if (rule.allow === "*") {
    return false;
  }

  const targetRelative = toLayerAlias(targetImportPath);

  if (rule.allowPrefix) {
    return !rule.allowPrefix.some((prefix) => targetRelative.startsWith(prefix));
  }

  return false;
}

async function collectAndCheck() {
  const violations = [];

  for (const rootName of sourceGlobs) {
    const root = path.join(projectRoot, rootName);
    const files = await collectFiles(root);

    for (const filePath of files) {
      const fromLayer = getLayer(filePath);
      if (!fromLayer) {
        continue;
      }

      const source = await fs.readFile(filePath, "utf8");
      const relativePath = path.relative(projectRoot, filePath);

      for (const matcher of importMatchers) {
        const regex = new RegExp(matcher.source, "g");
        let match;

        while ((match = regex.exec(source)) !== null) {
          const importedSource = match[1];
          if (!importedSource) {
            continue;
          }

          if (isLegacyReference(importedSource)) {
            violations.push({
              file: relativePath,
              source: importedSource,
              type: "legacy-reference",
            });
          }

          const resolved = await classifyImport(importedSource, filePath);
          if (!resolved) {
            continue;
          }

          if (!resolved.startsWith(projectRoot)) {
            continue;
          }

          const toLayer = getLayer(resolved);
          if (!toLayer) {
            continue;
          }

          if (violatesDependency(fromLayer, toLayer, resolved)) {
            violations.push({
              file: relativePath,
              source: importedSource,
              type: "boundary",
              fromLayer,
              toLayer,
            });
          }
        }
      }
    }
  }

  if (violations.length > 0) {
    console.error("Layer boundary check failed:");
    for (const violation of violations) {
      if (violation.type === "legacy-reference") {
        console.error(`- ${violation.file} imports legacy path ${violation.source}`);
      } else {
        console.error(
          `- ${violation.file} (${violation.fromLayer}) -> ${violation.source} (${violation.toLayer})`,
        );
      }
    }
    process.exit(1);
  }

  console.log("Layer boundaries passed.");
}

await collectAndCheck();
