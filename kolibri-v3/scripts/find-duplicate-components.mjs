#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const ROOT_DIR = path.join(process.cwd(), "components");
const TARGET_EXTS = new Set([".ts", ".tsx", ".js", ".jsx"]);

function walkFiles(dir, out) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walkFiles(full, out);
      continue;
    }
    if (!TARGET_EXTS.has(path.extname(entry.name))) continue;
    out.push(full);
  }
}

function normalizeText(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/.*$/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}

function hashText(text) {
  return crypto.createHash("sha1").update(text).digest("hex");
}

function isCandidateName(name) {
  if (!name) return false;
  const first = name[0];
  return first === first?.toUpperCase();
}

function collectDeclarationText(file, node, sourceText) {
  if (ts.isFunctionDeclaration(node) && node.body) {
    return {
      name: node.name?.text ?? "anonymous",
      text: sourceText.slice(node.getStart(), node.body.getEnd()),
      type: "function",
      lineStart: sourceText.slice(0, node.getStart()).split("\n").length,
      lineEnd: sourceText.slice(0, node.body.getEnd()).split("\n").length,
    };
  }

  if (ts.isVariableStatement(node)) {
    const decl = node.declarationList.declarations[0];
    if (!decl || !ts.isIdentifier(decl.name)) return null;
    if (!isCandidateName(decl.name.text)) return null;
    if (decl.initializer && ts.isArrowFunction(decl.initializer)) {
      return {
        name: decl.name.text,
        text: sourceText.slice(decl.initializer.getStart(), decl.initializer.getEnd()),
        type: "arrow",
        lineStart: sourceText.slice(0, decl.getStart()).split("\n").length,
        lineEnd: sourceText.slice(0, decl.initializer.getEnd()).split("\n").length,
      };
    }
    if (decl.initializer && ts.isFunctionExpression(decl.initializer)) {
      return {
        name: decl.name.text,
        text: sourceText.slice(decl.initializer.getStart(), decl.initializer.getEnd()),
        type: "function-expression",
        lineStart: sourceText.slice(0, decl.getStart()).split("\n").length,
        lineEnd: sourceText.slice(0, decl.initializer.getEnd()).split("\n").length,
      };
    }
  }

  return null;
}

function extractEntries(filePath) {
  const sourceText = fs.readFileSync(filePath, "utf8");
  const sourceFile = ts.createSourceFile(
    filePath,
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const entries = [];

  sourceFile.statements.forEach((stmt) => {
    const declaration = collectDeclarationText(filePath, stmt, sourceText);
    if (!declaration) return;
    const normalized = normalizeText(declaration.text);
    if (normalized.length < 400) return;

    entries.push({
      ...declaration,
      file: filePath,
      key: hashText(normalized),
      normalizedLength: normalized.length,
    });
  });

  return entries;
}

const files = [];
walkFiles(ROOT_DIR, files);

const catalog = new Map();
for (const filePath of files) {
  for (const entry of extractEntries(filePath)) {
    const list = catalog.get(entry.key);
    if (!list) {
      catalog.set(entry.key, []);
    }
    catalog.get(entry.key).push(entry);
  }
}

let duplicated = 0;
for (const [hash, entries] of catalog.entries()) {
  if (entries.length < 2) continue;
  duplicated += 1;
  console.log("----");
  console.log(`duplicate-${entries[0].type} body (${entries.length} copies, ${entries[0].normalizedLength} chars, key=${hash})`);
  for (const entry of entries) {
    console.log(`  ${entry.name}  ${entry.file}:${entry.lineStart}-${entry.lineEnd}`);
  }
}

if (duplicated === 0) {
  console.log("No duplicate component blocks found.");
}
