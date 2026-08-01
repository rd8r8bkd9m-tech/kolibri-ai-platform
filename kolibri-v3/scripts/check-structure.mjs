#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const root = path.resolve(import.meta.dirname, "..");
const failures = [];

const requiredPaths = [
  "AGENTS.md",
  "CONTRIBUTING.md",
  "docs/DEVELOPMENT_STANDARDS.md",
  "docs/PROJECT_MAP.md",
  "docs/SOURCE_OF_TRUTH.md",
  "docs/adr/0000-template.md",
  "app",
  "components/ui",
  "lib/server",
  "backend/app",
  "backend/migrations",
  "backend/tests",
  "apps/kolibri-mobile",
  "packages",
  "deploy/portable",
  "scripts/dev-stack.mjs",
  "scripts/dev-backend.sh",
];

for (const relativePath of requiredPaths) {
  if (!fs.existsSync(path.join(root, relativePath))) {
    failures.push(`missing canonical path: ${relativePath}`);
  }
}

const packageJson = JSON.parse(
  fs.readFileSync(path.join(root, "package.json"), "utf8"),
);
const expectedScripts = {
  dev: "node scripts/dev-stack.mjs",
  "dev:backend": "bash scripts/dev-backend.sh",
  "dev:web": "node scripts/dev-web-blocked.mjs",
  "verify:structure": "node scripts/check-structure.mjs",
};

for (const [name, command] of Object.entries(expectedScripts)) {
  if (packageJson.scripts?.[name] !== command) {
    failures.push(`package script ${name} must be exactly: ${command}`);
  }
}

const markdownFiles = [
  "README.md",
  "CONTRIBUTING.md",
  "docs/DEVELOPMENT_STANDARDS.md",
  "docs/PROJECT_MAP.md",
  "docs/SOURCE_OF_TRUTH.md",
];
const localLinkPattern = /\[[^\]]+\]\((?!https?:|mailto:|#)([^)#]+)(?:#[^)]+)?\)/g;

for (const relativePath of markdownFiles) {
  const absolutePath = path.join(root, relativePath);
  if (!fs.existsSync(absolutePath)) continue;
  const markdown = fs.readFileSync(absolutePath, "utf8");
  for (const match of markdown.matchAll(localLinkPattern)) {
    const target = path.resolve(path.dirname(absolutePath), match[1]);
    if (!fs.existsSync(target)) {
      failures.push(`${relativePath} links to missing path: ${match[1]}`);
    }
  }
}

if (failures.length > 0) {
  console.error("Structure contract failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("Structure contract passed.");
