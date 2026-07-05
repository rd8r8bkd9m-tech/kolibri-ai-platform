#!/usr/bin/env node

import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";

const repoRoot = process.cwd();

const artifactManifestPath = path.join(repoRoot, "release/artifact-manifest.json");
const releaseManifestPath = path.join(repoRoot, "release/manifest.json");
const finalReportPath = path.join(repoRoot, "release/final-report.md");

const bundleExclude = new Set([
  "release/manifest.json",
  "release/final-report.md",
  "release/artifact-manifest.json",
]);

const bundleRoots = [
  "README.md",
  "Cargo.toml",
  "package.json",
  "pnpm-workspace.yaml",
  "Makefile",
  ".github",
  "apps",
  "crates",
  "services",
  "proto",
  "migrations",
  "infra",
  "docs",
  "release",
  "CNAME",
];

function sha256Hex(content) {
  return createHash("sha256").update(content).digest("hex");
}

async function fileSha256(relPath) {
  const abs = path.join(repoRoot, relPath);
  const buf = await fs.readFile(abs);
  return sha256Hex(buf);
}

async function pathExists(relPath) {
  try {
    await fs.stat(path.join(repoRoot, relPath));
    return true;
  } catch {
    return false;
  }
}

async function walkFiles(relPath, out) {
  const abs = path.join(repoRoot, relPath);
  const stat = await fs.stat(abs);
  if (stat.isFile()) {
    out.push(relPath);
    return;
  }
  if (!stat.isDirectory()) {
    return;
  }
  const names = await fs.readdir(abs);
  names.sort();
  for (const name of names) {
    await walkFiles(path.join(relPath, name), out);
  }
}

function normalizeRel(p) {
  return p.split(path.sep).join("/");
}

async function main() {
  const nowUtc = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  const releaseManifest = JSON.parse(await fs.readFile(releaseManifestPath, "utf8"));

  const bundleFiles = [];
  for (const root of bundleRoots) {
    if (!(await pathExists(root))) {
      continue;
    }
    await walkFiles(root, bundleFiles);
  }
  const normalized = bundleFiles
    .map(normalizeRel)
    .filter((p) => !bundleExclude.has(p))
    .sort();

  const lines = [];
  for (const rel of normalized) {
    const sum = await fileSha256(rel);
    lines.push(`${sum}  ${rel}`);
  }
  const bundleDigest = sha256Hex(`${lines.join("\n")}\n`);

  const report = await fs.readFile(finalReportPath, "utf8");
  const updatedReport = report
    .replace(
      /Aggregate release bundle SHA-256 at report time: `[a-f0-9]{64}`\./,
      `Aggregate release bundle SHA-256 at report time: \`${bundleDigest}\`.`
    )
    .replace(
      /Bundle hash scope: .*\n/,
      "Bundle hash scope: content hash over release artifacts excluding `release/manifest.json`, `release/final-report.md`, `release/artifact-manifest.json` to avoid self-referential hashing.\n"
    );
  await fs.writeFile(finalReportPath, updatedReport, "utf8");

  releaseManifest.generated_at_utc = nowUtc;
  releaseManifest.release_bundle_sha256 = bundleDigest;
  releaseManifest.release_bundle_scope =
    "content hash over tracked release artifacts excluding release/manifest.json, release/final-report.md and release/artifact-manifest.json to avoid self-referential hashing";
  if (!releaseManifest.artifact_manifest) {
    releaseManifest.artifact_manifest = {};
  }
  releaseManifest.artifact_manifest.generated_at_utc = nowUtc;

  const releaseManifestText = `${JSON.stringify(releaseManifest, null, 2)}\n`;
  await fs.writeFile(releaseManifestPath, releaseManifestText, "utf8");

  const artifactManifest = JSON.parse(await fs.readFile(artifactManifestPath, "utf8"));
  for (const entry of artifactManifest.entries) {
    if (!(await pathExists(entry.path))) {
      throw new Error(`artifact entry path missing: ${entry.path}`);
    }
    entry.sha256 = await fileSha256(entry.path);
  }
  artifactManifest.generated_at_utc = nowUtc;
  const artifactManifestText = `${JSON.stringify(artifactManifest, null, 2)}\n`;
  await fs.writeFile(artifactManifestPath, artifactManifestText, "utf8");

  console.log(`synced release manifests at ${nowUtc}`);
  console.log(`release_bundle_sha256=${bundleDigest}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
