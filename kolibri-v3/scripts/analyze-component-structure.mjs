#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const ROOT = process.cwd();
const DEFAULT_DIR = "components";
const TARGET_EXTS = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]);
const SKIP_DIRS = new Set([
	".git",
	"node_modules",
	".next",
	"dist",
	"build",
	"coverage",
	"output",
]);

function parseArg(name, fallback) {
	const idx = process.argv.indexOf(name);
	if (idx === -1 || idx + 1 >= process.argv.length) return fallback;
	return process.argv[idx + 1];
}

function parseBool(name, fallback = false) {
	return process.argv.includes(name) || fallback;
}

const targetDir = path.resolve(ROOT, parseArg("--dir", DEFAULT_DIR));
const maxLines = Math.max(1, Number.parseInt(parseArg("--max-lines", "300"), 10));
const strict = parseBool("--strict") || parseBool("--ci");
const top = Math.max(1, Number.parseInt(parseArg("--top", "10"), 10));

function isPascalCase(name) {
	return /^[A-Z][A-Za-z0-9_]*$/.test(name);
}

function walk(dir, out) {
	for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
		if (entry.name.startsWith(".")) continue;
		if (entry.isDirectory()) {
			if (SKIP_DIRS.has(entry.name)) continue;
			walk(path.join(dir, entry.name), out);
			continue;
		}
		if (!TARGET_EXTS.has(path.extname(entry.name))) continue;
		out.push(path.join(dir, entry.name));
	}
}

function countLines(filePath) {
	const text = fs.readFileSync(filePath, "utf8");
	return text === "" ? 0 : text.split(/\n/).length;
}

function analyzeFile(filePath) {
	const text = fs.readFileSync(filePath, "utf8");
	const sourceFile = ts.createSourceFile(
		filePath,
		text,
		ts.ScriptTarget.Latest,
		true,
		ts.ScriptKind.TSX,
	);

	const lines = countLines(filePath);
	let componentDecls = 0;
	let exportedComponents = 0;
	let hooks = 0;
	let jsxBlocks = 0;

	for (const stmt of sourceFile.statements) {
		const isExport = stmt.modifiers?.some((mod) => mod.kind === ts.SyntaxKind.ExportKeyword);

		if (ts.isFunctionDeclaration(stmt) && stmt.name && isPascalCase(stmt.name.text)) {
			componentDecls += 1;
			if (isExport) exportedComponents += 1;
		}

		if (ts.isVariableStatement(stmt)) {
			const decl = stmt.declarationList.declarations[0];
			if (!decl || !ts.isIdentifier(decl.name)) continue;
			if (!isPascalCase(decl.name.text)) continue;
			if (decl.initializer && (ts.isArrowFunction(decl.initializer) || ts.isFunctionExpression(decl.initializer))) {
				componentDecls += 1;
				if (isExport) exportedComponents += 1;
			}
		}
	}

	const sourceText = sourceFile.getText();
	hooks = [...sourceText.matchAll(/\buse[A-Z][A-Za-z0-9_]*/g)].length;
	jsxBlocks = [...sourceText.matchAll(/<\w+/g)].length;

	const hasClientDirective = /^"use client"/m.test(text) || /^'use client'/m.test(text);
	return {
		file: path.relative(ROOT, filePath),
		lines,
		componentDecls,
		exportedComponents,
		hooks,
		jsxBlocks,
		hasClientDirective,
	};
}

if (!fs.existsSync(targetDir) || !fs.statSync(targetDir).isDirectory()) {
	console.error(`[component-structure] target directory not found: ${targetDir}`);
	process.exit(1);
}

const files = [];
walk(targetDir, files);

const rows = files.map(analyzeFile).sort((a, b) => b.lines - a.lines);
const monoliths = rows.filter((row) => row.lines > maxLines);

console.log("[component-structure] audit", {
	targetDir: path.relative(ROOT, targetDir) || ".",
	totalFiles: rows.length,
	maxLines,
});

console.log(`\n[component-structure] top ${Math.min(top, rows.length)} files by physical size:`);
for (const row of rows.slice(0, Math.min(top, rows.length))) {
	console.log(
		`${String(row.lines).padStart(4, " ")} lines | ${String(row.componentDecls).padStart(2, " ")} comps | ${String(row.exportedComponents).padStart(2, " ")} exports | jsx ${String(row.jsxBlocks).padStart(4, " ")} | ${row.file}`,
	);
}

if (monoliths.length === 0) {
	console.log(`\n[component-structure] no files above ${maxLines} lines.`);
} else {
	console.log(`\n[component-structure] files above ${maxLines} lines (recommend split):`);
	for (const row of monoliths) {
		console.log(`  ${row.lines}\t${row.file}`);
	}
}

const noClientDirective = rows.filter((row) => row.lines > 150 && !row.hasClientDirective);
if (noClientDirective.length) {
	console.log("\n[component-structure] client-side files over 150 lines without 'use client':");
	for (const row of noClientDirective.slice(0, 10)) {
		console.log(`  ${row.lines}\t${row.file}`);
	}
}

if (strict) {
	if (monoliths.length > 0) {
		console.log(`\n[component-structure] strict mode: ${monoliths.length} structural violations`);
		process.exit(1);
	}
	console.log("[component-structure] strict mode: pass");
}
