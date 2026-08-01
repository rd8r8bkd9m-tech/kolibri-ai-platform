#!/usr/bin/env node

import { existsSync, readdirSync } from "node:fs";
import { join, extname } from "node:path";
import { spawnSync } from "node:child_process";

const WEB_ROOT_DIRS = ["app", "components", "lib"];
const MOBILE_ROOT_DIRS = [
  "apps/kolibri-mobile/app",
  "apps/kolibri-mobile/src",
  "apps/kolibri-mobile/components",
  "apps/kolibri-mobile/lib",
  "apps/kolibri-mobile/constants",
  "apps/kolibri-mobile/hooks",
];
const INCLUDE_MOBILE = process.argv.includes("--include-mobile") || process.argv.includes("--all");
const ROOT_DIRS = INCLUDE_MOBILE ? [...WEB_ROOT_DIRS, ...MOBILE_ROOT_DIRS] : WEB_ROOT_DIRS;
const TARGET_EXTS = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]);
const SKIP_DIRS = new Set([
  ".next",
  ".git",
  "node_modules",
  "dist",
  "build",
  "output",
  "coverage",
  "public",
]);

const DRY_RUN = process.argv.includes("--check") || process.argv.includes("--dry-run");
const FORCE = process.argv.includes("--force");
const ROOT = process.cwd();

function runCommand(description, command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: ROOT,
    stdio: options.stdio ?? "inherit",
    shell: false,
    ...options,
  });

  if (result.error) {
    console.error(`❌ ${description}:`, result.error.message);
    return false;
  }
  if (result.status !== 0) {
    console.error(`⚠️  ${description}: exited with ${result.status}`);
    return false;
  }
  return true;
}

function resolveTargetDirs() {
  return ROOT_DIRS.filter((dir) => existsSync(join(ROOT, dir)));
}

function walkTsLikeFiles(dir, out) {
  const entries = readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.name.startsWith(".")) {
      continue;
    }
    if (entry.isDirectory()) {
      if (!SKIP_DIRS.has(entry.name)) {
        walkTsLikeFiles(join(dir, entry.name), out);
      }
      continue;
    }
    const ext = extname(entry.name);
    if (TARGET_EXTS.has(ext)) {
      out.push(join(dir, entry.name));
    }
  }
}

function collectFiles() {
  const files = [];
  for (const dir of resolveTargetDirs()) {
    walkTsLikeFiles(join(ROOT, dir), files);
  }
  return files;
}

function runBiomeFormat(files) {
  if (files.length === 0) {
    console.warn("[react-frontend-cleaner] no target files found");
    return false;
  }

  const chunkSize = 150;
  let ok = true;
  for (let index = 0; index < files.length; index += chunkSize) {
    const chunk = files
      .slice(index, index + chunkSize)
      .map((file) => file.replace(`${ROOT}/`, ""));
    const args = [
      "-y",
      "@biomejs/biome",
      "format",
      ...chunk,
    ];
    if (!DRY_RUN) {
      args.push("--write");
    }
    if (!runCommand(`biome format batch ${index}`, "npx", args)) {
      ok = false;
      break;
    }
  }
  return ok;
}

function runDuplicateScan() {
  return runCommand("duplicate component scan", "node", ["scripts/find-duplicate-components.mjs"], {
    stdio: "inherit",
  });
}

function runTypecheck() {
  return runCommand("typecheck", "npm", ["run", "-s", "typecheck"], {
    stdio: "inherit",
  });
}

function printHeader() {
  console.log("[react-frontend-cleaner] scan started");
  console.log(`[react-frontend-cleaner] root dirs: ${ROOT_DIRS.join(", ")}`);
  console.log(`[react-frontend-cleaner] dry-run/check: ${DRY_RUN ? "yes" : "no"}`);
}

function printFooter(success) {
  if (success) {
    console.log("[react-frontend-cleaner] done");
  } else {
    console.log("[react-frontend-cleaner] finished with issues");
  }
}

function main() {
  printHeader();

  const files = collectFiles();
  const formatWorked = runBiomeFormat(files);
  const scanWorked = runDuplicateScan();
  const shouldTypecheck = !DRY_RUN && (FORCE || process.argv.includes("--typecheck"));
  const allSucceeded = formatWorked && scanWorked && (!shouldTypecheck || runTypecheck());

  printFooter(allSucceeded);
  if (!allSucceeded) {
    process.exit(1);
  }
}

main();
