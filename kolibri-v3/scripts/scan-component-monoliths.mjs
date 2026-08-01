#!/usr/bin/env node

import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative } from "node:path";

const ROOT = process.cwd();
const TARGET_EXTS = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]);
const SKIP = new Set([".git", "node_modules", ".next", "dist", "build", "output", "coverage"]);

function parseArg(name, fallback) {
  const idx = process.argv.indexOf(name);
  if (idx === -1 || idx + 1 >= process.argv.length) {
    return fallback;
  }
  return process.argv[idx + 1];
}

function asInt(name, fallback) {
  const raw = parseArg(name);
  if (!raw) return fallback;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

const targetRoot = parseArg("--dir", "components");
const maxLines = asInt("--max-lines", 300);
const failOnBreaches = process.argv.includes("--strict") || process.argv.includes("--ci");

const rootDir = join(ROOT, targetRoot);

function collectFiles(dir, out) {
  const entries = readdirSync(dir, { withFileTypes: true });

  for (const entry of entries) {
    if (entry.name.startsWith(".")) continue;

    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (SKIP.has(entry.name)) continue;
      collectFiles(full, out);
      continue;
    }

    if (!TARGET_EXTS.has(extname(entry.name))) continue;
    out.push(full);
  }
}

function lineCount(path) {
  const data = readFileSync(path, "utf8");
  return data === "" ? 0 : data.split("\n").length;
}

if (!statSync(rootDir).isDirectory()) {
  console.error(`[component-monoliths] target directory missing: ${targetRoot}`);
  process.exit(1);
}

const allFiles = [];
collectFiles(rootDir, allFiles);

const breaches = allFiles
  .map((file) => ({
    rel: relative(ROOT, file),
    lines: lineCount(file),
  }))
  .filter((row) => row.lines >= maxLines)
  .sort((a, b) => b.lines - a.lines);

if (breaches.length === 0) {
  console.log(`[component-monoliths] no files >= ${maxLines} lines in ${targetRoot}`);
  process.exit(0);
}

console.log(`[component-monoliths] threshold: ${maxLines} lines`);
for (const row of breaches) {
  console.log(`${String(row.lines).padStart(4, " ")}\t${row.rel}`);
}
console.log(`[component-monoliths] total: ${breaches.length}`);

if (failOnBreaches) {
  console.log("[component-monoliths] strict mode: exiting with error");
  process.exit(1);
}
