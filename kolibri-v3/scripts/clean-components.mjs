#!/usr/bin/env node

import { existsSync, readdirSync, statSync } from "node:fs";
import { join, extname, relative, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const ROOT = process.cwd();

const DEFAULT_DIR = "components";
const TARGET_EXTS = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]);
const SKIP_DIRS = new Set([".next", ".git", "node_modules", "dist", "build", "output", "coverage", "public"]);

function parseArg(name, fallback) {
  const idx = process.argv.indexOf(name);
  return idx !== -1 && idx + 1 < process.argv.length && !process.argv[idx + 1].startsWith("--")
    ? process.argv[idx + 1]
    : fallback;
}

function collectFiles(dir, out) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith(".")) continue;

    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      collectFiles(full, out);
      continue;
    }

    if (TARGET_EXTS.has(extname(entry.name))) {
      out.push(full);
    }
  }
}

function runBiome(filePaths, writeMode) {
  const chunksize = 120;
  for (let i = 0; i < filePaths.length; i += chunksize) {
    const chunk = filePaths.slice(i, i + chunksize).map((file) => relative(ROOT, file));
    const args = ["-y", "@biomejs/biome", "format", ...chunk];
    if (writeMode) {
      args.push("--write");
    }

    const result = spawnSync("npx", args, {
      cwd: ROOT,
      stdio: "inherit",
      shell: false,
    });

    if (result.status !== 0) {
      return false;
    }
  }
  return true;
}

const rawDir = parseArg("--dir", DEFAULT_DIR);
const targetDir = resolve(ROOT, rawDir);
const checkMode = process.argv.includes("--check") || process.argv.includes("--dry-run");

if (!existsSync(targetDir) || !statSync(targetDir).isDirectory()) {
  console.error(`[components-cleaner] target directory does not exist: ${rawDir}`);
  process.exit(1);
}

const files = [];
collectFiles(targetDir, files);

if (files.length === 0) {
  console.log(`[components-cleaner] no files found in ${rawDir}`);
  process.exit(0);
}

console.log(`[components-cleaner] scanning ${rawDir} (${files.length} files)`);
console.log(`[components-cleaner] mode: ${checkMode ? "check" : "write"}`);

const ok = runBiome(files, !checkMode);
if (!ok) {
  console.error("[components-cleaner] failed");
  process.exit(1);
}

console.log("[components-cleaner] done");
