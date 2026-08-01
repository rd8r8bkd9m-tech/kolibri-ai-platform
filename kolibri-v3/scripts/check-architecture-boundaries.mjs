#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const projectRoot = path.resolve(import.meta.dirname, "..");
const sourceGlobs = ["app", "components", "lib", "backend", "packages", "scripts", "tests"];

const ALLOWLIST_SOURCE_PREFIXES = [
  "@/",
  "react",
  "next",
  "react/",
  "next/",
  "@assistant-ui",
  "@assistant-ui/",
  "@radix-ui/",
  "@streamdown/",
  "streamdown",
  "zod",
  "lucide-react",
  "node:",
  "http",
  "https",
];

const extensionPatterns = new Set([".ts", ".tsx", ".js", ".mjs"]);
const sourceCodeImport = /(?:import|export)\s+(?:[^"'`]+?\s+from\s+)?["']([^"']+)["']/g;
const requireImport = /\brequire\(\s*["']([^"']+)["']\s*\)/g;

const violations = [];

async function collectFiles(baseDir) {
  const entries = await fs.readdir(baseDir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
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

function isAllowedSource(source) {
  if (ALLOWLIST_SOURCE_PREFIXES.some((prefix) => source.startsWith(prefix))) {
    return true;
  }
  return false;
}

function isBoundaryViolation(importSource, fromFile) {
  if (isAllowedSource(importSource)) {
    return false;
  }

  if (importSource.startsWith("./") || importSource.startsWith("../")) {
    const absoluteImport = path.resolve(path.dirname(fromFile), importSource);
    if (!absoluteImport.startsWith(projectRoot)) {
      return true;
    }
    return false;
  }

  return false;
}

async function checkFile(filePath) {
  const source = await fs.readFile(filePath, "utf8");
  const relativePath = path.relative(projectRoot, filePath);

for (const matcher of [sourceCodeImport, requireImport]) {
    const regex = new RegExp(matcher.source, "g");
    let match;
    while ((match = regex.exec(source)) !== null) {
      const importSource = match[1];
      if (importSource === "") {
        continue;
      }
      if (isBoundaryViolation(importSource, filePath)) {
        violations.push({
          file: relativePath,
          source: importSource,
        });
      }
    }
  }
}

for (const rootName of sourceGlobs) {
  const root = path.join(projectRoot, rootName);
  const files = await collectFiles(root);
  for (const file of files) {
    await checkFile(file);
  }
}

if (violations.length > 0) {
  console.error("Architecture boundary check failed:");
  for (const violation of violations) {
    console.error(
      `- ${violation.file} imports ${violation.source} (outside canonical project root)`,
    );
  }
  process.exit(1);
}

console.log("Architecture boundaries are within canonical project root.");
